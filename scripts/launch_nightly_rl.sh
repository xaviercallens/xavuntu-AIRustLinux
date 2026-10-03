#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# launch_nightly_rl.sh — Run 100 Functional Tests & Nightly RL Post-Training
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

LOG_DIR="results/rl_nightly"
mkdir -p "$LOG_DIR"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_LOG="${LOG_DIR}/nightly_run_${TIMESTAMP}.log"

echo "═══════════════════════════════════════════════════════════════════════" | tee -a "$RUN_LOG"
echo "🌙 ANSE NIGHTLY RL PIPELINE DISPATCH" | tee -a "$RUN_LOG"
echo "   Start time: $(date)" | tee -a "$RUN_LOG"
echo "   Working dir: $REPO_DIR" | tee -a "$RUN_LOG"
echo "   Log file:    $RUN_LOG" | tee -a "$RUN_LOG"
echo "═══════════════════════════════════════════════════════════════════════" | tee -a "$RUN_LOG"

# Step 1: 100 Code Functional Tests (Issue & Positive) + Session Recording
echo "[1/2] Conducting 100 Code Functional Tests with Redis Session Recording..." | tee -a "$RUN_LOG"
uv run python scripts/run_100_functional_tests.py --num-tests 100 --output-dir "$LOG_DIR" 2>&1 | tee -a "$RUN_LOG"

# Step 2: Nightly RL / DPO Post-Training
echo "[2/2] Conducting Post-Training on RL Reinforcement Learning..." | tee -a "$RUN_LOG"
uv run python scripts/nightly_rl_train.py \
    --dataset "${LOG_DIR}/dpo_preference_pairs.jsonl" \
    --output-dir "$LOG_DIR" \
    --epochs 100 \
    --batch-size 8 \
    --lr 1e-3 2>&1 | tee -a "$RUN_LOG"

echo "═══════════════════════════════════════════════════════════════════════" | tee -a "$RUN_LOG"
echo "✅ NIGHTLY PIPELINE COMPLETED SUCCESSFULLY AT $(date)" | tee -a "$RUN_LOG"
echo "   Traces & Sessions: ${LOG_DIR}/sessions.jsonl" | tee -a "$RUN_LOG"
echo "   DPO Preference:    ${LOG_DIR}/dpo_preference_pairs.jsonl" | tee -a "$RUN_LOG"
echo "   Critic Model:      ${LOG_DIR}/anse_critic_final.pt" | tee -a "$RUN_LOG"
echo "   Report:            ${LOG_DIR}/training_report.json" | tee -a "$RUN_LOG"
echo "═══════════════════════════════════════════════════════════════════════" | tee -a "$RUN_LOG"
