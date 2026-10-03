#!/usr/bin/env bash
# ==============================================================================
# Cron Wrapper for Master Nightly Retraining Pipeline (Scheduled at 05:05 AM)
# Runs REM dream phase, Redis LTM sync, Qwen LoRA, RL critic, JEPA, autopoiesis, GCP deploy
# ==============================================================================
set -euo pipefail

export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LOG_DIR="$REPO_ROOT/results/nightly_training"
mkdir -p "$LOG_DIR"
CRON_LOG="$LOG_DIR/cron_retrain_5am.log"

echo "==============================================================================" >> "$CRON_LOG"
echo "🚀 CRON RETRAINING PIPELINE LAUNCH: $(date --iso-8601=seconds)" >> "$CRON_LOG"
echo "==============================================================================" >> "$CRON_LOG"

exec "$HOME/.local/bin/uv" run python "$REPO_ROOT/scripts/nightly_retrain_at_5am.py" --now "$@" >> "$CRON_LOG" 2>&1
