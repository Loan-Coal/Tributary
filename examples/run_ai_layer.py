"""
Example runner for the Tributary AI layer using a fake Claude client.
"""
import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from tributary.ai.fake_client import FakeClaudeClient
from tributary.ai.models import RuleSummary, TransactionContext
from tributary.ai.qwen_client import QwenLocalClient
from tributary.ai.rag_retriever import RAGRetriever
from tributary.ai.service import AILayerService


class FileGraphReader:
    def __init__(self, transaction_context: TransactionContext):
        self.transaction_context = transaction_context

    def get_transaction_context(self, transaction_id: str):
        # Return the provided context; real implementation would query the graph.
        return self.transaction_context


class FileRuleLoader:
    def __init__(self, rule_summaries: List[RuleSummary]):
        self.rule_summaries = rule_summaries or []

    def get_rule_summaries(self, jurisdictions):
        # In this demo, ignore jurisdictions and return provided summaries.
        return self.rule_summaries


def run_from_file(input_path: Path, output_path: Path, backend: str, qwen_model: str, use_rag: bool = False) -> None:
    with input_path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    transaction_id = payload.get("transaction_id", "demo-transaction")
    transaction_context = TransactionContext.model_validate(payload.get("transaction_context", {}))
    rule_summaries = [RuleSummary.model_validate(item) for item in payload.get("rule_summaries", [])]

    graph_reader = FileGraphReader(transaction_context)
    # Default: file-based loader
    rule_loader = FileRuleLoader(rule_summaries)
    # If rules DB exists and user requested RAG, attempt to use the retriever
    rules_db_path = Path("examples/rules.db")
    if use_rag and rules_db_path.exists():
        rule_loader = RAGRetriever(rules_db_path)
    if backend == "qwen":
        llm_client = QwenLocalClient(model_name=qwen_model)
    else:
        llm_client = FakeClaudeClient()
    service = AILayerService(graph_reader, rule_loader, llm_client)

    output = service.classify_transaction(transaction_id)

    # Write output JSON to file
    with output_path.open("w", encoding="utf-8") as outfh:
        outfh.write(output.model_dump_json(indent=2))

    print(f"Wrote AI output to: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", default="examples/input_transaction.json")
    parser.add_argument("--output", "-o", default="examples/output_transaction.json")
    parser.add_argument("--backend", "-b", choices=["fake", "qwen"], default="fake")
    parser.add_argument("--use-rag", action="store_true", help="Use local RAG retriever against examples/rules.db if available")
    parser.add_argument(
        "--qwen-model",
        default="Qwen/Qwen3-30B-A3B-Instruct-2507",
        help="Qwen model name or local path for the local LLM backend.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    # Propagate the --use-rag flag into the input payload for the demo runner
    payload = {}
    run_from_file(input_path, output_path, args.backend, args.qwen_model, use_rag=args.use_rag)


if __name__ == "__main__":
    main()
