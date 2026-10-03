"""
Junior Model Cluster Coordinator & Load Balancer.

Coordinates a pool of junior/student inference endpoints (e.g., local vLLM,
Ollama, or low-cost Flash APIs) during the active learning phase.
Escalates hard tasks to Frontier Teacher models and logs all frontier interactions
to Redis LTM for post-processing distillation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class JuniorWorker:
    """Represents a junior inference worker in the local/remote cluster."""
    worker_id: str
    endpoint_url: str
    model_name: str
    max_concurrency: int = 4
    active_requests: int = 0
    total_completed: int = 0
    is_healthy: bool = True
    last_latency_ms: float = 0.0


@dataclass
class ClusterConfig:
    """Configuration for the Junior Inference Cluster."""
    workers: list[JuniorWorker] = field(default_factory=list)
    escalate_on_error: bool = True
    escalate_on_complexity_threshold: int = 15  # Cyclomatic complexity or token threshold
    frontier_stream_key: str = "antigravity:stream:frontier_distillation"


class JuniorClusterRouter:
    """
    Manages load balancing across junior models and transparently escalates
    to Frontier models (Gemini 3.1 Pro / Claude 3.7 Sonnet / Opus) when complexity
    or retry counts require frontier reasoning.
    """

    def __init__(self, config: ClusterConfig | None = None) -> None:
        self.config = config or self._default_config()
        self._lock = asyncio.Lock()
        self.client = httpx.AsyncClient(timeout=60.0)

    @staticmethod
    def _default_config() -> ClusterConfig:
        local_url = os.getenv("LOCAL_INFERENCE_URL", "http://localhost:8000/v1/chat/completions")
        local_model = os.getenv("LOCAL_MODEL_NAME", "antigravity-local")
        fallback_model = os.getenv("MODEL_EXECUTION", "gemini-3.8-flash")
        
        workers = [
            JuniorWorker(
                worker_id="junior-local-vllm",
                endpoint_url=local_url,
                model_name=local_model,
                max_concurrency=4,
            ),
            JuniorWorker(
                worker_id="junior-cloud-flash",
                endpoint_url="https://generativelanguage.googleapis.com",
                model_name=fallback_model,
                max_concurrency=16,
            ),
        ]
        return ClusterConfig(workers=workers)

    def is_complex_task(self, prompt: str) -> bool:
        """Determines if a task exceeds Junior capabilities and requires a Frontier model."""
        prompt_lower = prompt.lower()
        complexity_indicators = [
            "architect",
            "formal proof",
            "lean 4",
            "refactor entire",
            "multi-file",
            "solve differential equation",
            "symplect",
            "quantum",
            "tensor dimension mismatch",
        ]
        # Check explicit keywords or prompt length
        if any(ci in prompt_lower for ci in complexity_indicators):
            return True
        if len(prompt.split()) > 600:
            return True
        return False

    async def select_best_worker(self) -> JuniorWorker | None:
        """Least-connections load balancing across healthy junior workers."""
        async with self._lock:
            available = [w for w in self.config.workers if w.is_healthy and w.active_requests < w.max_concurrency]
            if not available:
                return None
            return min(available, key=lambda w: (w.active_requests, w.last_latency_ms))

    async def record_worker_result(self, worker_id: str, latency_ms: float, success: bool) -> None:
        """Updates worker health telemetry."""
        async with self._lock:
            for w in self.config.workers:
                if w.worker_id == worker_id:
                    w.active_requests = max(0, w.active_requests - 1)
                    w.last_latency_ms = latency_ms
                    if success:
                        w.total_completed += 1
                        w.is_healthy = True
                    else:
                        logger.warning("Junior worker '%s' encountered failure.", worker_id)
                    break
