"""Lazy, local Qwen inference with a strict evidence-grounding prompt."""
from __future__ import annotations
import json
from pathlib import Path
from threading import Lock
from typing import Any

SYSTEM_PROMPT = """You are a wildfire risk report writer. The supplied JSON is the complete evidence available to you. Treat the statistical model probability as the risk estimate; do not invent or recalculate a probability. Web-tool data may update the interpretation, but clearly distinguish observations, forecasts, alerts, and model estimates. Never claim that no fire will occur. Cite web evidence inline using its source title and URL. If a tool failed or the requested date is outside its coverage, state that briefly. Answer the user's question, then give: Risk assessment, Evidence, Uncertainty, and Practical actions. Keep the report under 450 words. This is a research aid, not an evacuation authority; direct urgent safety decisions to local officials."""

class QwenReporter:
    def __init__(self, model_path: Path, adapter_path: Path | None = None):
        self.model_path, self.adapter_path = model_path, adapter_path
        self.tokenizer = self.model = None
        self._lock = Lock()

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def _load(self) -> None:
        if self.loaded: return
        if not self.model_path.exists(): raise FileNotFoundError(f"Qwen model not found at {self.model_path}")
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("Install site/server/requirements.txt before starting the Qwen service") from exc
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(self.model_path, local_files_only=True, torch_dtype="auto", device_map="auto", low_cpu_mem_usage=True)
        if self.adapter_path:
            from peft import PeftModel
            self.model = PeftModel.from_pretrained(self.model, self.adapter_path)
        self.model.eval()

    def generate(self, evidence: dict[str, Any]) -> str:
        with self._lock:
            self._load()
            messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": json.dumps(evidence, ensure_ascii=False, indent=2)}]
            prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
            outputs = self.model.generate(**inputs, max_new_tokens=700, do_sample=True, temperature=0.7, top_p=0.8, top_k=20, repetition_penalty=1.05)
            return self.tokenizer.decode(outputs[0, inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
