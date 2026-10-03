#!/usr/bin/env bash
# ==============================================================================
# Cron Wrapper for Nightly REM Sleep Dream Phase (Scheduled at 02:00 AM)
# Consolidates hippocampal memory, trains Laya LoRA adapters, runs Latent MCTS
# ==============================================================================
set -euo pipefail

export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LOG_DIR="$REPO_ROOT/results/nightly_training"
mkdir -p "$LOG_DIR"
CRON_LOG="$LOG_DIR/cron_dream.log"

echo "==============================================================================" >> "$CRON_LOG"
echo "🌙 CRON DREAM PHASE LAUNCH: $(date --iso-8601=seconds)" >> "$CRON_LOG"
echo "==============================================================================" >> "$CRON_LOG"

exec "$HOME/.local/bin/uv" run python "$REPO_ROOT/scripts/nightly_dream_phase.py" >> "$CRON_LOG" 2>&1
