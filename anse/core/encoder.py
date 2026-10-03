"""
Hidden-state extractor for LLM backbone.

Formal Lean 4 Specification:
-----------------------------
See `formal/ANSE/JEPA.lean`:
  abbrev HiddenState (d : ℕ) := EuclideanSpace ℝ (Fin d)
where d = 4096 for Qwen2.5-Coder-7B.

In Phase 1, the LLM backbone acts as the System 1 perceptual engine.
We extract the internal activations (hidden states) of the model alongside
its generated textual output, grounding the neuro-symbolic bridge:
  (prompt) ↦ (code, hidden_state)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import torch

from anse.config import ModelConfig, get_config

logger = logging.getLogger(__name__)


# ─── Record Dataclass ────────────────────────────────────────────────────────


@dataclass
class HiddenStateRecord:
    """
    Container for extracted neural representations from the LLM backbone.

    Corresponds to Lean 4: `ANSE.JEPA.HiddenState (d : ℕ)` where `d = 4096`.
    """

    hidden_state: torch.Tensor
    """Tensor of shape [1, hidden_dim] representing the last generated token's top hidden state."""

    layer_indices: list[int]
    """Indices of layers captured (e.g. [-1] or [-1, -2, -3, -4])."""

    token_count: int
    """Number of tokens generated in this step."""

    model_id: str
    """Model identifier (e.g. 'Qwen/Qwen2.5-Coder-7B-Instruct')."""

    device: str
    """Execution device ('cuda', 'cpu', 'mps', or 'mock')."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Optional metadata (prompt length, generation params, etc.)."""

    def to_embedding(self) -> list[float]:
        """Convert hidden state to a 1D float list for vector database storage."""
        flat = self.hidden_state.detach().cpu().flatten().to(torch.float32)
        return flat.tolist()


# ─── Extractor ───────────────────────────────────────────────────────────────


class HiddenStateExtractor:
    """
    Extracts code text and residual hidden states from the causal language model.

    Implements the perceptual mapping in ANSE:
      Prompt ↦ (GeneratedCode, HiddenStateRecord)
    """

    def __init__(
        self,
        config: ModelConfig | None = None,
        mock_mode: bool = False,
    ) -> None:
        self.config = config or get_config().model
        self.mock_mode = mock_mode
        self._model: Any = None
        self._tokenizer: Any = None
        self._device = self._resolve_device()

    def _resolve_device(self) -> str:
        if self.mock_mode:
            return "cpu"
        if self.config.device != "auto":
            return self.config.device
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def _load_model_if_needed(self) -> None:
        """Lazy-load HuggingFace transformers model and tokenizer."""
        if self.mock_mode or self._model is not None:
            return

        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as err:
            raise ImportError(
                "transformers package is required for real model extraction. "
                "Install it with `pip install transformers` or use mock_mode=True."
            ) from err

        logger.info("Loading tokenizer for %s ...", self.config.model_id)
        self._tokenizer = AutoTokenizer.from_pretrained(  # nosec B615  # type: ignore
            self.config.model_id,
            trust_remote_code=True,
            revision="main",
        )

        logger.info(
            "Loading model %s on %s (4bit=%s) ...",
            self.config.model_id,
            self.config.device,
            self.config.load_in_4bit,
        )

        load_kwargs: dict[str, Any] = {
            "device_map": self.config.device,
            "trust_remote_code": True,
        }
        if self.config.load_in_4bit:
            load_kwargs["load_in_4bit"] = True
        else:
            load_kwargs["torch_dtype"] = torch.float32

        self._model = AutoModelForCausalLM.from_pretrained(  # nosec B615  # type: ignore
            self.config.model_id,
            **load_kwargs,
            revision="main",
        )

        if not self.config.load_in_4bit and self.config.device != "auto":
            self._model.to(self._device)  # type: ignore

        self._model.eval()  # type: ignore

    def _format_prompt(self, prompt: str, system_prompt: str | None) -> str:
        if hasattr(self._tokenizer, "apply_chat_template") and self._tokenizer.chat_template:  # type: ignore
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            return self._tokenizer.apply_chat_template(  # type: ignore
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        if system_prompt:
            return f"System: {system_prompt}\n\nUser: {prompt}\n\nAssistant:"
        return f"User: {prompt}\n\nAssistant:"

    def _build_gen_kwargs(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor | None,
        max_tokens: int,
        temp: float,
    ) -> dict[str, Any]:
        gen_kwargs: dict[str, Any] = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "max_new_tokens": max_tokens,
            "output_hidden_states": True,
            "return_dict_in_generate": True,
            "pad_token_id": self._tokenizer.eos_token_id or self._tokenizer.pad_token_id,  # type: ignore
        }
        if temp > 0.0:
            gen_kwargs["do_sample"] = True
            gen_kwargs["temperature"] = temp
        else:
            gen_kwargs["do_sample"] = False
        return gen_kwargs

    def extract(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_new_tokens: int | None = None,
        temperature: float | None = None,
    ) -> tuple[str, HiddenStateRecord]:
        """
        Run inference on *prompt* and extract both the text response and the
        last-layer hidden state tensor.

        Returns:
            (response_text, hidden_state_record)
        """
        max_tokens = max_new_tokens or self.config.max_new_tokens
        temp = temperature if temperature is not None else self.config.temperature

        if self.mock_mode:
            return self._mock_extract(prompt, max_tokens)

        self._load_model_if_needed()

        formatted_prompt = self._format_prompt(prompt, system_prompt)
        inputs = self._tokenizer(formatted_prompt, return_tensors="pt")  # type: ignore
        input_ids = inputs["input_ids"].to(self._model.device)  # type: ignore
        attention_mask = inputs.get("attention_mask")
        if attention_mask is not None:
            attention_mask = attention_mask.to(self._model.device)  # type: ignore

        gen_kwargs = self._build_gen_kwargs(input_ids, attention_mask, max_tokens, temp)

        with torch.no_grad():
            outputs = self._model.generate(**gen_kwargs)  # type: ignore

        # Decode generated text (omitting prompt prefix)
        gen_tokens = outputs.sequences[0, input_ids.shape[-1] :]
        response_text = self._tokenizer.decode(gen_tokens, skip_special_tokens=True)  # type: ignore

        # Extract hidden state: outputs.hidden_states is a tuple of generation steps
        # outputs.hidden_states[-1] is the tuple of layer hidden states at the last generated token
        # outputs.hidden_states[-1][-1] has shape [batch_size, 1, hidden_dim]
        last_step_layers = outputs.hidden_states[-1]
        last_layer_state = last_step_layers[-1][:, -1, :]  # shape: [1, hidden_dim]

        record = HiddenStateRecord(
            hidden_state=last_layer_state.detach().cpu(),
            layer_indices=[-1],
            token_count=len(gen_tokens),
            model_id=self.config.model_id,
            device=str(self._model.device),  # type: ignore
            metadata={"prompt_length": len(prompt)},
        )

        return response_text, record

    def _mock_extract(
        self,
        prompt: str,
        max_tokens: int,
    ) -> tuple[str, HiddenStateRecord]:
        """Deterministic mock extraction for fast local testing and CI."""
        # Check if the prompt suggests a specific mock output
        code_response = (
            "```python\n"
            "def solution():\n"
            "    return True\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    assert solution() is True\n"
            "    print('OK')\n"
            "```"
        )

        # Generate synthetic deterministic hidden state of shape [1, hidden_dim]
        # Use prompt hash to make it content-dependent
        prompt_hash = sum(ord(c) for c in prompt) % 10000
        torch.manual_seed(prompt_hash)
        synthetic_state = torch.randn(1, self.config.hidden_dim, dtype=torch.float32)

        record = HiddenStateRecord(
            hidden_state=synthetic_state,
            layer_indices=[-1],
            token_count=32,
            model_id=f"mock-{self.config.model_id}",
            device="mock",
            metadata={"mock": True, "prompt_hash": prompt_hash},
        )

        return code_response, record
