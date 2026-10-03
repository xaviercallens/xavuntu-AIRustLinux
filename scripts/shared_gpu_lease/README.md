# Shared T4 GPU lease

**Canonical, live copy:** `/mnt/disks/disk-socrateai-local-1/gpu_lease/gpu_lease.py`
(disk 2, so it survives this repo's checkout and is reachable from any project on this
machine, e.g. `runux-ai-runtime` — see its `docs/SHARED_GPU_LEASE_PROPOSAL.md`).

`gpu_lease.py` in this directory is a **snapshot for review and history**, not the
module the code actually imports. `scripts/hardness/run_ladder.py` and
`scripts/night_training_workflow.py` add the disk-2 path to `sys.path` and import from
there; `scripts/restart_session.sh` shells out to the disk-2 copy's CLI. If you change
the lease's behavior, edit the disk-2 file and copy it back here — this file existing
out of sync with disk 2 is a bug, not an alternate implementation.

## Why it exists

On 2026-09-27 a runux-ai-runtime session ran `sudo systemctl stop ollama` twice during
an AutoevolveAI prover baseline, costing it 112 wasted rows each time, with zero
coordination between the two projects sharing one T4. See `LL.md` §8b and `TODO.md`
item 10 for the incident and the requirement; `docs/SHARED_GPU_LEASE_PROPOSAL.md` in
runux-ai-runtime for the cross-project proposal.

## What it is

A single lock file (`fcntl.flock`) plus a JSON state file on disk 2, holder identified
by name (not pid, since CLI acquire/release are separate shell invocations), reclaimed
automatically on TTL expiry or a dead holder pid. Stdlib only. Verified 2026-09-27:
cross-process contention blocked, a `kill -9`'d holder's lease reclaims via dead-pid
detection before its TTL would expire, and a missing lease file never blocks a caller
(best-effort degrade, see `restart_session.sh`'s `lease_acquire()`).

## Usage

```python
import sys; sys.path.insert(0, "/mnt/disks/disk-socrateai-local-1/gpu_lease")
from gpu_lease import gpu_lease
with gpu_lease("autoevolveai", "what you're doing", ttl_s=1800, timeout_s=3600):
    ...  # exclusive GPU work; released on exit, including on exception
```

```bash
LEASE=/mnt/disks/disk-socrateai-local-1/gpu_lease/gpu_lease.py
python3 "$LEASE" acquire --holder autoevolveai --purpose "..." --ttl 1800 --wait --timeout 3600
trap 'python3 "$LEASE" release --holder autoevolveai' EXIT
# ... GPU work in the SAME shell/script, so the recorded pid stays alive ...
```
