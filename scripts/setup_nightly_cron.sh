#!/usr/bin/env bash
# ==============================================================================
# Setup / Manage Nightly Retraining & Dream Phase Cron Schedules
# ==============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DREAM_SCRIPT="$REPO_ROOT/scripts/run_cron_dream.sh"
RETRAIN_SCRIPT="$REPO_ROOT/scripts/run_cron_retrain.sh"

chmod +x "$DREAM_SCRIPT" "$RETRAIN_SCRIPT"

ACTION="${1:---install}"

BEGIN_MARKER="# BEGIN_AUTOEVOLVEAI_ANSE_NIGHTLY_SCHEDULE"
END_MARKER="# END_AUTOEVOLVEAI_ANSE_NIGHTLY_SCHEDULE"

show_status() {
    echo "=============================================================================="
    echo "📅 CURRENT USER CRONTAB STATUS (User: $(whoami))"
    echo "=============================================================================="
    if crontab -l 2>/dev/null | grep -q "$BEGIN_MARKER"; then
        echo "✅ AutoevolveAI / ANSE Nightly Cron schedule is currently INSTALLED:"
        crontab -l | awk "/$BEGIN_MARKER/,/$END_MARKER/"
    else
        echo "⚠️ AutoevolveAI / ANSE Nightly Cron schedule is NOT installed in crontab."
    fi
    echo "=============================================================================="
    echo "📁 Log Files in $REPO_ROOT/results/nightly_training/:"
    ls -lh "$REPO_ROOT/results/nightly_training/" 2>/dev/null || echo "(No log files yet)"
    echo "=============================================================================="
}

uninstall_cron() {
    echo "🧹 Removing AutoevolveAI Nightly Cron schedule from crontab..."
    CURRENT_CRON=$(crontab -l 2>/dev/null || true)
    if [ -n "$CURRENT_CRON" ]; then
        CLEANED_CRON=$(echo "$CURRENT_CRON" | awk "
            /$BEGIN_MARKER/ { skip=1; next }
            /$END_MARKER/ { skip=0; next }
            !skip { print }
        ")
        echo "$CLEANED_CRON" | crontab -
        echo "✅ Uninstalled successfully."
    else
        echo "ℹ️ Crontab was already empty."
    fi
}

install_cron() {
    uninstall_cron
    echo "⚙️ Installing AutoevolveAI Nightly Cron schedule..."

    NEW_SCHEDULE=$(cat <<EOF
$BEGIN_MARKER
# ANSE Nightly REM Sleep Dream Phase (02:00 AM)
# Consolidates hippocampal memory, trains Laya LoRA adapters, runs Latent MCTS
0 2 * * * "$DREAM_SCRIPT"

# ANSE Master Continual Learning Retraining Pipeline (05:05 AM)
# Runs Dream Phase, Redis LTM Sync, Qwen LoRA, RL critic, JEPA, Autopoiesis, GCP Deploy
5 5 * * * "$RETRAIN_SCRIPT"
$END_MARKER
EOF
)

    CURRENT_CRON=$(crontab -l 2>/dev/null || true)
    if [ -n "$CURRENT_CRON" ]; then
        COMBINED_CRON=$(printf "%s\n\n%s\n" "$CURRENT_CRON" "$NEW_SCHEDULE")
    else
        COMBINED_CRON=$(printf "%s\n" "$NEW_SCHEDULE")
    fi

    echo "$COMBINED_CRON" | crontab -
    echo "✅ Successfully installed nightly schedule into crontab!"
    show_status
}

case "$ACTION" in
    --install)
        install_cron
        ;;
    --uninstall)
        uninstall_cron
        show_status
        ;;
    --status)
        show_status
        ;;
    *)
        echo "Usage: $0 [--install | --uninstall | --status]"
        exit 1
        ;;
esac
