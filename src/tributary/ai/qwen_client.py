"""
Module: qwen_client
Layer: ai
Purpose: Local Qwen model adapter for structured AI output.
Dependencies: json, re, typing, transformers, torch, tributary.common.errors, tributary.common.logging, tributary.ai.models
Used by: ai.service, examples
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

from tributary.common.errors import AIClientError
from tributary.common.logging import get_logger
from tributary.ai.models import AILayerOutput

logger = get_logger(__name__)


class QwenLocalClient:
    def __init__(self, model_name: str = "Qwen/Qwen3-30B-A3B-Instruct-2507") -> None:
        self.model_name = model_name
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        except Exception as exc:
            logger.error("Failed to load Qwen tokenizer", exc_info=exc)
            raise AIClientError("Failed to load Qwen tokenizer") from exc

        try:
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype="auto",
                device_map="auto",
                trust_remote_code=True,
            )
        except Exception as exc:
            logger.error("Failed to load Qwen model", exc_info=exc)
            raise AIClientError("Failed to load Qwen model") from exc

    def generate(self, prompt: str, max_tokens: int = 800) -> AILayerOutput:
        """Generate structured output from a local Qwen model."""
        try:
            messages = [{"role": "user", "content": prompt}]
            text = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            model_inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)
            generated_ids = self.model.generate(
                **model_inputs,
                max_new_tokens=max_tokens,
            )
            output_ids = generated_ids[0][len(model_inputs.input_ids[0]):].tolist()
            content = self.tokenizer.decode(output_ids, skip_special_tokens=True)
            payload = self._extract_json(content)
            normalized = self._normalize_payload(payload)
            return AILayerOutput.model_validate(normalized)
        except AIClientError:
            raise
        except Exception as exc:
            logger.error("Qwen local generation failed", exc_info=exc)
            raise AIClientError("Qwen local generation failed") from exc

    def _extract_json(self, content: str) -> Any:
        content = content.strip()
        fenced = re.search(r"```(?:json)?\n(.*)\n```", content, re.S)
        if fenced:
            content = fenced.group(1).strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1 or start >= end:
                logger.error("Failed to parse JSON from Qwen content", extra={"content": content})
                raise AIClientError("Qwen returned non-JSON output")
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError as exc:
                logger.error(
                    "Failed to parse extracted JSON from Qwen content",
                    exc_info=exc,
                    extra={"extracted": content[start : end + 1]},
                )
                raise AIClientError("Qwen returned invalid structured JSON") from exc

    def _normalize_payload(self, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise AIClientError("Qwen returned unexpected payload format")

        return {
            "transaction_id": str(payload.get("transaction_id", "")),
            "flow_classification": self._normalize_flow_classification(payload.get("flow_classification", "")),
            "candidate_jurisdictions": self._normalize_jurisdictions(payload.get("candidate_jurisdictions", [])),
            "retrieved_rules": self._normalize_rules(payload.get("retrieved_rules", [])),
            "evidence_requests": self._normalize_evidence_requests(payload.get("evidence_requests", [])),
            "narrative_template": str(payload.get("narrative_template", "")),
            "needs_human_review": bool(payload.get("needs_human_review", False)),
            "abstain": bool(payload.get("abstain", False)),
        }

    def _normalize_flow_classification(self, value: Any) -> str:
        mapping = {
            "revenue": "REVENUE",
            "expense": "EXPENSE",
            "intercompany": "INTERCOMPANY",
            "capital": "CAPITAL",
            "loan": "LOAN",
        }
        if isinstance(value, str):
            normalized = value.strip().lower()
            for keyword, category in mapping.items():
                if keyword in normalized:
                    return category
        return "UNCLASSIFIED"

    def _normalize_jurisdictions(self, value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        if isinstance(value, str):
            return [value]
        return []

    def _normalize_rules(self, rules: Any) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        if not isinstance(rules, list):
            return result
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            result.append(
                {
                    "rule_id": str(rule.get("rule_id", rule.get("id", ""))),
                    "source_citation": str(rule.get("source_citation", "")),
                    "as_of_date": str(rule.get("as_of_date", "")),
                    "confidence": float(rule.get("confidence", 0.5)) if rule.get("confidence") is not None else 0.5,
                    "reasoning": str(rule.get("reasoning", rule.get("comment", ""))) or "Rule referenced by AI output.",
                }
            )
        return result

    def _normalize_evidence_requests(self, requests: Any) -> List[str]:
        output: List[str] = []
        if isinstance(requests, list):
            for item in requests:
                if isinstance(item, str):
                    output.append(item)
                elif isinstance(item, dict):
                    if "request" in item:
                        output.append(str(item["request"]))
                    else:
                        output.append(json.dumps(item, ensure_ascii=False))
        return output
