"""
Example runner for the grounded AI layer over the graph snapshot.

Reads `graph/graph_snapshot.json`, and for every distinct balance-sheet line item
performs the grounded AI-layer analysis against the DIPN 21 rule pack
(`examples/Datasets/hk_dipn21_rules.json`, used as the RAG source):

  1. flow classification           (REVENUE / EXPENSE / INTERCOMPANY / CAPITAL / LOAN / UNCLASSIFIED)
  2. candidate-jurisdiction attribution  (the jurisdictions reporting the base)
  3. grounded rule retrieval       (mandatory citation + confidence + abstention)
  4. brief narrative drafting      (engine placeholders only -- never figures)

Design notes:
- Monetary amounts are intentionally IGNORED. The layer judges which regulation
  applies, with what confidence, and whether jurisdictions conflict.
- The snapshot reports the SAME company under three listings (HK / US / DE), so each
  line item is analysed ONCE and attributed to every jurisdiction that reports it;
  tax-base-relevant items reported by >= 2 jurisdictions are flagged as cross-border
  conflicts for the downstream brief.
- Backends:
    deterministic  -- fast, reproducible keyword matcher (offline default / fallback).
    qwen           -- the real grounded layer: local Qwen LLM via AILayerService.
                      The model is loaded ONCE and reused across all line items.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

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
ENTITY_LABEL = "Entity"
REPORTS_REL = "REPORTS"  # entity -> financial line item
RESIDENT_REL = "RESIDENT_IN"  # entity -> jurisdiction

# Deterministic matcher thresholds (the qwen backend sets these from its own reasoning).
MIN_MATCH_CONFIDENCE = 0.35  # below this the item abstains
REVIEW_CONFIDENCE = 0.50  # below this the item is flagged for human review
MATERIAL_CONFIDENCE = 0.40  # rules above this are weighed for rule-vs-rule conflict
CONFIDENCE_TIE_BAND = 0.10  # two material rules this close => ambiguous classification
MAX_REPORTED_RULES = 4

# Tokens too generic to carry matching signal.
STOPWORDS = frozenset(
    {
        "the", "and", "for", "are", "from", "with", "that", "this", "their", "which",
        "where", "without", "based", "place", "profits", "income", "revenue", "tax",
        "other", "into", "they", "have", "been", "made", "fees", "fee", "out", "all",
        "item", "items", "line", "sheet", "balance", "statement", "reported", "entity",
        "total", "current", "long", "term", "net",
    }
)

# Keyword groups mapping a balance-sheet line item to the engine flow enum.
# Checked in order; LOAN before CAPITAL so "Capital Lease Obligation" reads as debt.
FLOW_KEYWORD_GROUPS = (
    ("LOAN", ("debt", "loan", "lease", "borrow", "payable", "payables")),
    ("CAPITAL", ("equity", "stock", "share", "shares", "capital", "retained", "treasury", "minority")),
)

# Line items whose base can plausibly be claimed by more than one jurisdiction.
# Scopes cross-border conflict flagging to tax-relevant stocks only.
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

    Implements ``get_rule_summaries(jurisdictions)`` (RulePackLoaderProtocol). The pack
    is the single body of HK source-of-profits law every item is tested against, so all
    rules are returned for grounding regardless of the candidate jurisdictions.
    """

    def __init__(self, rules: List[Dict[str, Any]]) -> None:
        self.rules = rules

    def get_rule_summaries(self, jurisdictions: Iterable[str]) -> List[RuleSummary]:
        """Return every rule in the pack as a RuleSummary for prompt grounding."""
        return [
            RuleSummary(
                id=rule["id"],
                summary=rule.get("summary", ""),
                as_of_date=rule.get("as_of_date", ""),
                source_citation=rule.get("source_citation", ""),
            )
            for rule in self.rules
        ]


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
    """Map a balance-sheet line item name to the engine flow enum (deterministic)."""
    lowered = line_item.lower()
    for flow, keywords in FLOW_KEYWORD_GROUPS:
        if any(keyword in lowered for keyword in keywords):
            return flow
    return "UNCLASSIFIED"


def build_context(line_item: str, statement_type: str, jurisdictions: List[str]) -> TransactionContext:
    """Build a grounded TransactionContext for a line item (amounts excluded)."""
    text = (
        f"Balance-sheet line item '{line_item}' (statement: {statement_type}) of Lenovo "
        f"Group Limited, a multinational reported under listings in "
        f"{', '.join(jurisdictions)}. Monetary amounts are excluded by design: assess "
        f"only which DIPN 21 source-of-profits rule (if any) governs this item, with what "
        f"confidence, and which of these jurisdictions may tax it."
    )
    return TransactionContext(
        transaction_text=text,
        candidate_jurisdictions=jurisdictions,
        line_item=line_item,
        statement_type=statement_type,
    )


def group_line_items(
    line_items: List[Dict[str, Any]], node_jurisdiction: Dict[str, str]
) -> List[Dict[str, Any]]:
    """Collapse line items into one analysis group per distinct line item.

    Each group aggregates every jurisdiction (and node id) that reports the base, so the
    grounded layer analyses the item once and attributes it across jurisdictions.
    """
    accum: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for props in line_items:
        line_item = props.get("line_item", "")
        jurisdiction = jurisdiction_for(props, node_jurisdiction)
        if line_item not in accum:
            accum[line_item] = {
                "line_item": line_item,
                "statement_type": props.get("statement_type", ""),
                "currency": props.get("currency", ""),
                "node_ids_by_jurisdiction": defaultdict(list),
                "periods": set(),
            }
            order.append(line_item)
        record = accum[line_item]
        record["node_ids_by_jurisdiction"][jurisdiction].append(props.get("id", ""))
        record["periods"].add(props.get("period", ""))

    groups: List[Dict[str, Any]] = []
    for line_item in order:
        record = accum[line_item]
        jurisdictions = sorted(record["node_ids_by_jurisdiction"].keys())
        node_ids_by_jurisdiction = {j: record["node_ids_by_jurisdiction"][j] for j in jurisdictions}
        flat_ids = [nid for ids in node_ids_by_jurisdiction.values() for nid in ids]
        groups.append({
            "line_item": line_item,
            "statement_type": record["statement_type"],
            "currency": record["currency"],
            "jurisdictions": jurisdictions,
            "node_ids_by_jurisdiction": node_ids_by_jurisdiction,
            "rep_id": flat_ids[0] if flat_ids else line_item,
            "periods": sorted(p for p in record["periods"] if p),
            "context": build_context(line_item, record["statement_type"], jurisdictions),
        })
    return groups


# --- Deterministic rule matcher (offline backend / fallback) -----------------

def _rule_keywords(rule: Dict[str, Any]) -> set[str]:
    """Extract salient lowercase keywords describing a rule."""
    applies = str(rule.get("parameters", {}).get("applies_to", ""))
    tokens = {tok for tok in applies.lower().replace("_", " ").split() if tok}
    for word in re.findall(r"[a-z]+", rule.get("summary", "").lower()):
        if len(word) > 4 and word not in STOPWORDS:
            tokens.add(word)
    return tokens - STOPWORDS


def _line_item_tokens(line_item: str) -> set[str]:
    """Tokenize the line-item name only (keeps matching free of boilerplate)."""
    return {word for word in re.findall(r"[a-z]+", line_item.lower()) if len(word) > 3} - STOPWORDS


def _score_rule(rule_tokens: set[str], item_tokens: set[str]) -> float:
    """Score a rule against line-item tokens; returns a confidence in [0, 0.95].

    A single coincidental keyword stays below the match floor (it should abstain);
    a genuine match requires at least two overlapping terms.
    """
    if not rule_tokens:
        return 0.0
    overlap = rule_tokens & item_tokens
    if not overlap:
        return 0.0
    coverage = len(overlap) / len(rule_tokens)
    if len(overlap) == 1:
        return round(min(0.30, 0.20 + 0.10 * coverage), 3)
    return round(min(0.95, 0.45 + 0.45 * coverage), 3)


def classify_group_deterministic(group: Dict[str, Any], rules: List[Dict[str, Any]]) -> AILayerOutput:
    """Classify a line item by deterministic keyword matching against the rule pack."""
    item_tokens = _line_item_tokens(group["line_item"])
    scored = sorted(
        ((rule, _score_rule(_rule_keywords(rule), item_tokens)) for rule in rules),
        key=lambda pair: pair[1],
        reverse=True,
    )
    citations = [_citation(rule, score) for rule, score in scored[:MAX_REPORTED_RULES] if score > 0.0]
    top_confidence = citations[0].confidence if citations else 0.0
    abstain = top_confidence < MIN_MATCH_CONFIDENCE
    return AILayerOutput(
        transaction_id=group["rep_id"],
        flow_classification=classify_flow(group["line_item"]),
        candidate_jurisdictions=group["jurisdictions"],
        retrieved_rules=[] if abstain else citations,
        evidence_requests=_evidence_requests(abstain),
        narrative_template=_narrative_template(classify_flow(group["line_item"]), abstain),
        needs_human_review=abstain or top_confidence < REVIEW_CONFIDENCE,
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
    """Build CPA evidence requests for an item."""
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
            "No DIPN 21 source rule could be grounded for this line item across "
            "{{engine:period_count}} period(s); refer to a CPA for the operational facts."
        )
    return (
        f"This {flow.lower()} position of {{{{engine:amount}}}} is assessed under the cited "
        "DIPN 21 source rule, with locality determined by the place of operations."
    )


# --- Qwen backend (real grounded layer) --------------------------------------

class _SingleContextGraphReader:
    """GraphReader returning one fixed context (rebuilt per line item)."""

    def __init__(self, context: TransactionContext) -> None:
        self.context = context

    def get_transaction_context(self, transaction_id: str) -> TransactionContext:
        return self.context


def build_qwen_client(model_name: str) -> Any:
    """Load the local Qwen model ONCE for reuse across all line items."""
    from tributary.ai.qwen_client import QwenLocalClient

    print(f"Loading Qwen model '{model_name}' (one-time) ...", flush=True)
    return QwenLocalClient(model_name=model_name)


def classify_group_qwen(group: Dict[str, Any], retriever: JsonRuleRetriever, client: Any) -> AILayerOutput:
    """Classify a line item via the local Qwen LLM through AILayerService."""
    from tributary.ai.service import AILayerService

    reader = _SingleContextGraphReader(group["context"])
    service = AILayerService(reader, retriever, client)
    output = service.classify_transaction(group["rep_id"])
    if not output.candidate_jurisdictions:
        output.candidate_jurisdictions = group["jurisdictions"]
    return output


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


def cross_border_for_group(group: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the per-group cross-border conflict flag."""
    flagged = len(group["jurisdictions"]) >= 2 and is_tax_base_relevant(group["line_item"])
    return {
        "is_flagged": flagged,
        "jurisdictions": group["jurisdictions"] if flagged else [],
        "note": "Same tax-relevant base reported in multiple jurisdictions." if flagged else "",
    }


# --- Report assembly ---------------------------------------------------------

def build_group_record(
    group: Dict[str, Any],
    output: AILayerOutput,
    rule_conflict: Dict[str, Any],
    cross_border: Dict[str, Any],
) -> Dict[str, Any]:
    """Assemble the downstream JSON record for one analysed line item."""
    return {
        "line_item": group["line_item"],
        "statement_type": group["statement_type"],
        "currency": group["currency"],
        "reported_jurisdictions": group["jurisdictions"],
        "node_ids_by_jurisdiction": group["node_ids_by_jurisdiction"],
        "node_count": sum(len(ids) for ids in group["node_ids_by_jurisdiction"].values()),
        "periods": group["periods"],
        "flow_classification": output.flow_classification,
        "candidate_jurisdictions": output.candidate_jurisdictions,
        "retrieved_rules": [c.model_dump() for c in output.retrieved_rules],
        "top_confidence": output.retrieved_rules[0].confidence if output.retrieved_rules else 0.0,
        "abstain": output.abstain,
        "needs_human_review": output.needs_human_review,
        "rule_conflict": rule_conflict,
        "cross_border_conflict": cross_border,
        "evidence_requests": output.evidence_requests,
        "narrative_template": output.narrative_template,
    }


def summarize_cross_border(group_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate the flagged cross-border conflicts for the report header."""
    conflicts: List[Dict[str, Any]] = []
    for record in group_records:
        if not record["cross_border_conflict"]["is_flagged"]:
            continue
        conflicts.append({
            "line_item": record["line_item"],
            "jurisdictions": record["reported_jurisdictions"],
            "flow_classification": record["flow_classification"],
            "matched_rule_ids": [c["rule_id"] for c in record["retrieved_rules"]],
            "node_ids_by_jurisdiction": record["node_ids_by_jurisdiction"],
            "rationale": (
                "A tax-relevant base reported under multiple listings may be claimed by "
                "more than one jurisdiction; reconcile the source determination downstream."
            ),
        })
    return conflicts


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
            "total_line_item_nodes": line_item_count,
            "analysed_line_items": len(group_records),
            "jurisdictions": sorted({j for r in group_records for j in r["reported_jurisdictions"]}),
            "grounded_matches": sum(1 for r in group_records if not r["abstain"]),
            "items_needing_review": sum(1 for r in group_records if r["needs_human_review"]),
            "items_with_rule_conflict": sum(1 for r in group_records if r["rule_conflict"]["has_conflict"]),
            "cross_border_conflicts": len(cross_border),
            "note": (
                "Monetary amounts ignored by design. Output is regulation matching, "
                "confidence, abstention, and conflict judgment only; numeric values stay "
                "as engine placeholders for the deterministic engine downstream."
            ),
        },
        "classifications": group_records,
        "cross_border_conflicts": cross_border,
    }


# --- Orchestration -----------------------------------------------------------

def write_report(
    output_path: Path,
    input_path: Path,
    rules_path: Path,
    backend: str,
    line_item_count: int,
    group_records: List[Dict[str, Any]],
    rule_as_of: str,
) -> None:
    """Write the report to disk (called incrementally so progress is never lost)."""
    cross_border_summary = summarize_cross_border(group_records)
    report = assemble_report(
        input_path, rules_path, backend, line_item_count, group_records, cross_border_summary, rule_as_of
    )
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    tmp_path.replace(output_path)  # atomic swap so a kill never leaves a half-written file


def load_done_line_items(output_path: Path) -> Tuple[List[Dict[str, Any]], set[str]]:
    """Load already-classified records from an existing report (for --resume)."""
    if not output_path.exists():
        return [], set()
    with output_path.open("r", encoding="utf-8") as handle:
        existing = json.load(handle)
    records = existing.get("classifications", [])
    return records, {r["line_item"] for r in records}


def run(
    input_path: Path,
    rules_path: Path,
    output_path: Path,
    backend: str,
    qwen_model: str,
    limit: Optional[int],
    resume: bool,
) -> None:
    """Run the grounded AI layer over all line items, checkpointing after each one."""
    rules, params_by_id = load_rule_pack(rules_path)
    rule_as_of = rules[0].get("as_of_date", "") if rules else ""
    retriever = JsonRuleRetriever(rules)

    nodes, relationships = load_graph(input_path)
    node_jurisdiction = build_jurisdiction_index(relationships)
    line_items = extract_line_items(nodes)
    groups = group_line_items(line_items, node_jurisdiction)
    if limit:
        groups = groups[:limit]

    group_records, done = load_done_line_items(output_path) if resume else ([], set())
    pending = [g for g in groups if g["line_item"] not in done]
    print(f"Read {len(line_items)} line-item nodes -> {len(groups)} distinct line items "
          f"(backend={backend}); {len(done)} already done, {len(pending)} to do.", flush=True)

    client = build_qwen_client(qwen_model) if (backend == "qwen" and pending) else None

    for index, group in enumerate(pending, start=1):
        if backend == "qwen":
            output = classify_group_qwen(group, retriever, client)
        else:
            output = classify_group_deterministic(group, rules)
        rule_conflict = detect_rule_conflict(output, params_by_id)
        cross_border = cross_border_for_group(group)
        group_records.append(build_group_record(group, output, rule_conflict, cross_border))
        write_report(output_path, input_path, rules_path, backend, len(line_items), group_records, rule_as_of)
        print(f"  [{index}/{len(pending)}] {group['line_item']}: {output.flow_classification}, "
              f"abstain={output.abstain}, top_conf={group_records[-1]['top_confidence']}", flush=True)

    matched = sum(1 for r in group_records if not r["abstain"])
    flagged = sum(1 for r in group_records if r["cross_border_conflict"]["is_flagged"])
    print(f"Grounded a DIPN 21 rule for {matched}/{len(group_records)} line items; "
          f"flagged {flagged} cross-border conflicts.", flush=True)
    print(f"Wrote AI layer report to: {output_path}", flush=True)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "-i", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--rules", "-r", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--backend", "-b", choices=["deterministic", "qwen"], default="deterministic")
    parser.add_argument("--qwen-model", default="Qwen/Qwen3-30B-A3B-Instruct-2507")
    parser.add_argument("--limit", type=int, default=None, help="Analyse only the first N line items.")
    parser.add_argument("--resume", action="store_true", help="Skip line items already in the output file.")
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")
    if not args.rules.exists():
        raise SystemExit(f"Rule pack not found: {args.rules}")

    run(args.input, args.rules, args.output, args.backend, args.qwen_model, args.limit, args.resume)


if __name__ == "__main__":
    main()
