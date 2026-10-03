"""
anse/neo/core.py — Neo-AI Autonomous Terminal Assistant Engine for Xavuntu AI & GWAYA v3.

Integrates Vasco0x4/Neo-AI with:
1. Local open weights: Qwen 14B Doctoral Reasoner (TPU ReBAR) / Qwen 3.8 Quant via Ollama (http://127.0.0.1:11434).
2. GWAYA v3 System 1 Zero-Trust Command Approval & Adversarial Screening.
3. AttentionMatter Redis Long-Term Memory (LTM) context pruning & durable facts.
4. MCP 5-protocol dispatch: terminal, files, analyze, network, security.
5. Sovereign offline execution without external cloud tokens.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from anse.memory.redis_ltm import PrunedContextResult, RedisLongTermMemoryManager
from anse.neo.approval import ApprovalHandler, CommandApprovalResult
from anse.neo.protocols import MCPProtocol, ProtocolRegistry

logger = logging.getLogger("anse.neo.core")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [NEO-CORE] %(message)s")

DEFAULT_SYSTEM_PROMPT = """### Pre-Prompt for Neo (Xavuntu AI Sovereign Terminal Assistant)

#### 1. Role
You are Neo, an autonomous, highly capable Linux terminal AI assistant integrated into Xavuntu AI and GWAYA v3.
You run sovereignly on local open-weights models (Qwen 14B / 3.8B in TPU ReBAR memory).
Execute commands, inspect kernel subsystems, analyze hardware metrics, and respond concisely with technical precision.

#### 2. Machine Communication Protocol (MCP)
Always use MCP tags to interact with the Linux system:
- `<mcp:terminal>command</mcp:terminal>`: Execute bash shell commands (e.g., `<mcp:terminal>ls -la /var/log</mcp:terminal>`).
- `<mcp:files>read:/path/to/file</mcp:files>`: Read file content.
- `<mcp:files>write:/path/to/file content</mcp:files>`: Write file content.
- `<mcp:files>list:/path/to/dir</mcp:files>`: List files in directory.
- `<mcp:analyze></mcp:analyze>`: Complete CPU, RAM, GPU/TPU, disk, and load analysis.
- `<mcp:network>connections|interfaces|ping:host|scan:subnet</mcp:network>`: Network operations.
- `<mcp:security>users|ports|listening|shield</mcp:security>`: Security posture & KalCyberShield inspection.

#### 3. Execution Rules
- Announce commands clearly before the tag.
- Never use MCP tags when merely describing capabilities to the user.
- All mutating commands pass through GWAYA System 1 pre-screening and require user confirmation.
- Summarize command output concisely and extract key technical insights.
"""


@dataclass
class NeoConfig:
    """Configuration for Neo-AI sovereign runtime."""
    model: str = "gwaya-qwen:14b-t4"
    fallback_model: str = "gwaya-qwen:3.8-quant"
    ollama_url: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    require_approval: bool = True
    auto_approve_all: bool = False
    enable_redis_ltm: bool = True
    enable_gwaya_s1: bool = True
    max_context_tokens: int = 4096
    temperature: float = 0.7
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    redis_host: str = os.getenv("REDIS_HOST", "127.0.0.1")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    session_id: str = "xavuntu-neo"
    request_timeout_sec: float = 120.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NeoConfig:
        return cls(
            model=data.get("model", "gwaya-qwen:14b-t4"),
            fallback_model=data.get("fallback_model", "gwaya-qwen:3.8-quant"),
            ollama_url=data.get("ollama_url", os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")),
            require_approval=data.get("require_approval", True),
            auto_approve_all=data.get("auto_approve_all", False),
            enable_redis_ltm=data.get("enable_redis_ltm", True),
            enable_gwaya_s1=data.get("enable_gwaya_s1", True),
            max_context_tokens=int(data.get("max_context_tokens", 4096)),
            temperature=float(data.get("temperature", 0.7)),
            system_prompt=data.get("system_prompt", DEFAULT_SYSTEM_PROMPT),
            redis_host=data.get("redis_host", os.getenv("REDIS_HOST", "127.0.0.1")),
            redis_port=int(data.get("redis_port", 6379)),
            session_id=data.get("session_id", "xavuntu-neo"),
            request_timeout_sec=float(data.get("request_timeout_sec", 120.0)),
        )


class NeoAI:
    """
    Sovereign Neo-AI Engine with Ollama local inference, GWAYA v3 Zero-Trust,
    AttentionMatter Redis LTM context packing, and MCP Protocol Execution.
    """

    def __init__(self, config: Optional[NeoConfig] = None) -> None:
        self.config = config or NeoConfig()
        self.approval_handler = ApprovalHandler(
            require_approval=self.config.require_approval,
            auto_approve_all=self.config.auto_approve_all,
        )
        self.registry = ProtocolRegistry()
        self.mcp = MCPProtocol(self.registry)

        # Initialize Redis LTM
        self.memory_manager: Optional[RedisLongTermMemoryManager] = None
        if self.config.enable_redis_ltm:
            try:
                self.memory_manager = RedisLongTermMemoryManager(
                    redis_host=self.config.redis_host,
                    redis_port=self.config.redis_port,
                    max_context_tokens=self.config.max_context_tokens,
                )
                logger.info("AttentionMatter Redis LTM initialized for Neo-AI.")
            except Exception as e:
                logger.warning(f"Failed to initialize Redis LTM: {e}. Running without persistent memory.")

        self.history: List[Dict[str, str]] = []
        self._turn_counter = 0

    def check_ollama_status(self) -> Dict[str, Any]:
        """Check Ollama service status and enumerate available models."""
        url = f"{self.config.ollama_url.rstrip('/')}/api/tags"
        try:
            resp = requests.get(url, timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                return {
                    "online": True,
                    "url": self.config.ollama_url,
                    "models": models,
                    "active_model": self.config.model if self.config.model in models else (models[0] if models else "none"),
                }
            return {"online": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"online": False, "error": str(e), "url": self.config.ollama_url}

    def _get_active_model_name(self) -> str:
        """Determines best active model (preferred model, fallback, or any available)."""
        status = self.check_ollama_status()
        if not status.get("online"):
            return self.config.model

        available = status.get("models", [])
        if self.config.model in available:
            return self.config.model
        if self.config.fallback_model in available:
            return self.config.fallback_model
        if available:
            return available[0]
        return self.config.model

    def _build_context_prompt(self, query: str) -> Tuple[str, int]:
        """
        Retrieves durable facts and history from AttentionMatter Redis LTM,
        returning an enriched system prompt and tokens saved metric.
        """
        memories_text = ""
        tokens_saved = 0

        if self.memory_manager:
            try:
                pruned: PrunedContextResult = self.memory_manager.build_pruned_context(
                    session_id=self.config.session_id,
                    query=query,
                    token_budget=self.config.max_context_tokens,
                )
                tokens_saved = pruned.tokens_saved

                if pruned.selected_memories:
                    mem_block = "\n".join(f"- {m}" for m in pruned.selected_memories)
                    memories_text = f"\n\n### Persistent AttentionMatter LTM Facts:\n{mem_block}\n"
            except Exception as e:
                logger.debug(f"Context pruning fallback: {e}")

        # Add system context info (kernel, hostname, user)
        uname = os.uname()
        sys_context = f"\n\n<context>\nHost: {uname.nodename} | Kernel: {uname.release} | Arch: {uname.machine} | User: {os.environ.get('USER', 'xavkal')}\n</context>"

        full_prompt = self.config.system_prompt + memories_text + sys_context
        return full_prompt, tokens_saved

    def _call_ollama_chat(
        self,
        messages: List[Dict[str, str]],
        model_name: str,
        stream: bool = False,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Call Ollama /api/chat with streaming or blocking mode."""
        url = f"{self.config.ollama_url.rstrip('/')}/api/chat"
        payload = {
            "model": model_name,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": self.config.temperature,
                "num_ctx": self.config.max_context_tokens,
            },
        }

        full_text = ""
        try:
            if stream:
                with requests.post(url, json=payload, stream=True, timeout=self.config.request_timeout_sec) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines(decode_unicode=True):
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                            delta = chunk.get("message", {}).get("content", "")
                            if delta:
                                full_text += delta
                                if on_chunk:
                                    on_chunk(delta)
                        except json.JSONDecodeError:
                            continue
            else:
                resp = requests.post(url, json=payload, timeout=self.config.request_timeout_sec)
                resp.raise_for_status()
                data = resp.json()
                full_text = data.get("message", {}).get("content", "")
                if on_chunk and full_text:
                    on_chunk(full_text)

            return full_text
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama request failed: {e}")
            raise RuntimeError(f"Ollama connection error at {url}: {e}")

    def query(
        self,
        user_prompt: str,
        interactive: bool = True,
        stream: bool = False,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Executes a user request through Neo-AI:
        1. Context synthesis via AttentionMatter Redis LTM.
        2. Local Ollama LLM execution.
        3. MCP tag parsing & execution (with GWAYA System 1 pre-screening).
        4. Recursive synthesis for MCP command results.
        5. STM/LTM memory persistence.
        """
        t0 = time.perf_counter()
        self._turn_counter += 1
        active_model = self._get_active_model_name()

        # Build context
        system_content, tokens_saved = self._build_context_prompt(user_prompt)

        # Assemble messages
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_content}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": user_prompt})

        # Query LLM
        try:
            initial_reply = self._call_ollama_chat(
                messages=messages,
                model_name=active_model,
                stream=stream,
                on_chunk=on_chunk,
            )
        except Exception as e:
            # Fallback if preferred model fails and fallback is different
            if active_model != self.config.fallback_model:
                logger.warning(f"Model '{active_model}' failed: {e}. Retrying with '{self.config.fallback_model}'...")
                active_model = self.config.fallback_model
                initial_reply = self._call_ollama_chat(
                    messages=messages,
                    model_name=active_model,
                    stream=stream,
                    on_chunk=on_chunk,
                )
            else:
                raise

        # Process MCP tags
        mcp_results = self.mcp.process_response(
            initial_reply,
            approval_handler=self.approval_handler,
            interactive=interactive,
        )

        final_response = initial_reply
        follow_ups: List[str] = []

        for proto, res in mcp_results.items():
            if isinstance(res, dict) and res.get("executed", False):
                cmd = res.get("command", "")
                out = res.get("output", "")
                follow_ups.append(f"The <mcp:{proto}> command '{cmd}' executed with result:\n{out}")

        # Recursive follow-up synthesis if commands were executed
        if follow_ups:
            combined_follow_up = "\n\n".join(follow_ups)
            messages.append({"role": "assistant", "content": initial_reply})
            messages.append({"role": "user", "content": combined_follow_up})

            if stream and on_chunk:
                on_chunk("\n\n\033[1;36m[Neo-AI Synthesis]\033[0m\n")

            follow_up_reply = self._call_ollama_chat(
                messages=messages,
                model_name=active_model,
                stream=stream,
                on_chunk=on_chunk,
            )
            final_response = f"{initial_reply}\n\n{follow_up_reply}"

        # Update local history
        self.history.append({"role": "user", "content": user_prompt})
        self.history.append({"role": "assistant", "content": final_response})
        # Keep history to last 10 messages
        if len(self.history) > 10:
            self.history = self.history[-10:]

        # Record STM in Redis LTM
        if self.memory_manager:
            try:
                self.memory_manager.record_stm_turn(
                    session_id=self.config.session_id,
                    role="user",
                    text=user_prompt,
                    turn=self._turn_counter,
                )
                self.memory_manager.record_stm_turn(
                    session_id=self.config.session_id,
                    role="assistant",
                    text=final_response,
                    turn=self._turn_counter,
                )
            except Exception as e:
                logger.debug(f"Redis LTM record_stm_turn failed: {e}")

        duration_ms = (time.perf_counter() - t0) * 1000.0

        return {
            "query": user_prompt,
            "response": final_response,
            "mcp_results": mcp_results,
            "model": active_model,
            "tokens_saved": tokens_saved,
            "latency_ms": round(duration_ms, 2),
            "turn": self._turn_counter,
        }

    def reset_session(self) -> None:
        """Reset conversation history and turn counter."""
        self.history = []
        self._turn_counter = 0
