#!/usr/bin/env bash
#
# One-command environment check and restore. Safe to run any time; the usual
# moment is right after a reboot (notably the reboot that loads the NVIDIA
# kernel module).
#
# Read-only by default: it reports what is and is not ready and exits non-zero
# if anything essential is missing. Pass --fix to let it repair the things that
# are safe to repair without sudo (staging dirs, data-lake fetches, a stale
# runner lock). It never installs packages, never touches a service, and never
# reboots.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DISK2="/mnt/disks/disk-socrateai-local-1"
STAGE="$DISK2/AutoevolveAI"
LAKE="$STAGE/datalake"
VENV="$REPO/.venv/bin/python"

FIX=0
[[ "${1:-}" == "--fix" ]] && FIX=1

ok=0; warn=0; bad=0
pass() { printf '  \033[32mOK\033[0m   %s\n' "$*"; ok=$((ok+1)); }
note() { printf '  \033[33mWARN\033[0m %s\n' "$*"; warn=$((warn+1)); }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$*"; bad=$((bad+1)); }

echo "=== AutoevolveAI environment ==="
echo "repo: $REPO"
[[ $FIX -eq 1 ]] && echo "mode: --fix (will repair what is safe)" || echo "mode: read-only (pass --fix to repair)"
echo

# ---------------------------------------------------------------- 1. storage
echo "1. storage"
if mountpoint -q "$DISK2"; then
    pass "disk 2 mounted ($(df -h "$DISK2" | awk 'NR==2{print $4}') free)"
else
    fail "disk 2 NOT mounted at $DISK2 — models and Lean cache are unreachable"
fi

if [[ -L "$REPO/formal/.lake" ]]; then
    if [[ -e "$REPO/formal/.lake" ]]; then
        pass "formal/.lake -> $(readlink "$REPO/formal/.lake")"
    else
        fail "formal/.lake symlink is dangling — disk 2 may not be mounted"
    fi
elif [[ -d "$REPO/formal/.lake" ]]; then
    note "formal/.lake is a real dir on /; run scripts/setup_disk2_storage.sh --apply"
else
    note "formal/.lake absent (fine until Lean is built)"
fi

for d in "$LAKE" "$STAGE/models" "$STAGE/hf-cache" "$STAGE/training_runs"; do
    if [[ -d "$d" ]]; then
        pass "staging $(basename "$d")"
    elif [[ $FIX -eq 1 ]]; then
        mkdir -p "$d" && pass "staging $(basename "$d") (created)"
    else
        note "staging dir missing: $d"
    fi
done
echo

# ------------------------------------------------------------------- 2. GPU
echo "2. GPU"
if lspci 2>/dev/null | grep -qi "nvidia"; then
    pass "T4 present on the PCI bus"
else
    fail "no NVIDIA device on the PCI bus"
fi

if nvidia-smi -L >/dev/null 2>&1; then
    pass "driver live: $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1)"
    if [[ -x "$VENV" ]] && "$VENV" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
        pass "torch sees CUDA — GPU training is unblocked"
    else
        fail "nvidia-smi works but torch.cuda.is_available() is False (toolkit mismatch)"
    fi
else
    fail "NVIDIA driver not loaded — GPU training stays blocked (card P0-3)"
    echo "         the kernel module for $(uname -r) is missing. To fix:"
    echo "           sudo apt-get install -y linux-modules-nvidia-580-server-\$(uname -r | sed 's/-gcp//')-gcp nvidia-driver-580-server"
    echo "           sudo modprobe nvidia    # or reboot"
    echo "         also install linux-modules-nvidia-580-server-gcp so kernel upgrades keep it."
fi
echo

# --------------------------------------------------------------- 3. services
echo "3. services"
if curl -s --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    n=$(curl -s --max-time 3 http://127.0.0.1:11434/api/tags | grep -o '"name"' | wc -l)
    pass "Ollama up ($n models)"
else
    note "Ollama unreachable on 127.0.0.1:11434"
fi

if command -v redis-cli >/dev/null 2>&1 && redis-cli ping >/dev/null 2>&1; then
    pass "Redis up (DBSIZE=$(redis-cli DBSIZE 2>/dev/null | tr -d '[:alpha:] '))"
else
    note "Redis not running (card P0-5). dump.rdb with 516 keys is staged at $LAKE/data/redis/"
fi

if systemctl is-enabled night-remediation.timer >/dev/null 2>&1; then
    nxt=$(systemctl show night-remediation.timer -p NextElapseUSecRealtime --value 2>/dev/null)
    pass "night timer enabled (next: ${nxt:-unknown})"
else
    note "night timer not enabled: sudo systemctl enable --now night-remediation.timer"
fi
echo

# ------------------------------------------------------------ 4. data + models
echo "4. data lake artifacts"
check_file() {
    if [[ -s "$1" ]]; then pass "$2"; else note "$2 — missing"; return 1; fi
}
missing=0
check_file "$LAKE/vendor/laya/rl_common.py" "rl_common.py (repairs dead import)" || missing=1
check_file "$LAKE/data/redis/dump.rdb" "redis dump.rdb" || missing=1
check_file "$LAKE/data/redis/redis_ltm_lora_dataset.jsonl" "LTM training corpus" || missing=1
[[ -d "$LAKE/data/chroma" ]] && pass "chroma stores" || { note "chroma stores missing"; missing=1; }

nmodels=$(find "$LAKE/models" -type f 2>/dev/null | wc -l)
if [[ "$nmodels" -gt 0 ]]; then
    pass "model artifacts on disk 2: $nmodels file(s), $(du -sh "$LAKE/models" 2>/dev/null | cut -f1)"
else
    note "no model artifacts staged"; missing=1
fi

if [[ $missing -eq 1 && $FIX -eq 1 ]]; then
    echo "  -> fetching missing artifacts"
    "$VENV" "$REPO/scripts/bootstrap_from_datalake.py" --only code >/dev/null 2>&1 && pass "code fetched"
    "$VENV" "$REPO/scripts/bootstrap_from_datalake.py" --only data >/dev/null 2>&1 && pass "data fetched"
fi
echo

# --------------------------------------------------------------- 5. workflow
echo "5. remediation workflow"
if [[ -f "$REPO/.night_runner.lock" ]]; then
    if fuser "$REPO/.night_runner.lock" >/dev/null 2>&1; then
        note "a runner is active right now"
    elif [[ $FIX -eq 1 ]]; then
        rm -f "$REPO/.night_runner.lock" && pass "stale lock removed"
    else
        note "stale lock present — remove it or the next run exits 3"
    fi
else
    pass "no stale lock"
fi

dirty=$(cd "$REPO" && git status --porcelain | wc -l)
if [[ "$dirty" -eq 0 ]]; then
    pass "working tree clean (the runner refuses to start otherwise)"
else
    fail "working tree has $dirty change(s) — tonight's run would abort"
fi

if [[ -f "$REPO/docs/remediation/status.json" ]]; then
    done_n=$("$VENV" -c "import json;print(len(json.load(open('$REPO/docs/remediation/status.json'))['done']))" 2>/dev/null || echo "?")
    pass "cards done: $done_n"
fi
echo

echo "=== $ok ok, $warn warning(s), $bad failure(s) ==="
if [[ $bad -gt 0 ]]; then
    echo "Something essential is missing; see FAIL lines above."
    exit 1
fi
echo "Environment is ready."
