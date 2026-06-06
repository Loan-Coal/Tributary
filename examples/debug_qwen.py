from pathlib import Path
import json

from tributary.ai.qwen_client import QwenLocalClient
from tributary.prompts.loader import load_ai_classification_prompt

input_path = Path("examples/input_transaction.json")
payload = json.loads(input_path.read_text())
transaction_id = payload.get("transaction_id", "demo-transaction")
transaction_context = payload.get("transaction_context", {})
rule_summaries = payload.get("rule_summaries", [])

prompt_template = load_ai_classification_prompt()["system_prompt"]
serialized_context = "".join(
    [
        f"- {key}: {value}\n"
        for key, value in sorted(transaction_context.items())
        if key != "candidate_jurisdictions" and not isinstance(value, (int, float))
    ]
)
serialized_rules = "".join(
    [
        f"- id: {rule.get('id', '')}; as_of_date: {rule.get('as_of_date', '')}; "
        f"source_citation: {rule.get('source_citation', '')}; summary: {rule.get('summary', '')}\n"
        for rule in rule_summaries
    ]
)
prompt = (
    prompt_template
    .replace("{{transaction_id}}", transaction_id)
    .replace("{{transaction_context}}", serialized_context)
    .replace("{{rule_summaries}}", serialized_rules)
)

print("PROMPT:\n", prompt)

client = QwenLocalClient(model_name="Qwen/Qwen2.5-7B-Instruct")
messages = [{"role": "user", "content": prompt}]
text = client.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
model_inputs = client.tokenizer([text], return_tensors="pt").to(client.model.device)
generated_ids = client.model.generate(**model_inputs, max_new_tokens=800)
output_ids = generated_ids[0][len(model_inputs.input_ids[0]):].tolist()
content = client.tokenizer.decode(output_ids, skip_special_tokens=True)

print("\nCONTENT:\n", content)
