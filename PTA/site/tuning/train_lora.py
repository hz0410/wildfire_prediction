"""Supervised LoRA tuning for grounded wildfire-report behavior."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--model", default="Models/Qwen3-14B"); p.add_argument("--data", default="site/tuning/fire_reports.jsonl"); p.add_argument("--output", default="Models/Qwen3-14B-fire-lora"); args = p.parse_args()
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(args.model, local_files_only=True, torch_dtype="auto", device_map="auto")
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM", target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
    rows = [json.loads(line) for line in Path(args.data).read_text().splitlines() if line.strip()]
    def tokenize(row):
        text = tokenizer.apply_chat_template(row["messages"], tokenize=False, add_generation_prompt=False, enable_thinking=False)
        encoded = tokenizer(text, truncation=True, max_length=4096); encoded["labels"] = encoded["input_ids"].copy(); return encoded
    dataset = Dataset.from_list(rows).map(tokenize, remove_columns=["messages"])
    trainer = Trainer(model=model, train_dataset=dataset, args=TrainingArguments(output_dir=args.output, num_train_epochs=3, per_device_train_batch_size=1, gradient_accumulation_steps=16, learning_rate=2e-4, logging_steps=5, save_strategy="epoch", bf16=True, gradient_checkpointing=True, report_to="none"))
    trainer.train(); model.save_pretrained(args.output); tokenizer.save_pretrained(args.output)
if __name__ == "__main__": main()
