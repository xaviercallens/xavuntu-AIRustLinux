"""
API-backed System 1: drop-in alternative to HiddenStateExtractor for machines
without a GPU. Generates through an OpenAI-compatible endpoint (Ollama / vLLM)
and, when the server is Ollama, fetches the model's embedding of the response as
the hidden-state vector. If no embedding is available the record is empty, and
the harvester skips vector indexing for that trace.

Set ``ollama_native=True`` for Ollama: some Ollama versions (0.1.44 verified)
silently ignore ``seed`` and ``temperature`` on /v1/chat/completions, so every
"seed" returns the same sample. The native /api/chat endpoint honours both.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx
import torch

from anse.config import ModelConfig, get_config
from anse.core.encoder import HiddenStateRecord

logger = logging.getLogger(__name__)

_DISK2_CALL_LOGS = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/call_logs")


def _default_call_log() -> Path | None:
    """Every LLM call is persisted unless ANSE_CALL_LOG=off.

    Resolution order: ANSE_CALL_LOG env var, then the disk-2 call-log dir,
    then a repo-local fallback. The JSONL file is the durable record; Redis
    (see _log_call) is the searchable LTM layer on top of it.
    """
    import os

    env = os.environ.get("ANSE_CALL_LOG", "").strip()
    if env.lower() in {"off", "0", "none"}:
        return None
    if env:
        return Path(env)
    # Mocked calls from the test suite must never land in long-term memory.
    if "PYTEST_CURRENT_TEST" in os.environ:
        return None
    if _DISK2_CALL_LOGS.parent.exists():
        return _DISK2_CALL_LOGS / "llm_calls.jsonl"
    return Path(__file__).resolve().parent.parent.parent / "data" / "call_logs" / "llm_calls.jsonl"


class APIExtractor:
    def __init__(
        self,
        config: ModelConfig | None = None,
        client: httpx.Client | None = None,
        seed: int | None = None,
        timeout_s: float = 600.0,
        ollama_native: bool = False,
        model_name: str | None = None,
        call_log_path: str | Path | None = None,
    ) -> None:
        self.config = config or get_config().model
        self.api_model_name = model_name or self.config.api_model_name
        self.seed = seed
        self.ollama_native = ollama_native
        self._client = client or httpx.Client(timeout=timeout_s)
        self._base = self.config.api_base_url.rstrip("/")
        self._native_root = self._base[:-3] if self._base.endswith("/v1") else self._base
        self._call_log_path = Path(call_log_path) if call_log_path else _default_call_log()
        if self._call_log_path:
            self._call_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._redis = None  # lazily connected in _log_call

    def extract(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_new_tokens: int | None = None,
        temperature: float | None = None,
    ) -> tuple[str, HiddenStateRecord]:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        max_tokens = max_new_tokens or self.config.max_new_tokens
        temp = self.config.temperature if temperature is None else temperature
        if self.ollama_native:
            text, token_count = self._chat_native(messages, max_tokens, temp)
        else:
            text, token_count = self._chat_openai(messages, max_tokens, temp)

        if self._call_log_path:
            self._log_call(messages, text, token_count, max_tokens, temp)

        embedding = self._embed_code(text)
        record = HiddenStateRecord(
            hidden_state=torch.tensor([embedding], dtype=torch.float32),
            layer_indices=[-1],
            token_count=token_count,
            model_id=self.api_model_name,
            device="api",
            metadata={"prompt_length": len(prompt), "has_embedding": bool(embedding)},
        )
        return text, record

    def _chat_openai(
        self, messages: list[dict[str, str]], max_tokens: int, temperature: float
    ) -> tuple[str, int]:
        payload: dict[str, object] = {
            "model": self.api_model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if self.seed is not None:
            payload["seed"] = self.seed
        response = self._client.post(
            f"{self._base}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {self.config.api_key}"},
        )
        response.raise_for_status()
        body = response.json()
        text = body["choices"][0]["message"]["content"] or ""
        return text, int(body.get("usage", {}).get("completion_tokens", 0))

    def _chat_native(
        self, messages: list[dict[str, str]], max_tokens: int, temperature: float
    ) -> tuple[str, int]:
        options: dict[str, object] = {"temperature": temperature, "num_predict": max_tokens}
        if self.seed is not None:
            options["seed"] = self.seed
        response = self._client.post(
            f"{self._native_root}/api/chat",
            json={
                "model": self.api_model_name,
                "messages": messages,
                "stream": False,
                "options": options,
            },
        )
        response.raise_for_status()
        body = response.json()
        return body["message"]["content"] or "", int(body.get("eval_count", 0))

    def _embed_code(self, text: str) -> list[float]:
        """Embed only the code portion of the LLM response for JEPA.

        The JEPA world model must predict *execution* energy, so it needs
        code-semantic embeddings, not text-semantic ones. This method
        extracts the first Python code block from the response and embeds
        that alone. Falls back to the full text if no code block is found.
        """
        code_text = self._extract_code_for_embedding(text)
        return self._embed(code_text)

    @staticmethod
    def _extract_code_for_embedding(text: str) -> str:
        """Extract the first Python code block from a markdown response."""
        import re

        # Match ```python ... ``` or ``` ... ``` blocks
        pattern = r"```(?:python)?\s*\n(.*?)```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Fallback: if the entire response looks like code (no markdown), use it as-is
        return text

    def _embed(self, text: str) -> list[float]:
        if not text:
            return []
        try:
            response = self._client.post(
                f"{self._native_root}/api/embeddings",
                json={"model": self.api_model_name, "prompt": text},
            )
            response.raise_for_status()
            return [float(x) for x in response.json().get("embedding", [])]
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Embedding unavailable (%s); trace will not be vector-indexed.", exc)
            return []

    def _log_call(
        self,
        messages: list[dict[str, str]],
        output: str,
        token_count: int,
        max_tokens: int,
        temperature: float,
    ) -> None:
        if not self._call_log_path:
            return
        call_record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "model": self.api_model_name,
            "input": {"messages": messages, "max_tokens": max_tokens, "temperature": temperature},
            "output": {"text": output, "completion_tokens": token_count},
        }
        line = json.dumps(call_record)
        try:
            with open(self._call_log_path, "a") as f:
                f.write(line + "\n")
        except Exception as exc:
            logger.warning("Failed to log LLM call: %s", exc)
        # LTM layer: push to Redis so calls are queryable across sessions.
        # The JSONL above is the durable record; Redis failure must not break
        # generation, so this degrades to a warning.
        try:
            if self._redis is None:
                import os

                import redis

                self._redis = redis.Redis.from_url(
                    os.environ.get("ANSE_REDIS_URL", "redis://localhost:6379/0"),
                    socket_connect_timeout=2,
                )
            self._redis.lpush("anse:ltm:llm_calls", line)
        except Exception as exc:
            logger.warning("LLM call not pushed to Redis LTM: %s", exc)
