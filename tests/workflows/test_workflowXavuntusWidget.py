"""
tests/workflows/test_workflowXavuntusWidget.py — Unit Tests for Xavuntu Widget, GNOME & Voice Hardness Workflow.
"""

import os
import pytest

from workflowXavuntusWidget import WorkflowXavuntusWidget


@pytest.fixture
def workflow():
    return WorkflowXavuntusWidget()


def test_gate_1_gnome_cyberpunk_aesthetics(workflow):
    res = workflow.gate_1_gnome_cyberpunk_aesthetics()
    assert res.passed is True
    assert res.score >= 0.8
    assert "theme_installed" in res.details


def test_gate_2_modular_widget_and_kula_telemetry(workflow):
    res = workflow.gate_2_modular_widget_and_kula_telemetry()
    assert res.passed is True
    assert res.score >= 0.8
    assert res.details.get("hud_compilation") == "OK"


def test_gate_3_kal_dual_model_and_voice_control(workflow):
    res = workflow.gate_3_kal_dual_model_and_voice_control()
    assert res.passed is True
    assert res.score >= 0.8
    assert res.details.get("voice_command_intent") == "SYSTEM_STATUS"


def test_gate_4_sovereign_cyber_protection(workflow):
    res = workflow.gate_4_sovereign_cyber_protection()
    assert res.passed is True
    assert res.score >= 0.8
    assert res.details.get("zero_trust_attestation") is True


def test_gate_5_thermodynamic_and_antistub_monotonicity(workflow):
    res = workflow.gate_5_thermodynamic_and_antistub_monotonicity()
    assert res.passed is True
    assert res.score == 1.0
    assert res.details.get("antistub_passed") is True
    assert res.details.get("delta_e_joules") <= 0.0


def test_gate_6_redis_long_term_memory_and_context_management(workflow):
    res = workflow.gate_6_redis_long_term_memory_and_context_management()
    assert res.passed is True
    assert res.score >= 0.8
    assert res.details.get("pruning_functional") is True
    assert res.details.get("cosine_sim_related") > res.details.get("cosine_sim_unrelated")


def test_gate_7_runux_ai_runtime_optimization(workflow):
    res = workflow.gate_7_runux_ai_runtime_optimization()
    assert res.passed is True
    assert res.score >= 0.8
    assert res.details.get("polarquant_compression_ratio") >= 4.0
    assert res.details.get("systolic_occupancy") >= 0.85
    assert res.details.get("paged_kv_allocation_ok") is True


def test_execute_all_gates(workflow):
    report = workflow.execute_all_gates()
    assert report.all_gates_passed is True
    assert report.proof_receipt.startswith("PROOF_RECEIPT:XAVUNTU_WIDGET_VOICE_")
    assert len(report.gates) == 7
    assert report.thermodynamic_delta_e <= 0.0
