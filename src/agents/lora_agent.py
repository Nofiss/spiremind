from __future__ import annotations

from typing import Optional

from loguru import logger
from models.state import GameState
from agents.heuristics import heuristic_action
from utils.command_policy import normalize_and_validate_command
from utils.prompt import build_combat_prompt


class LoraAgent:
    def __init__(
        self,
        model_path: str = "spiremind_lora_model",
        max_new_tokens: int = 64,
        chat_template: str = "llama-3",
        max_seq_length: int = 2048,
    ):
        self.model_path = model_path
        self.max_new_tokens = max_new_tokens
        self.chat_template = chat_template
        self.max_seq_length = max_seq_length
        self._load_model()

    def _load_model(self) -> None:
        try:
            import torch
            from unsloth import FastLanguageModel, get_chat_template
        except Exception as exc:
            raise RuntimeError("Unsloth is required for LoraAgent") from exc

        self._torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.device == "cpu":
            logger.warning("LoraAgent running on CPU; inference will be slow")

        load_in_4bit = torch.cuda.is_available()
        self.model, self.tokenizer = FastLanguageModel.from_pretrained(
            model_name=self.model_path,
            max_seq_length=self.max_seq_length,
            dtype=None,
            load_in_4bit=load_in_4bit,
        )
        self.tokenizer = get_chat_template(
            self.tokenizer,
            chat_template=self.chat_template,
        )
        FastLanguageModel.for_inference(self.model)
        if self.device == "cuda":
            self.model.to("cuda")

    def build_prompt(self, state: GameState) -> str:
        return build_combat_prompt(state)

    def sanitize_command(self, raw_cmd: Optional[str], state: GameState) -> str:
        normalized = normalize_and_validate_command(raw_cmd or "", state)
        if normalized is None:
            return "end" if getattr(state, "in_game", False) else "state"
        return normalized

    def _extract_response(self, text: str) -> str:
        if "<|start_header_id|>assistant" in text:
            text = text.split("<|start_header_id|>assistant", 1)[1]
            if "<|end_header_id|>" in text:
                text = text.split("<|end_header_id|>", 1)[1]
        if "<|eot_id|>" in text:
            text = text.split("<|eot_id|>", 1)[0]
        return text.strip()

    def _generate_action(self, prompt: str) -> Optional[str]:
        messages = [
            {
                "role": "system",
                "content": "You are a Slay the Spire expert bot. Output only valid game commands.",
            },
            {"role": "user", "content": prompt},
        ]
        inputs = self.tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        )
        if self.device == "cuda":
            inputs = inputs.to("cuda")

        with self._torch.no_grad():
            outputs = self.model.generate(
                input_ids=inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
            )
        text = self.tokenizer.decode(outputs[0], skip_special_tokens=False)
        return self._extract_response(text)

    def think(self, state: GameState) -> str:
        if state and state.ready_for_command:
            h = heuristic_action(state)
            if h:
                return self.sanitize_command(h, state)

        prompt = self.build_prompt(state)
        try:
            raw_action = self._generate_action(prompt)
            final_action = self.sanitize_command(raw_action, state)
            if raw_action and final_action != raw_action.strip().lower():
                logger.info(f"LoraAgent: '{raw_action}' -> '{final_action}'")
            return final_action
        except Exception as exc:
            logger.error(f"LoraAgent error: {exc}")
            return "end"
