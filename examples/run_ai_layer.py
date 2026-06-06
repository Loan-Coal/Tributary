"""
Example runner for the Tributary AI layer over the graph snapshot.

Reads `graph/graph_snapshot.json`, classifies every `FinancialLineItem` node
against the DIPN 21 rule pack (`examples/Datasets/hk_dipn21_rules.json`) used as
the RAG source, and writes a single aggregated JSON report.

Design notes:
- Monetary amounts are intentionally IGNORED. The AI layer only judges which
  regulation applies, with what confidence, and whether rules / jurisdictions
  conflict. No figures are emitted (numeric slots stay as ``{{engine:...}}``
  placeholders for the deterministic engine downstream).
- Line items are deduplicated by classification signature (amount/period/node-id
  excluded) so the 900+ nodes collapse to one group per (jurisdiction, line_item);
  each group is classified once and mapped back to all its node ids and periods.
- Because the snapshot reports the SAME company under three listings (HK / US / DE),
  a cross-border pass flags tax-base-relevant line items claimed by >= 2
  jurisdictions -- the cross-border conflict signal for the downstream brief.
- Default backend is a deterministic rule matcher (instant, reproducible). Pass
  ``--backend qwen`` to route each unique group through the local Qwen LLM instead.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

# Ensure the `src/` layout is importable when run directly (no PYTHONPATH needed).
_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if _SRC_DIR.is_dir() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from tributary.ai.models import AILayerOutput, RuleCitation, RuleSummary, TransactionContext

# --- Configuration constants ------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "graph" / "graph_snapshot.json"
DEFAULT_RULES = REPO_ROOT / "examples" / "Datasets" / "hk_dipn21_rules.json"
DEFAULT_OUTPUT = REPO_ROOT / "examples" / "ai_layer_output.json"

LINE_ITEM_LABEL = "FinancialLineItem"
REPORTS_REL = "REPORTS"  # entity -> financial line item
RESIDENT_REL = "RESIDENT_IN"  # entity -> jurisdiction

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
        "item", "items", "line", "sheet", "balance", "statement", "reported", "entity",
    }
)

# Keyword groups mapping a balance-sheet line item to the engine flow enum.
# Checked in order; LOAN before CAPITAL so "Capital Lease Obligation" reads as debt.
FLOW_KEYWORD_GROUPS = (
    ("LOAN", ("debt", "loan", "lease", "borrow", "payable", "payables")),
    ("CAPITAL", ("equity", "stock", "share", "shares", "capital", "retained", "treasury", "minority")),
)

# Line items whose base can plausibly be claimed by more than one jurisdiction.
# Used to scope cross-border conflict flagging to tax-relevant stocks only.
TAX_BASE_KEYWORDS = frozenset(
    {"tax", "taxes", "deferred", "retained", "earnings", "profit", "goodwill",
     "equity", "investment", "investments", "invested"}
)


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


# --- Graph snapshot ingestion ------------------------------------------------

def load_graph(input_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load the graph snapshot JSON into (nodes, relationships)."""
    with input_path.open("r", encoding="utf-8") as handle:
        snapshot = json.load(handle)
    return snapshot.get("nodes", []), snapshot.get("relationships", [])


def build_jurisdiction_index(relationships: List[Dict[str, Any]]) -> Dict[str, str]:
    """Map each line-item node id to its reporting jurisdiction.

    Follows REPORTS (entity -> line item) then RESIDENT_IN (entity -> jurisdiction).
    """
    entity_jurisdiction = {
        rel["source"]: rel["target"]
        for rel in relationships
        if rel.get("type") == RESIDENT_REL
    }
    node_jurisdiction: Dict[str, str] = {}
    for rel in relationships:
        if rel.get("type") != REPORTS_REL:
            continue
        jurisdiction = entity_jurisdiction.get(rel.get("source"))
        if jurisdiction:
            node_jurisdiction[rel["target"]] = jurisdiction
    return node_jurisdiction


def extract_line_items(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return the properties of every FinancialLineItem node."""
    return [
        node.get("properties", {})
        for node in nodes
        if LINE_ITEM_LABEL in node.get("labels", [])
    ]


def jurisdiction_for(props: Dict[str, Any], node_jurisdiction: Dict[str, str]) -> str:
    """Resolve a line item's jurisdiction from the graph, falling back to its id."""
    direct = node_jurisdiction.get(props.get("id", ""))
    if direct:
        return direct
    blob = props.get("id", "").lower()
    for token, code in (("lenovo_hk", "HK"), ("lenovo_us", "US"), ("lenovo_de", "DE")):
        if token in blob:
            return code
    return "UNKNOWN"


def classify_flow(line_item: str) -> str:
    """Map a balance-sheet line item name to the engine flow enum."""
    lowered = line_item.lower()
    for flow, keywords in FLOW_KEYWORD_GROUPS:
        if any(keyword in lowered for keyword in keywords):
            return flow
    return "UNCLASSIFIED"


def build_context(props: Dict[str, Any], jurisdiction: str) -> TransactionContext:
    """Build a TransactionContext for a line item, excluding monetary amounts."""
    line_item = props.get("line_item", "")
    # Only the line-item's own wording should drive rule matching; boilerplate
    # field names (source / statement / ticker) are deliberately kept out of the text.
    text = f"Balance-sheet line item: {line_item}."
    return TransactionContext(
        transaction_text=text,
        candidate_jurisdictions=[jurisdiction],
        line_item=line_item,
        statement_type=props.get("statement_type", ""),
        currency=props.get("currency", ""),
        source=props.get("source", ""),
    )


def signature_of(props: Dict[str, Any], jurisdiction: str) -> Tuple[str, ...]:
    """Return the classification signature for a line item (amount/period/id excluded)."""
    return (
        jurisdiction,
        props.get("line_item", ""),
        props.get("statement_type", ""),
        props.get("currency", ""),
    )


def group_line_items(
    line_items: List[Dict[str, Any]], node_jurisdiction: Dict[str, str]
) -> List[Dict[str, Any]]:
    """Collapse line items into unique (jurisdiction, line_item) classification groups."""
    groups: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    order: List[Tuple[str, ...]] = []
    for props in line_items:
        jurisdiction = jurisdiction_for(props, node_jurisdiction)
        key = signature_of(props, jurisdiction)
        if key not in groups:
            groups[key] = {
                "context": build_context(props, jurisdiction),
                "jurisdiction": jurisdiction,
                "line_item": props.get("line_item", ""),
                "node_ids": [],
                "periods": [],
            }
            order.append(key)
        groups[key]["node_ids"].append(props.get("id", ""))
        groups[key]["periods"].append(props.get("period", ""))
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
    text = context.transaction_text or ""
    return {word for word in re.findall(r"[a-z]+", text.lower()) if len(word) > 3} - STOPWORDS


def _score_rule(rule_tokens: set[str], context_tokens: set[str]) -> float:
    """Score a rule against context tokens; returns a confidence in [0, 0.95].

    A single coincidental keyword stays below the match floor (it should abstain);
    a genuine match requires at least two overlapping terms.
    """
    if not rule_tokens:
        return 0.0
    overlap = rule_tokens & context_tokens
    if not overlap:
        return 0.0
    coverage = len(overlap) / len(rule_tokens)
    if len(overlap) == 1:
        return round(min(0.30, 0.20 + 0.10 * coverage), 3)
    return round(min(0.95, 0.45 + 0.45 * coverage), 3)


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
    flow = classify_flow(group["line_item"])
    return AILayerOutput(
        transaction_id=group["node_ids"][0],
        flow_classification=flow,
        candidate_jurisdictions=[group["jurisdiction"]],
        retrieved_rules=citations,
        evidence_requests=_evidence_requests(abstain),
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
        reasoning=f"Line-item wording overlaps the rule scope '{applies}'.",
    )


def _evidence_requests(abstain: bool) -> List[str]:
    """Build CPA evidence requests for a group."""
    if abstain:
        return [
            "No DIPN 21 source rule clearly applies to this balance-sheet line item. "
            "Confirm the underlying transactions (trading, services, financing, securities) "
            "and where the profit-generating operations were performed.",
        ]
    return [
        "Confirm where the operations giving rise to this balance reside to validate "
        "the source determination.",
    ]


def _narrative_template(flow: str, abstain: bool) -> str:
    """Build a narrative template that defers all figures to the engine."""
    if abstain:
        return (
            "Classification could not be grounded in a DIPN 21 source rule for this "
            "line item across {{engine:period_count}} period(s). Refer to a CPA."
        )
    return (
        f"This {flow.lower()} balance of {{{{engine:amount}}}} is assessed under the cited "
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
    return service.classify_transaction(group["node_ids"][0])


# --- Conflict detection ------------------------------------------------------

def detect_rule_conflict(output: AILayerOutput, params_by_id: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Flag regulatory conflicts among the material matched rules.

    Detects (a) apportionment disagreement between applicable rules and
    (b) ambiguous classification when two material rules score within a tie band.
    """
    material = [c for c in output.retrieved_rules if c.confidence >= MATERIAL_CONFIDENCE]
    if len(material) < 2:
        return _no_conflict()

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
    return _no_conflict()


def _no_conflict() -> Dict[str, Any]:
    """Return the canonical no-conflict record."""
    return {"has_conflict": False, "conflict_type": None, "details": "", "rule_ids": []}


def is_tax_base_relevant(line_item: str) -> bool:
    """Whether a line item represents a base that jurisdictions could overlap on."""
    tokens = set(re.findall(r"[a-z]+", line_item.lower()))
    return bool(tokens & TAX_BASE_KEYWORDS)


def detect_cross_border_conflicts(group_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flag tax-base-relevant line items reported by >= 2 jurisdictions.

    Mutates each participating group record's ``cross_border_conflict`` field and
    returns the aggregated cross-border conflict list.
    """
    by_line_item: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in group_records:
        by_line_item[record["signature"]["line_item"]].append(record)

    conflicts: List[Dict[str, Any]] = []
    for line_item, records in by_line_item.items():
        jurisdictions = sorted({r["signature"]["jurisdiction"] for r in records})
        if len(jurisdictions) < 2 or not is_tax_base_relevant(line_item):
            continue
        matched_rule_ids = sorted({c["rule_id"] for r in records for c in r["matched_rules"]})
        for record in records:
            others = [j for j in jurisdictions if j != record["signature"]["jurisdiction"]]
            record["cross_border_conflict"] = {
                "is_flagged": True,
                "also_reported_in": others,
                "note": "Same tax-relevant base reported in multiple jurisdictions.",
            }
        conflicts.append({
            "line_item": line_item,
            "jurisdictions": jurisdictions,
            "matched_rule_ids": matched_rule_ids,
            "node_ids_by_jurisdiction": {
                r["signature"]["jurisdiction"]: r["node_ids"] for r in records
            },
            "rationale": (
                "A tax-relevant base reported under multiple listings may be claimed by "
                "more than one jurisdiction; reconcile the source determination downstream."
            ),
        })
    return conflicts


# --- Report assembly ---------------------------------------------------------

def build_group_record(group: Dict[str, Any], output: AILayerOutput, rule_conflict: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble the downstream JSON record for a classified group."""
    periods = sorted(p for p in group["periods"] if p)
    return {
        "signature": {
            "jurisdiction": group["jurisdiction"],
            "line_item": group["line_item"],
            "statement_type": group["context"].statement_type,
            "currency": group["context"].currency,
        },
        "node_ids": group["node_ids"],
        "node_count": len(group["node_ids"]),
        "periods": periods,
        "flow_classification": output.flow_classification,
        "candidate_jurisdictions": output.candidate_jurisdictions,
        "matched_rules": [c.model_dump() for c in output.retrieved_rules],
        "top_confidence": output.retrieved_rules[0].confidence if output.retrieved_rules else 0.0,
        "rule_conflict": rule_conflict,
        "cross_border_conflict": {"is_flagged": False, "also_reported_in": [], "note": ""},
        "abstain": output.abstain,
        "needs_human_review": output.needs_human_review,
        "evidence_requests": output.evidence_requests,
        "narrative_template": output.narrative_template,
    }


def assemble_report(
    input_path: Path,
    rules_path: Path,
    backend: str,
    line_item_count: int,
    group_records: List[Dict[str, Any]],
    cross_border: List[Dict[str, Any]],
    rule_as_of: str,
) -> Dict[str, Any]:
    """Assemble the full output report with metadata and conflict summaries."""
    return {
        "metadata": {
            "source_file": str(input_path),
            "rule_pack": str(rules_path),
            "rule_pack_as_of": rule_as_of,
            "backend": backend,
            "total_line_items": line_item_count,
            "unique_groups": len(group_records),
            "jurisdictions": sorted({r["signature"]["jurisdiction"] for r in group_records}),
            "groups_needing_review": sum(1 for r in group_records if r["needs_human_review"]),
            "groups_with_rule_conflict": sum(1 for r in group_records if r["rule_conflict"]["has_conflict"]),
            "cross_border_conflicts": len(cross_border),
            "note": (
                "Monetary amounts ignored by design. Output is regulation matching, "
                "confidence, and conflict judgment only; numeric values stay as engine "
                "placeholders for the deterministic engine downstream."
            ),
        },
        "classifications": group_records,
        "cross_border_conflicts": cross_border,
    }


# --- Orchestration -----------------------------------------------------------

def run(input_path: Path, rules_path: Path, output_path: Path, backend: str, qwen_model: str) -> None:
    """Classify all line items and write the aggregated JSON report."""
    rules, params_by_id = load_rule_pack(rules_path)
    rule_as_of = rules[0].get("as_of_date", "") if rules else ""
    retriever = JsonRuleRetriever(rules)

    nodes, relationships = load_graph(input_path)
    node_jurisdiction = build_jurisdiction_index(relationships)
    line_items = extract_line_items(nodes)
    groups = group_line_items(line_items, node_jurisdiction)
    print(f"Read {len(line_items)} line items -> {len(groups)} unique (jurisdiction, line_item) groups.")

    group_records: List[Dict[str, Any]] = []
    for group in groups:
        if backend == "qwen":
            output = classify_group_qwen(group, retriever, qwen_model)
        else:
            output = classify_group_deterministic(group, rules)
        rule_conflict = detect_rule_conflict(output, params_by_id)
        group_records.append(build_group_record(group, output, rule_conflict))

    cross_border = detect_cross_border_conflicts(group_records)
    matched = sum(1 for r in group_records if not r["abstain"])
    print(f"Matched a DIPN 21 rule for {matched} groups; "
          f"flagged {len(cross_border)} cross-border conflicts.")

    report = assemble_report(
        input_path, rules_path, backend, len(line_items), group_records, cross_border, rule_as_of
    )
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
