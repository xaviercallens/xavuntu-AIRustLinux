"""
anse/gateway/openai_proxy.py — OpenAI-Compatible API Gateway for Xavuntu AI & Ollama TPU.

Provides standard OpenAI REST endpoints (/v1/models, /v1/chat/completions, /v1/completions):
- Compatible with Open WebUI, Continue.dev (VS Code), Aider (CLI), Msty, and Chatbox.
- Routes requests to local Ollama (http://127.0.0.1:11434) with TPU ReBAR acceleration.
- Pre-screens queries and code via GWAYA System 1 Zero-Trust Guard.
- Augments context with AttentionMatter Redis Long-Term Memory.
- Supports both JSON batch requests and Server-Sent Events (SSE) token streaming.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

import requests
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from anse.memory.redis_ltm import RedisLongTermMemoryManager
from anse.neo.approval import ApprovalHandler

logger = logging.getLogger("anse.gateway.openai_proxy")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [OPENAI-PROXY] %(message)s")

router = APIRouter(prefix="/v1", tags=["OpenAI Compatible Gateway"])

OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("GWAYA_MODEL", "gwaya-qwen:14b-t4")

approval_handler = ApprovalHandler(require_approval=False, auto_approve_all=True)
try:
    memory_manager: Optional[RedisLongTermMemoryManager] = RedisLongTermMemoryManager()
except Exception as e:
    logger.debug(f"Redis LTM not initialized in gateway: {e}")
    memory_manager = None


# ---------------------------------------------------------------------------
# Request & Response Models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str = DEFAULT_MODEL
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.95
    n: Optional[int] = 1
    stream: Optional[bool] = False
    stop: Optional[Any] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = 0.0
    frequency_penalty: Optional[float] = 0.0


class CompletionRequest(BaseModel):
    model: str = DEFAULT_MODEL
    prompt: Any  # string or list of strings
    max_tokens: Optional[int] = 256
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False
    stop: Optional[Any] = None


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def fetch_ollama_models() -> List[Dict[str, Any]]:
    """Retrieve active models from local Ollama service."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3.0)
        if resp.status_code == 200:
            models_data = resp.json().get("models", [])
            out = []
            for m in models_data:
                name = m.get("name", "")
                created = int(time.time())
                out.append({
                    "id": name,
                    "object": "model",
                    "created": created,
                    "owned_by": "xavuntu-tpu",
                    "permission": [],
                    "root": name,
                    "parent": None,
                })
            return out
    except Exception as e:
        logger.debug(f"Ollama tags fetch error: {e}")

    # Fallback default models
    return [
        {"id": "gwaya-qwen:14b-t4", "object": "model", "created": int(time.time()), "owned_by": "xavuntu-tpu"},
        {"id": "gwaya-qwen:3.8-quant", "object": "model", "created": int(time.time()), "owned_by": "xavuntu-tpu"},
        {"id": "qwen2.5-coder:1.5b", "object": "model", "created": int(time.time()), "owned_by": "xavuntu-tpu"},
    ]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models() -> Dict[str, Any]:
    """OpenAI standard GET /v1/models endpoint."""
    models = fetch_ollama_models()
    return {"object": "list", "data": models}


@router.get("/models/{model_id:path}")
async def retrieve_model(model_id: str) -> Dict[str, Any]:
    """OpenAI standard GET /v1/models/{model_id} endpoint."""
    return {
        "id": model_id,
        "object": "model",
        "created": int(time.time()),
        "owned_by": "xavuntu-tpu",
    }


@router.post("/chat/completions")
async def create_chat_completion(req: ChatCompletionRequest) -> Response:
    """
    OpenAI standard POST /v1/chat/completions endpoint.
    Handles streaming and non-streaming inference, System 1 security pre-screening,
    and AttentionMatter Redis LTM context enrichment.
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created_time = int(time.time())

    # 1. System 1 Pre-screening on the latest user message
    last_user_msg = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
    if last_user_msg:
        is_safe, risk, heuristic = approval_handler.screen_command(last_user_msg)
        if not is_safe:
            logger.warning(f"GWAYA System 1 rejected adversarial payload: {heuristic}")
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "message": f"Blocked by GWAYA System 1 Guard: Detected {heuristic}",
                        "type": "invalid_request_error",
                        "param": "messages",
                        "code": "critical_adversarial_blocked",
                    }
                },
            )

    # 2. Redis LTM Context Enrichment
    system_addon = ""
    if memory_manager and last_user_msg:
        try:
            pruned = memory_manager.build_pruned_context(
                session_id="openai_gateway",
                query=last_user_msg,
                token_budget=2048,
            )
            if pruned.selected_memories:
                mems = "\n".join(f"- {m}" for m in pruned.selected_memories)
                system_addon = f"\n\n[AttentionMatter Redis LTM Facts]:\n{mems}"
        except Exception as e:
            logger.debug(f"Memory augmentation exception: {e}")

    # Prepare Ollama chat messages
    ollama_messages = []
    has_system = False
    for m in req.messages:
        if m.role == "system":
            has_system = True
            content = m.content + system_addon
            ollama_messages.append({"role": "system", "content": content})
        else:
            ollama_messages.append({"role": m.role, "content": m.content})

    if not has_system and system_addon:
        ollama_messages.insert(0, {"role": "system", "content": "You are a sovereign AI assistant on Xavuntu Linux." + system_addon})

    ollama_payload = {
        "model": req.model,
        "messages": ollama_messages,
        "stream": req.stream,
        "options": {
            "temperature": req.temperature or 0.7,
            "top_p": req.top_p or 0.95,
        },
    }

    ollama_url = f"{OLLAMA_BASE_URL}/api/chat"

    # Streaming Response
    if req.stream:
        async def event_generator() -> AsyncIterator[str]:
            try:
                with requests.post(ollama_url, json=ollama_payload, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    for line in r.iter_lines(decode_unicode=True):
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                            delta_content = chunk.get("message", {}).get("content", "")
                            done = chunk.get("done", False)

                            sse_data = {
                                "id": completion_id,
                                "object": "chat.completion.chunk",
                                "created": created_time,
                                "model": req.model,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"content": delta_content} if delta_content else {},
                                        "finish_reason": "stop" if done else None,
                                    }
                                ],
                            }
                            yield f"data: {json.dumps(sse_data)}\n\n"
                            if done:
                                break
                        except json.JSONDecodeError:
                            continue
                yield "data: [DONE]\n\n"
            except Exception as ex:
                err_data = {"error": {"message": str(ex), "type": "server_error"}}
                yield f"data: {json.dumps(err_data)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # Non-Streaming Response
    try:
        res = requests.post(ollama_url, json=ollama_payload, timeout=120)
        res.raise_for_status()
        data = res.json()
        content = data.get("message", {}).get("content", "")
        prompt_eval_count = data.get("prompt_eval_count", 0)
        eval_count = data.get("eval_count", 0)

        response_body = {
            "id": completion_id,
            "object": "chat.completion",
            "created": created_time,
            "model": req.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_eval_count,
                "completion_tokens": eval_count,
                "total_tokens": prompt_eval_count + eval_count,
            },
        }
        return JSONResponse(content=response_body)
    except Exception as ex:
        logger.error(f"Ollama chat error: {ex}")
        raise HTTPException(status_code=502, detail=f"Ollama inference error: {ex}")


@router.post("/completions")
async def create_completion(req: CompletionRequest) -> Response:
    """
    OpenAI standard POST /v1/completions endpoint.
    Used for code autocomplete by Continue.dev and other IDE extensions.
    """
    completion_id = f"cmpl-{uuid.uuid4().hex[:12]}"
    created_time = int(time.time())

    prompt_text = req.prompt if isinstance(req.prompt, str) else "\n".join(str(p) for p in req.prompt)

    ollama_payload = {
        "model": req.model,
        "prompt": prompt_text,
        "stream": req.stream,
        "options": {
            "temperature": req.temperature or 0.2,
            "num_predict": req.max_tokens or 256,
        },
    }

    ollama_url = f"{OLLAMA_BASE_URL}/api/generate"

    # Streaming
    if req.stream:
        async def event_generator() -> AsyncIterator[str]:
            try:
                with requests.post(ollama_url, json=ollama_payload, stream=True, timeout=90) as r:
                    r.raise_for_status()
                    for line in r.iter_lines(decode_unicode=True):
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                            tok = chunk.get("response", "")
                            done = chunk.get("done", False)

                            sse_data = {
                                "id": completion_id,
                                "object": "text_completion",
                                "created": created_time,
                                "model": req.model,
                                "choices": [
                                    {
                                        "text": tok,
                                        "index": 0,
                                        "finish_reason": "stop" if done else None,
                                    }
                                ],
                            }
                            yield f"data: {json.dumps(sse_data)}\n\n"
                            if done:
                                break
                        except json.JSONDecodeError:
                            continue
                yield "data: [DONE]\n\n"
            except Exception as ex:
                err_data = {"error": {"message": str(ex)}}
                yield f"data: {json.dumps(err_data)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # Non-streaming
    try:
        res = requests.post(ollama_url, json=ollama_payload, timeout=90)
        res.raise_for_status()
        data = res.json()
        generated_text = data.get("response", "")

        return JSONResponse(content={
            "id": completion_id,
            "object": "text_completion",
            "created": created_time,
            "model": req.model,
            "choices": [
                {
                    "text": generated_text,
                    "index": 0,
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            },
        })
    except Exception as ex:
        logger.error(f"Ollama completion error: {ex}")
        raise HTTPException(status_code=502, detail=f"Ollama completion error: {ex}")
