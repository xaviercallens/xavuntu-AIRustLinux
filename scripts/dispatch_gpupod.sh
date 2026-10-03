#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
    echo "Usage: $0 {export|push <host:port>|pull <host:port>|hot-reload}"
    echo ""
    echo "Commands:"
    echo "  export             Harvests frontier streams from Redis LTM into results/"
    echo "  push <host:port>   Rsyncs repository and datasets to remote RunPod instance"
    echo "  pull <host:port>   Rsyncs trained LoRA adapters back from remote RunPod instance"
    echo "  hot-reload         Reloads the latest adapter into local vLLM / gateway"
    echo ""
    echo "Example:"
    echo "  $0 export"
    echo "  $0 push root@123.45.67.89:22222"
    echo "  $0 pull root@123.45.67.89:22222"
    exit 1
}

CMD="${1:-}"

case "${CMD}" in
    export)
        echo "🌾 Harvesting Frontier Model Demonstrations from Redis LTM..."
        uv run python "${PROJECT_ROOT}/scripts/export_frontier_distillation.py"
        echo "✅ Datasets compiled in results/frontier_distillation_{sft,dpo}.jsonl"
        ;;
    push)
        TARGET="${2:-}"
        if [ -z "${TARGET}" ]; then usage; fi
        HOST="${TARGET%%:*}"
        PORT="${TARGET##*:}"
        if [ "${PORT}" = "${HOST}" ]; then PORT="22"; fi
        
        echo "🚀 Syncing AutoevolveAI to ${HOST} (Port: ${PORT})..."
        rsync -avz --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
            -e "ssh -p ${PORT}" \
            "${PROJECT_ROOT}/" "${HOST}:/workspace/AutoevolveAI/"
        echo "✅ Push complete. Connect with: ssh ${HOST} -p ${PORT}"
        ;;
    pull)
        TARGET="${2:-}"
        if [ -z "${TARGET}" ]; then usage; fi
        HOST="${TARGET%%:*}"
        PORT="${TARGET##*:}"
        if [ "${PORT}" = "${HOST}" ]; then PORT="22"; fi

        echo "📦 Pulling trained LoRA adapters from ${HOST} (Port: ${PORT})..."
        mkdir -p "${PROJECT_ROOT}/adapters/"
        rsync -avz \
            -e "ssh -p ${PORT}" \
            "${HOST}:/workspace/AutoevolveAI/adapters/" "${PROJECT_ROOT}/adapters/"
        echo "✅ Adapters successfully downloaded to adapters/"
        ;;
    hot-reload)
        echo "🔄 Triggering local adapter hot-reload..."
        uv run python -c "
from daily_trainer_daemon import reload_vllm_adapter
import redis
r = redis.Redis(host='127.0.0.1', port=6379)
active = r.get('antigravity:active_lora_version')
print('Active LoRA in Redis:', active)
"
        ;;
    *)
        usage
        ;;
esac
