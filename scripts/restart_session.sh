#!/usr/bin/env bash
# Bring the ANSE stack up and report what is actually true.
#
# Written because this environment has two failure modes that are invisible unless
# you look for them:
#
#   1. Ollama probes for a GPU ONCE at startup. If it wins the race against the
#      NVIDIA driver it serves on CPU forever, at ~2.3 tok/s instead of ~35, and
#      nothing reports it. That cost days. This script verifies placement and
#      restarts Ollama if a model is loaded but not on the GPU.
#
#   2. MCP servers are spawned by Claude Code, not by this script. `.mcp.json`
#      previously used `${CLAUDE_PROJECT_DIR:-.}` -- bash-style `:-default` syntax
#      that Claude Code does NOT expand -- so posix_spawn got the literal string
#      and every server failed with ENOENT. Fixed, but an MCP connection cannot be
#      reloaded mid-session: it takes effect on the NEXT `claude` invocation. This
#      script checks the config is spawnable and says so.
#
# Every check prints PASS / FAIL / SKIP with the evidence behind it. Exit code is
# nonzero if anything FAILED, so this is usable as a gate.
#
# Usage:
#   scripts/restart_session.sh            # verify, restart what needs it
#   scripts/restart_session.sh --quick    # skip the slow warm-throughput probe
#   scripts/restart_session.sh --no-sudo  # report instead of restarting services

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.elan/bin:$REPO/.venv/bin:$PATH"
export PYTHONPATH="$REPO"
export ANSE_LEAN_TESTS=0

PY="$REPO/.venv/bin/python"
LEASE=/mnt/disks/disk-socrateai-local-1/gpu_lease/gpu_lease.py
# Stopping/restarting Ollama while another job is mid-inference wastes that
# job's work (measured 2026-09-27: a runux-ai-runtime session's uncoordinated
# `systemctl stop ollama` cost an AutoevolveAI prover baseline 112 rows).
# Best-effort: absence of the lease module never blocks this script.
lease_acquire() { [[ -f "$LEASE" ]] || return 0; "$PY" "$LEASE" acquire --holder autoevolveai --purpose "$1" --ttl 60 --wait --timeout 120 >/dev/null 2>&1; }
lease_release() { [[ -f "$LEASE" ]] || return 0; "$PY" "$LEASE" release --holder autoevolveai >/dev/null 2>&1; true; }
QUICK=0
USE_SUDO=1
for arg in "$@"; do
  case "$arg" in
    --quick)   QUICK=1 ;;
    --no-sudo) USE_SUDO=0 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

FAILED=0
pass() { printf '  [PASS] %-22s %s\n' "$1" "$2"; }
fail() { printf '  [FAIL] %-22s %s\n' "$1" "$2"; FAILED=$((FAILED + 1)); }
skip() { printf '  [SKIP] %-22s %s\n' "$1" "$2"; }
hdr()  { printf '\n=== %s ===\n' "$1"; }

hdr "1. Interpreter and repo"
if [[ -x "$PY" ]]; then
  pass "venv python" "$("$PY" --version 2>&1) at .venv/bin/python"
else
  fail "venv python" "missing .venv -- run: uv sync --all-extras"
  echo; echo "Cannot continue without the venv."; exit 1
fi
pass "repo" "$REPO @ $(git rev-parse --short HEAD 2>/dev/null || echo 'not a git repo')"

# Disk 2 carries the data lake, Chroma and the model store. Its absence is not
# cosmetic: ingestion and training both write there.
if [[ -d /mnt/disks/disk-socrateai-local-1 ]]; then
  pass "disk2" "$(df -h /mnt/disks/disk-socrateai-local-1 | awk 'NR==2{print $4" free"}')"
else
  fail "disk2" "/mnt/disks/disk-socrateai-local-1 not mounted (data lake + Chroma live there)"
fi

hdr "2. GPU driver"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  pass "nvidia-smi" "$(nvidia-smi --query-gpu=name,memory.free,driver_version \
      --format=csv,noheader,nounits | awk -F', ' '{print $1", "$2" MiB free, driver "$3}')"
else
  fail "nvidia-smi" "driver unreachable -- Ollama will serve on CPU (~15x slower)"
fi

hdr "3. Redis"
if redis-cli ping >/dev/null 2>&1; then
  pass "redis" "up, $(redis-cli DBSIZE | awk '{print $1}') keys"
else
  if [[ $USE_SUDO -eq 1 ]]; then
    sudo systemctl start redis-server 2>/dev/null || sudo systemctl start redis 2>/dev/null
    sleep 2
  fi
  if redis-cli ping >/dev/null 2>&1; then
    pass "redis" "started, $(redis-cli DBSIZE | awk '{print $1}') keys"
  else
    fail "redis" "unreachable -- long-term memory writes will RAISE (by design)"
  fi
fi

hdr "4. Ollama and GPU placement"
if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  if [[ $USE_SUDO -eq 1 ]]; then
    echo "  ollama not responding; starting..."
    if lease_acquire "restart_session: start ollama"; then
      sudo systemctl start ollama 2>/dev/null
      sleep 8
      lease_release
    else
      echo "  could not acquire shared GPU lease; starting anyway (best-effort)"
      sudo systemctl start ollama 2>/dev/null
      sleep 8
    fi
  fi
fi

if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  pass "ollama api" "reachable ($(curl -s http://localhost:11434/api/tags \
      | "$PY" -c 'import json,sys;print(len(json.load(sys.stdin).get("models",[])),"models")'))"

  PS_OUT="$(ollama ps 2>/dev/null)"
  if echo "$PS_OUT" | grep -q "GPU"; then
    pass "gpu placement" "a model is resident on the GPU"
  elif [[ "$(echo "$PS_OUT" | wc -l)" -le 1 ]]; then
    skip "gpu placement" "no model loaded yet; placement is checked on first inference"
  else
    # This is the regression the script exists for: loaded, but on CPU.
    fail "gpu placement" "model loaded but NOT on GPU -- restarting ollama so it re-probes"
    if [[ $USE_SUDO -eq 1 ]]; then
      # Restarting an already-running Ollama can kill someone else's
      # in-flight generation, so unlike the start-when-idle case above,
      # a failed lease acquisition here skips the restart rather than
      # proceeding best-effort.
      if lease_acquire "restart_session: fix GPU placement"; then
        sudo systemctl restart ollama && sleep 8
        lease_release
        ollama ps 2>/dev/null | grep -q "GPU" \
          && { pass "gpu placement" "recovered after restart"; FAILED=$((FAILED - 1)); } \
          || fail "gpu placement" "still on CPU after restart -- check driver load order"
      else
        fail "gpu placement" "could not acquire shared GPU lease; another job may be using the GPU -- not restarting ollama"
      fi
    fi
  fi

  # Residency policy: 27 GB of pulled weights against ~15 GB of VRAM, so one model
  # at a time. Without this, concurrent different-model workloads thrash on ~200 s
  # cold loads.
  DROPIN=/etc/systemd/system/ollama.service.d/10-t4-residency.conf
  if [[ -f "$DROPIN" ]]; then
    pass "residency policy" "$DROPIN present (MAX_LOADED_MODELS=1, KEEP_ALIVE=10m)"
  else
    fail "residency policy" "$DROPIN missing -- models may co-reside and thrash"
  fi
else
  fail "ollama api" "unreachable on :11434"
fi

if [[ $QUICK -eq 0 ]] && curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  hdr "5. Warm throughput (cold load is ~200 s and is not the useful number)"
  TPS="$("$PY" - <<'PYEOF' 2>/dev/null
import httpx
M, P = "qwen2.5-coder:7b-instruct", "def add(a,b):"
body = {"model": M, "prompt": P, "stream": False,
        "options": {"num_predict": 60, "temperature": 0.2}}
try:
    httpx.post("http://localhost:11434/api/generate", json=body, timeout=900)  # warm
    d = httpx.post("http://localhost:11434/api/generate", json=body, timeout=900).json()
    n, s = d.get("eval_count", 0), d.get("eval_duration", 1) / 1e9
    print(f"{n/s:.1f}" if s else "0")
except Exception:
    print("0")
PYEOF
)"
  if [[ -n "$TPS" ]] && "$PY" -c "import sys;sys.exit(0 if float('$TPS')>=10 else 1)" 2>/dev/null; then
    pass "warm throughput" "$TPS tok/s"
  else
    fail "warm throughput" "${TPS:-0} tok/s -- CPU-class; the GPU is not being used"
  fi
else
  skip "warm throughput" "--quick, or ollama unreachable"
fi

hdr "6. MCP servers (health-checked by Claude Code itself; attach on the NEXT session)"
# Ask Claude Code, don't infer. An earlier version of this section grepped
# .mcp.json for "bad" patterns, and the pattern it rejected -- ${CLAUDE_PROJECT_DIR:-.}
# -- was in fact the one that worked (24 of 24 logged sessions connected). The one
# it recommended, a bare ${CLAUDE_PROJECT_DIR}, failed every session: that variable is
# set for hooks but NOT for .mcp.json expansion, so without a default it expands to
# nothing and posix_spawn gets '/.venv/bin/python'. `claude mcp list` spawns each
# server exactly as a session would, so it cannot drift from reality that way.
if [[ ! -f .mcp.json ]]; then
  fail "mcp config" ".mcp.json absent"
elif command -v claude >/dev/null 2>&1; then
  MCP_OUT="$(timeout 150 claude mcp list 2>&1)"
  if echo "$MCP_OUT" | grep -q "Missing environment variables"; then
    fail "mcp config" "$(echo "$MCP_OUT" | grep -o 'Missing environment variables: [A-Z_, ]*' \
      | sort -u | head -1) -- give it a default, e.g. \${VAR:-.}"
  fi
  while IFS= read -r line; do
    NAME="${line%%:*}"
    if [[ "$line" == *"✔ Connected"* ]]; then
      pass "  mcp:$NAME" "connected"
    elif [[ "$line" == *"✘"* || "$line" == *"Failed"* ]]; then
      fail "  mcp:$NAME" "$(echo "${line##* - }" | cut -c1-90)"
    fi
  done < <(echo "$MCP_OUT" | grep -E '^[A-Za-z0-9_.-]+: .* - (✔|✘)')
  echo "$MCP_OUT" | grep -qE ' - (✔|✘)' || fail "mcp config" "claude mcp list reported no servers"
else
  # No CLI here (e.g. the Antigravity host). Flag the one form known to break.
  if grep -qE '\$\{CLAUDE_PROJECT_DIR\}' .mcp.json; then
    fail "mcp config" "bare \${CLAUDE_PROJECT_DIR} is unset for .mcp.json; use \${CLAUDE_PROJECT_DIR:-.}"
  else
    skip "mcp config" "claude CLI not on PATH; cannot health-check servers"
  fi
fi

hdr "7. Environment profile (probed, never assumed)"
# One python call, no pipe. A heredoc on `python -` occupies stdin, so piping JSON
# INTO such a call silently delivers nothing -- which is how this check first
# reported "could not resolve" against a profile that resolves fine.
PROFILE_LINE="$("$PY" - <<'PYEOF' 2>/dev/null
from anse.infrastructure.agent_environment import resolve_capability_profile
p = resolve_capability_profile()
d = p.as_dict() if hasattr(p, "as_dict") else p.__dict__
gpu = d.get("gpu")
gpu_name = (gpu.get("name") if isinstance(gpu, dict) else getattr(gpu, "name", None)) or "no gpu"
mem = d.get("memory")
ram = (mem.get("ram_gb") if isinstance(mem, dict) else getattr(mem, "ram_gb", "?"))
print(f"{d.get('profile_id')} | agent={d.get('coding_agent')} | "
      f"device={d.get('device')} | {gpu_name} | RAM {ram} GB")
PYEOF
)"
if [[ -n "$PROFILE_LINE" ]]; then
  pass "profile" "$PROFILE_LINE"
else
  fail "profile" "could not resolve -- check: python -m anse.infrastructure.agent_environment"
fi

hdr "8. Data plane"
EP="data/episodes/harvest.jsonl"
if [[ -f "$EP" ]]; then
  # Capture, then judge in bash, so a FAIL reaches the counter. A `[FAIL]` printed
  # from inside a pipeline runs in a subshell and its increment is discarded -- which
  # produced a run that showed a FAIL line and then "All checks passed".
  EP_LINE="$("$PY" - <<'PYEOF' 2>/dev/null
import json
rows = [json.loads(l) for l in open("data/episodes/harvest.jsonl") if l.strip()]
tasks = {r["task"] for r in rows}
dims = {len(r.get("hidden_state") or []) for r in rows}
verdicts = sum(1 for r in rows if (r.get("metadata") or {}).get("tests_total", 0) > 0)
failing = sum(1 for r in rows if not r.get("converged"))
ok = len(tasks) >= 2 and len(dims) == 1 and verdicts == len(rows) and bool(rows)
print(f"{int(ok)}|{failing}|{len(rows)} rows, {len(tasks)} tasks, dims {sorted(dims)}, "
      f"{verdicts} with verdicts")
PYEOF
)"
  if [[ -n "$EP_LINE" ]]; then
    EP_OK="${EP_LINE%%|*}"; REST="${EP_LINE#*|}"
    EP_FAILING="${REST%%|*}"; EP_DESC="${REST#*|}"
    if [[ "$EP_OK" == "1" ]]; then
      pass "episodes" "$EP_DESC"
    else
      fail "episodes" "$EP_DESC -- JEPA contract NOT met"
    fi
    # Well-formed but non-discriminative is a real limitation, not a pass.
    if [[ "$EP_FAILING" == "0" ]]; then
      printf '  [WARN] %-22s %s\n' "episodes" \
        "0 failing examples -- validates the data path but carries no discriminative"
      printf '  %-29s %s\n' "" "signal; use harder tasks before training on it"
    fi
  else
    fail "episodes" "could not parse $EP"
  fi
else
  skip "episodes" "$EP absent -- run: scripts/harvest_episodes.py"
fi

hdr "Summary"
if [[ $FAILED -eq 0 ]]; then
  echo "  All checks passed."
else
  echo "  $FAILED check(s) FAILED -- these are real defects in this deployment,"
  echo "  not script bugs. Fix them before trusting a run."
fi

cat <<'NEXT'

Next steps
  full validator     .venv/bin/python scripts/validate_environment.py
  load conversations .venv/bin/python scripts/ingest_memory.py --transcripts \
                       --transcript-root ~/.claude/projects/-home-callensxavier-gmail-com-AutoevolveAI
  load documents     .venv/bin/python scripts/ingest_memory.py --pdfs
  harvest episodes   .venv/bin/python scripts/harvest_episodes.py --tasks 12 --samples 2
  reproduce the demo .venv/bin/python scripts/phd_demo/run_experiment.py --check

MCP: a connection cannot be reloaded mid-session. Start a fresh `claude` in this
directory for the servers above to attach.
NEXT

exit $(( FAILED > 0 ? 1 : 0 ))
