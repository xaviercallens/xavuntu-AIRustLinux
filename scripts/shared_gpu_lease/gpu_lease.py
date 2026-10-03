#!/usr/bin/env python3
"""Shared T4 GPU lease for AutoevolveAI and runux-ai-runtime.

Root cause it fixes: on 2026-09-27 a runux-ai-runtime session ran
`sudo systemctl stop ollama` to free the GPU for its own benchmark while an
AutoevolveAI session had a prover baseline mid-flight on Ollama. Neither
project's own rule ("flag it and get confirmation first" -- runux's
CLAUDE_SESSION_GUIDE.md; "never assume Ollama is free" -- AutoevolveAI's
LL.md) was machine-enforced, so it happened twice in one run.

Design: a single lock file on disk 2 (visible to both projects, both run as
the same user), held with `fcntl.flock` for atomicity across processes, with
JSON metadata (holder project, purpose, pid, host, acquired_at, ttl) written
under the lock. A stale lease (holder process dead, or past its TTL) is
reclaimed automatically -- a crashed job must not deadlock the GPU forever.

No new dependency, no daemon: stdlib only, works from either repo's Python
without either repo importing the other.

CLI:
    gpu_lease.py acquire --holder <name> --purpose <text> [--ttl 1800] [--wait] [--timeout 3600]
    gpu_lease.py release --holder <name>
    gpu_lease.py status
    gpu_lease.py wait [--timeout 3600]      # block until free, then exit 0

Python:
    from gpu_lease import gpu_lease
    with gpu_lease("autoevolveai", "hardness ladder baseline", ttl_s=1800):
        ...  # exclusive GPU work; lease auto-releases on exit, even on error
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import socket
import sys
import time
from collections.abc import Iterator
from pathlib import Path

_DEFAULT_DIR = Path("/mnt/disks/disk-socrateai-local-1/gpu_lease")
if not _DEFAULT_DIR.exists():
    try:
        _DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        _DEFAULT_DIR = Path("/tmp/gpu_lease")

LEASE_DIR = Path(os.environ.get("ANSE_GPU_LEASE_DIR", str(_DEFAULT_DIR)))
LOCK_FILE = LEASE_DIR / "t4.lock"
STATE_FILE = LEASE_DIR / "t4.json"
DEFAULT_TTL_S = 1800  # 30 min; a job that needs longer should re-acquire


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _read_state() -> dict | None:
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _is_stale(state: dict) -> bool:
    if state.get("host") == socket.gethostname() and not _pid_alive(state.get("pid", -1)):
        return True
    return time.time() > state.get("expires_at", 0)


class _LockHandle:
    def __init__(self, fd: int):
        self.fd = fd

    def close(self) -> None:
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)


def _flock(blocking: bool) -> _LockHandle | None:
    LEASE_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o666)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return _LockHandle(fd)


def status() -> dict:
    """Current holder, or {'free': True} if none / stale."""
    state = _read_state()
    if state is None:
        return {"free": True}
    if _is_stale(state):
        return {"free": True, "reclaimed_from": state}
    remaining = round(state["expires_at"] - time.time(), 1)
    return {"free": False, **state, "seconds_remaining": remaining}


def try_acquire(holder: str, purpose: str, ttl_s: int = DEFAULT_TTL_S,
                 pid: int | None = None) -> bool:
    """Non-blocking. Returns True iff the lease is now held by `holder`.

    Identity is the holder string, matching release() -- not the pid. Two
    different logical holders can share a pid (e.g. a library caller testing
    both roles in one process), and a real acquirer's pid changes across
    separate CLI invocations, so pid cannot be the ownership key.

    `pid` is what liveness-based reclaim checks: pass the PID of whatever
    process actually holds the GPU for the lease's duration (a long-running
    script), not a short-lived helper that exits right after acquiring --
    that helper's pid would die immediately and make the lease reclaimable
    a moment after it was granted. Defaults to the caller's own pid, correct
    for the Python context-manager path where the caller holds the lease for
    its own lifetime.
    """
    lock = _flock(blocking=True)  # flock itself always blocks briefly; fast in practice
    if lock is None:
        return False
    try:
        state = _read_state()
        if state is not None and not _is_stale(state) and state.get("holder") != holder:
            return False
        now = time.time()
        STATE_FILE.write_text(json.dumps({
            "holder": holder, "purpose": purpose, "pid": pid if pid is not None else os.getpid(),
            "host": socket.gethostname(), "acquired_at": now,
            "expires_at": now + ttl_s, "ttl_s": ttl_s,
        }, indent=1))
        return True
    finally:
        lock.close()


def release(holder: str) -> bool:
    """Best-effort. Only clears the lease if `holder` matches the recorded
    name -- identity is the holder string, not the pid, because the CLI's
    acquire and release are typically separate shell invocations (different
    pids) even within one logical job."""
    lock = _flock(blocking=True)
    if lock is None:
        return False
    try:
        state = _read_state()
        if state is None or state.get("holder") != holder:
            return False
        STATE_FILE.unlink(missing_ok=True)
        return True
    finally:
        lock.close()


def wait_and_acquire(holder: str, purpose: str, ttl_s: int = DEFAULT_TTL_S,
                      timeout_s: int = 3600, poll_s: int = 10,
                      pid: int | None = None) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if try_acquire(holder, purpose, ttl_s, pid=pid):
            return True
        time.sleep(poll_s)
    return False


@contextlib.contextmanager
def gpu_lease(holder: str, purpose: str, ttl_s: int = DEFAULT_TTL_S,
              timeout_s: int = 3600) -> Iterator[None]:
    """`with gpu_lease("autoevolveai", "..."):` -- blocks until acquired,
    always releases on exit (even on exception)."""
    if not wait_and_acquire(holder, purpose, ttl_s, timeout_s):
        raise TimeoutError(f"GPU lease not acquired within {timeout_s}s "
                           f"(current holder: {status()})")
    try:
        yield
    finally:
        release(holder)


def _cli() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("acquire")
    a.add_argument("--holder", required=True)
    a.add_argument("--purpose", required=True)
    a.add_argument("--ttl", type=int, default=DEFAULT_TTL_S)
    a.add_argument("--wait", action="store_true")
    a.add_argument("--timeout", type=int, default=3600)
    a.add_argument("--pid", type=int, default=None,
                    help="PID whose liveness the lease tracks (default: the "
                         "invoking shell's PID via getppid(), since this CLI "
                         "process exits right after acquiring)")

    r = sub.add_parser("release")
    r.add_argument("--holder", required=True)

    sub.add_parser("status")

    w = sub.add_parser("wait")
    w.add_argument("--timeout", type=int, default=3600)

    args = p.parse_args()

    if args.cmd == "status":
        print(json.dumps(status(), indent=1))
        return 0
    if args.cmd == "release":
        ok = release(args.holder)
        print("released" if ok else "not the holder; nothing released")
        return 0 if ok else 1
    if args.cmd == "wait":
        t0 = time.time()
        while time.time() - t0 < args.timeout:
            if status().get("free"):
                print("free")
                return 0
            time.sleep(10)
        print("timeout: still held", file=sys.stderr)
        return 1
    if args.cmd == "acquire":
        pid = args.pid if args.pid is not None else os.getppid()
        if args.wait:
            ok = wait_and_acquire(args.holder, args.purpose, args.ttl, args.timeout, pid=pid)
        else:
            ok = try_acquire(args.holder, args.purpose, args.ttl, pid=pid)
        print(json.dumps(status(), indent=1))
        return 0 if ok else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
