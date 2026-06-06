"""
Example runner for the Tributary AI layer over the real processed transactions.

Reads `data/processed/transactions.csv`, classifies every transaction against the
DIPN 21 rule pack (`examples/Datasets/hk_dipn21_rules.json`) used as the RAG source,
and writes a single aggregated JSON report.

Design notes:
- Monetary amounts are intentionally IGNORED. The AI layer only judges which
  regulation applies, with what confidence, and whether rules conflict. No figures
  are emitted (numeric slots stay as ``{{engine:...}}`` placeholders for the engine).
- Transactions are deduplicated by their classification signature (amount/date/id
  excluded) so the ~340 rows collapse to a handful of unique groups; each group is
  classified once and mapped back to all its transaction ids.
- Default backend is a deterministic rule matcher (instant, reproducible). Pass
  ``--backend qwen`` to route each unique group through the local Qwen LLM instead.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

# Ensure the `src/` layout is importable when run directly (no PYTHONPATH needed).
_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if _SRC_DIR.is_dir() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from tributary.ai.models import AILayerOutput, RuleCitation, RuleSummary, TransactionContext

# --- Configuration constants ------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "data" / "processed" / "transactions.csv"
DEFAULT_RULES = REPO_ROOT / "examples" / "Datasets" / "hk_dipn21_rules.json"
DEFAULT_OUTPUT = REPO_ROOT / "examples" / "ai_layer_output.json"

# Columns that describe value/time rather than the nature of the flow. Excluded
# from the classification signature so amounts never influence the determination.
AMOUNT_OR_TIME_COLUMNS = ("amount", "date", "id")

# Map raw jurisdiction tokens found in account/counterparty ids to ISO alpha-2.
JURISDICTION_ALIASES = {"hkg": "HK", "hk": "HK"}

# Deterministic matcher thresholds.
MIN_MATCH_CONFIDENCE = 0.35  # below this the group abstains / needs human review
MATERIAL_CONFIDENCE = 0.40  # rules above this are weighed for conflict detection
CONFIDENCE_TIE_BAND = 0.10  # two material rules this close => ambiguous classification
MAX_REPORTED_RULES = 4

# Tokens too generic to carry matching signal.
STOPWORDS = frozenset(
    {
        "the", "and", "for", "are", "from", "with", "that", "this", "their", "which",
        "where", "without", "based", "place", "profits", "income", "revenue", "tax",
        "other", "into", "they", "have", "been", "made", "fees", "fee", "out", "all",
    }
)

# Map flow_direction + record_type to the engine's flow classification enum.
FLOW_CLASSIFICATION_MAP = {
    ("inbound", "tax_revenue"): "REVENUE",
    ("inbound", "revenue"): "REVENUE",
    ("outbound", "expense"): "EXPENSE",
    ("inbound", "intercompany"): "INTERCOMPANY",
    ("outbound", "intercompany"): "INTERCOMPANY",
    ("inbound", "loan"): "LOAN",
    ("outbound", "loan"): "LOAN",
    ("inbound", "capital"): "CAPITAL",
    ("outbound", "capital"): "CAPITAL",
}


# --- Rule pack loading -------------------------------------------------------

def load_rule_pack(rules_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Load the DIPN 21 rule pack JSON.

    Args:
        rules_path: Path to the rule pack JSON file.
    Returns:
        A tuple of (raw rule list, mapping of rule_id -> rule parameters).
    """
    with rules_path.open("r", encoding="utf-8") as handle:
        rules = json.load(handle)
    params_by_id = {rule["id"]: rule.get("parameters", {}) for rule in rules}
    return rules, params_by_id


class JsonRuleRetriever:
    """RAG rule loader backed by the DIPN 21 JSON pack.

    Implements ``get_rule_summaries(jurisdictions)`` (RulePackLoaderProtocol) by
    returning every rule whose jurisdiction matches one of the candidates.
    """

    def __init__(self, rules: List[Dict[str, Any]]) -> None:
        self.rules = rules

    def get_rule_summaries(self, jurisdictions: Iterable[str]) -> List[RuleSummary]:
        """Return rule summaries for the requested jurisdictions.

        Args:
            jurisdictions: ISO alpha-2 codes; empty means return everything.
        Returns:
            The matching rules as RuleSummary records.
        """
        wanted = {str(code).upper() for code in jurisdictions}
        summaries: List[RuleSummary] = []
        for rule in self.rules:
            if wanted and str(rule.get("jurisdiction", "")).upper() not in wanted:
                continue
            summaries.append(
                RuleSummary(
                    id=rule["id"],
                    summary=rule.get("summary", ""),
                    as_of_date=rule.get("as_of_date", ""),
                    source_citation=rule.get("source_citation", ""),
                )
            )
        return summaries


# --- Transaction ingestion ---------------------------------------------------

def read_transactions(input_path: Path) -> List[Dict[str, str]]:
    """Read the processed transactions CSV into a list of row dicts."""
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def infer_jurisdictions(row: Dict[str, str]) -> List[str]:
    """Infer candidate ISO jurisdictions from account/counterparty identifiers."""
    blob = f"{row.get('account_id', '')} {row.get('counterparty_id', '')}".lower()
    found: List[str] = []
    for token, code in JURISDICTION_ALIASES.items():
        if re.search(rf"(?<![a-z]){token}(?![a-z])", blob) and code not in found:
            found.append(code)
    return found or ["HK"]


def build_context(row: Dict[str, str], jurisdictions: List[str]) -> TransactionContext:
    """Build a TransactionContext for a row, excluding monetary amounts."""
    description = row.get("description", "").strip()
    text = (
        f"{description}. Flow {row.get('flow_direction', '')} via GL code "
        f"{row.get('gl_code', '')}; record type {row.get('record_type', '')}; "
        f"counterparty {row.get('counterparty_id', '')}."
    )
    return TransactionContext(
        transaction_text=text,
        candidate_jurisdictions=jurisdictions,
        gl_code=row.get("gl_code", ""),
        flow_direction=row.get("flow_direction", ""),
        record_type=row.get("record_type", ""),
        data_source=row.get("data_source", ""),
        counterparty_id=row.get("counterparty_id", ""),
        currency=row.get("currency", ""),
    )


def signature_of(row: Dict[str, str], jurisdictions: List[str]) -> Tuple[str, ...]:
    """Return the classification signature for a row (amount/date/id excluded)."""
    return (
        ",".join(jurisdictions),
        row.get("description", ""),
        row.get("gl_code", ""),
        row.get("flow_direction", ""),
        row.get("record_type", ""),
        row.get("currency", ""),
    )


def group_transactions(rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Collapse rows into unique classification groups.

    Returns:
        A list of group dicts, each with a representative context, the member
        transaction ids, and the date span the group covers.
    """
    groups: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    order: List[Tuple[str, ...]] = []
    for row in rows:
        jurisdictions = infer_jurisdictions(row)
        key = signature_of(row, jurisdictions)
        if key not in groups:
            groups[key] = {
                "context": build_context(row, jurisdictions),
                "jurisdictions": jurisdictions,
                "description": row.get("description", ""),
                "transaction_ids": [],
                "dates": [],
            }
            order.append(key)
        groups[key]["transaction_ids"].append(row.get("id", ""))
        groups[key]["dates"].append(row.get("date", ""))
    return [groups[key] for key in order]


# --- Deterministic rule matcher ----------------------------------------------

def _rule_keywords(rule: Dict[str, Any]) -> set[str]:
    """Extract salient lowercase keywords describing a rule."""
    applies = str(rule.get("parameters", {}).get("applies_to", ""))
    tokens = {tok for tok in applies.lower().replace("_", " ").split() if tok}
    for word in re.findall(r"[a-z]+", rule.get("summary", "").lower()):
        if len(word) > 4 and word not in STOPWORDS:
            tokens.add(word)
    return tokens - STOPWORDS


def _context_tokens(context: TransactionContext) -> set[str]:
    """Extract lowercase keyword tokens from a transaction context."""
    text = " ".join(
        str(part)
        for part in (context.transaction_text, context.record_type, context.flow_direction)
        if part
    )
    return {word for word in re.findall(r"[a-z]+", text.lower()) if len(word) > 3}


def _score_rule(rule_tokens: set[str], context_tokens: set[str]) -> float:
    """Score a rule against context tokens; returns a confidence in [0, 0.95]."""
    if not rule_tokens:
        return 0.0
    overlap = rule_tokens & context_tokens
    if not overlap:
        return 0.0
    coverage = len(overlap) / len(rule_tokens)
    return round(min(0.95, 0.30 + 0.65 * coverage), 3)


def classify_group_deterministic(group: Dict[str, Any], rules: List[Dict[str, Any]]) -> AILayerOutput:
    """Classify a group by deterministic keyword matching against the rule pack."""
    context: TransactionContext = group["context"]
    ctx_tokens = _context_tokens(context)
    scored = sorted(
        ((rule, _score_rule(_rule_keywords(rule), ctx_tokens)) for rule in rules),
        key=lambda pair: pair[1],
        reverse=True,
    )
    citations = [_citation(rule, score) for rule, score in scored[:MAX_REPORTED_RULES] if score > 0.0]
    top_confidence = citations[0].confidence if citations else 0.0
    abstain = top_confidence < MIN_MATCH_CONFIDENCE
    flow = FLOW_CLASSIFICATION_MAP.get(
        (context.flow_direction or "", context.record_type or ""), "UNCLASSIFIED"
    )
    return AILayerOutput(
        transaction_id=group["transaction_ids"][0],
        flow_classification=flow,
        candidate_jurisdictions=group["jurisdictions"],
        retrieved_rules=citations,
        evidence_requests=_evidence_requests(abstain, context),
        narrative_template=_narrative_template(flow, abstain),
        needs_human_review=abstain or top_confidence < MATERIAL_CONFIDENCE,
        abstain=abstain,
    )


def _citation(rule: Dict[str, Any], score: float) -> RuleCitation:
    """Build a RuleCitation from a rule pack entry and its match score."""
    applies = rule.get("parameters", {}).get("applies_to", "n/a")
    return RuleCitation(
        rule_id=rule["id"],
        source_citation=rule.get("source_citation", ""),
        as_of_date=rule.get("as_of_date", ""),
        confidence=score,
        reasoning=f"Transaction wording overlaps the rule scope '{applies}'.",
    )


def _evidence_requests(abstain: bool, context: TransactionContext) -> List[str]:
    """Build CPA evidence requests for a group."""
    if abstain:
        return [
            "No DIPN 21 source rule clearly applies to this flow. Confirm the underlying "
            "business activity (trading, services, commission, financing) and the place "
            "where the profit-generating operations are performed.",
        ]
    return [
        "Confirm where the operations giving rise to this flow were physically performed "
        "to validate the source determination.",
    ]


def _narrative_template(flow: str, abstain: bool) -> str:
    """Build a narrative template that defers all figures to the engine."""
    if abstain:
        return (
            "Classification could not be grounded in a DIPN 21 source rule for this "
            "{{engine:flow_count}} flow(s). Refer to a CPA for the operational facts."
        )
    return (
        f"This {flow.lower()} flow of {{{{engine:amount}}}} is assessed under the cited "
        "DIPN 21 source rule, with locality determined by the place of operations."
    )


# --- Qwen backend ------------------------------------------------------------

class _SingleContextGraphReader:
    """GraphReader returning one fixed context (one per group)."""

    def __init__(self, context: TransactionContext) -> None:
        self.context = context

    def get_transaction_context(self, transaction_id: str) -> TransactionContext:
        return self.context


def classify_group_qwen(group: Dict[str, Any], retriever: JsonRuleRetriever, model_name: str) -> AILayerOutput:
    """Classify a group via the local Qwen LLM through AILayerService."""
    from tributary.ai.qwen_client import QwenLocalClient
    from tributary.ai.service import AILayerService

    reader = _SingleContextGraphReader(group["context"])
    service = AILayerService(reader, retriever, QwenLocalClient(model_name=model_name))
    return service.classify_transaction(group["transaction_ids"][0])


# --- Conflict detection ------------------------------------------------------

def detect_conflict(output: AILayerOutput, params_by_id: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Flag regulatory conflicts among the material matched rules.

    Detects (a) apportionment disagreement between applicable rules and
    (b) ambiguous classification when two material rules score within a tie band.
    """
    material = [c for c in output.retrieved_rules if c.confidence >= MATERIAL_CONFIDENCE]
    if len(material) < 2:
        return {"has_conflict": False, "conflict_type": None, "details": "", "rule_ids": []}

    apportionment = {
        c.rule_id: params_by_id.get(c.rule_id, {}).get("apportionment_allowed")
        for c in material
    }
    distinct = {value for value in apportionment.values() if value is not None}
    if len(distinct) > 1:
        return {
            "has_conflict": True,
            "conflict_type": "apportionment_disagreement",
            "details": "Applicable rules disagree on whether profit apportionment is allowed.",
            "rule_ids": [c.rule_id for c in material if apportionment.get(c.rule_id) is not None],
        }

    if material[0].confidence - material[1].confidence <= CONFIDENCE_TIE_BAND:
        return {
            "has_conflict": True,
            "conflict_type": "ambiguous_classification",
            "details": "Two source rules match with near-equal confidence; scope is ambiguous.",
            "rule_ids": [material[0].rule_id, material[1].rule_id],
        }
    return {"has_conflict": False, "conflict_type": None, "details": "", "rule_ids": []}


# --- Report assembly ---------------------------------------------------------

def build_group_record(group: Dict[str, Any], output: AILayerOutput, conflict: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble the downstream JSON record for a classified group."""
    dates = [d for d in group["dates"] if d]
    return {
        "signature": {
            "description": group["description"],
            "gl_code": group["context"].gl_code,
            "flow_direction": group["context"].flow_direction,
            "record_type": group["context"].record_type,
            "jurisdictions": group["jurisdictions"],
        },
        "transaction_ids": group["transaction_ids"],
        "transaction_count": len(group["transaction_ids"]),
        "date_range": {"earliest": min(dates), "latest": max(dates)} if dates else None,
        "flow_classification": output.flow_classification,
        "candidate_jurisdictions": output.candidate_jurisdictions,
        "matched_rules": [c.model_dump() for c in output.retrieved_rules],
        "top_confidence": output.retrieved_rules[0].confidence if output.retrieved_rules else 0.0,
        "conflict": conflict,
        "abstain": output.abstain,
        "needs_human_review": output.needs_human_review,
        "evidence_requests": output.evidence_requests,
        "narrative_template": output.narrative_template,
    }


def assemble_report(
    input_path: Path,
    rules_path: Path,
    backend: str,
    rows: List[Dict[str, str]],
    group_records: List[Dict[str, Any]],
    rule_as_of: str,
) -> Dict[str, Any]:
    """Assemble the full output report with metadata and conflict summary."""
    conflicts = [
        {"signature": rec["signature"], "transaction_count": rec["transaction_count"], "conflict": rec["conflict"]}
        for rec in group_records
        if rec["conflict"]["has_conflict"]
    ]
    return {
        "metadata": {
            "source_file": str(input_path),
            "rule_pack": str(rules_path),
            "rule_pack_as_of": rule_as_of,
            "backend": backend,
            "total_transactions": len(rows),
            "unique_groups": len(group_records),
            "groups_needing_review": sum(1 for r in group_records if r["needs_human_review"]),
            "groups_with_conflict": len(conflicts),
            "note": (
                "Monetary amounts ignored by design. Output is regulation matching, "
                "confidence, and conflict judgment only; numeric values stay as engine "
                "placeholders for the deterministic engine downstream."
            ),
        },
        "classifications": group_records,
        "conflicts_summary": conflicts,
    }


# --- Orchestration -----------------------------------------------------------

def run(input_path: Path, rules_path: Path, output_path: Path, backend: str, qwen_model: str) -> None:
    """Classify all transactions and write the aggregated JSON report."""
    rules, params_by_id = load_rule_pack(rules_path)
    rule_as_of = rules[0].get("as_of_date", "") if rules else ""
    retriever = JsonRuleRetriever(rules)

    rows = read_transactions(input_path)
    groups = group_transactions(rows)
    print(f"Read {len(rows)} transactions -> {len(groups)} unique classification groups.")

    group_records: List[Dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        if backend == "qwen":
            output = classify_group_qwen(group, retriever, qwen_model)
        else:
            output = classify_group_deterministic(group, rules)
        conflict = detect_conflict(output, params_by_id)
        group_records.append(build_group_record(group, output, conflict))
        print(f"  [{index}/{len(groups)}] {group['context'].gl_code or '-'}: "
              f"{output.flow_classification}, top_conf="
              f"{group_records[-1]['top_confidence']}, conflict={conflict['has_conflict']}")

    report = assemble_report(input_path, rules_path, backend, rows, group_records, rule_as_of)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    print(f"Wrote AI layer report to: {output_path}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "-i", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--rules", "-r", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--backend", "-b", choices=["deterministic", "qwen"], default="deterministic")
    parser.add_argument("--qwen-model", default="Qwen/Qwen3-30B-A3B-Instruct-2507")
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")
    if not args.rules.exists():
        raise SystemExit(f"Rule pack not found: {args.rules}")

    run(args.input, args.rules, args.output, args.backend, args.qwen_model)


if __name__ == "__main__":
    main()
