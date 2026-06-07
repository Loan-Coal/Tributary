"""
Module: qwen_client
Layer: ai
Purpose: Local Qwen model adapter for structured AI output.
Dependencies: json, re, typing, transformers, torch, bitsandbytes,
              tributary.common.errors, tributary.common.logging, tributary.ai.models
Used by: ai.service, examples
"""
from __future__ import annotations

import json
import re
from typing import Any

from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
from tributary.ai.models import AILayerOutput
from tributary.common.errors import AIClientError
from tributary.common.logging import get_logger

logger = get_logger(__name__)

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    _TRANSFORMERS_AVAILABLE = True
except ImportError:
    _TRANSFORMERS_AVAILABLE = False


class QwenLocalClient:
    def __init__(self, model_name: str = "Qwen/Qwen3-30B-A3B-Instruct-2507") -> None:
        self.model_name = model_name
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        except Exception as exc:
            logger.error("Failed to load Qwen tokenizer", exc_info=exc)
            raise AIClientError("Failed to load Qwen tokenizer") from exc

        try:
            # 4-bit quantization: reduces VRAM from ~60 GB to ~15 GB for the 30B model,
            # making it comfortably runnable on a single A100 (80 GB) or even A6000.
            quant_config: Optional[BitsAndBytesConfig] = None
            if use_4bit:
                quant_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.bfloat16,
                    bnb_4bit_use_double_quant=True,
                )
                print("Loading Qwen model with 4-bit NF4 quantization (~15 GB VRAM) ...", flush=True)
            else:
                print("Loading Qwen model in bfloat16 (~60 GB VRAM) ...", flush=True)

            try:
                self.model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    dtype=torch.bfloat16 if not use_4bit else None,
                    quantization_config=quant_config,
                    device_map="auto",
                    trust_remote_code=True,
                )
            except Exception as exc:
                # Surface the real error so the user can diagnose it.
                print(f"[ERROR] Model loading failed: {type(exc).__name__}: {exc}", flush=True)
                if use_4bit:
                    # Automatically fall back to bfloat16 if 4-bit init fails
                    # (e.g. bitsandbytes CUDA kernel mismatch on this driver version).
                    print("[WARN] 4-bit loading failed — retrying in bfloat16 (needs ~60 GB VRAM).", flush=True)
                    self.model = AutoModelForCausalLM.from_pretrained(
                        model_name,
                        dtype=torch.bfloat16,
                        device_map="auto",
                        trust_remote_code=True,
                    )
                else:
                    raise
        except Exception as exc:
            logger.error("Failed to load Qwen model", exc_info=exc)
            raise AIClientError(f"Failed to load Qwen model: {type(exc).__name__}: {exc}") from exc


    def generate(self, prompt: str, max_tokens: int = 1200) -> AILayerOutput:
        """Generate structured output from a local Qwen model.

        max_tokens is set to 1200 (up from 800) to accommodate multi-rule outputs
        with taxing_jurisdiction fields across HK/US/DE/OECD rule packs.
        """
        try:
            messages = [{"role": "user", "content": prompt}]
            # enable_thinking=False: suppresses Qwen3's internal chain-of-thought
            # so the model outputs clean JSON directly without a <think>...</think> block.
            text = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
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
                raise AIClientError("Qwen returned non-JSON output") from None
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError as exc:
                logger.error(
                    "Failed to parse extracted JSON from Qwen content",
                    exc_info=exc,
                    extra={"extracted": content[start : end + 1]},
                )
                raise AIClientError("Qwen returned invalid structured JSON") from exc

    def _normalize_payload(self, payload: Any) -> dict[str, Any]:
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

    def _normalize_jurisdictions(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        if isinstance(value, str):
            return [value]
        return []

    def _normalize_rules(self, rules: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
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
                    "taxing_jurisdiction": str(rule.get("taxing_jurisdiction", "")),
                    "reasoning": str(rule.get("reasoning", rule.get("comment", ""))) or "Rule referenced by AI output.",
                }
            )
        return result

    def _normalize_evidence_requests(self, requests: Any) -> list[str]:
        output: list[str] = []
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
