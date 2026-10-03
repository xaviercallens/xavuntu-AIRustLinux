from __future__ import annotations

from typing import Any

from anse.symbolic.sandbox import ExecutionResult

RESULT_VARIABLE = "BENCH_RESULT"
_MAX_RESULT_CHARS = 2000
_MAX_REPORTED_FAILURES = 3
_DRIVER_BUDGET_FRACTION = 0.8
"""Share of the sandbox timeout the driver grants the worker, so the driver always reports first."""

# ─── Out-of-band verification: trusted driver + isolated worker ──────────────

# Runs the untrusted component. Holds no secret: no nonce, no tests, no expected values.
_WORKER_SOURCE = r"""
import ast, json, os, sys, traceback

_in = os.fdopen(os.dup(0), "r", encoding="utf-8")
_out = os.fdopen(os.dup(1), "w", encoding="utf-8")
_null = os.open(os.devnull, os.O_RDWR)
os.dup2(_null, 0)
os.dup2(_null, 1)


def _send(message):
    _out.write(json.dumps(message) + "\n")
    _out.flush()


def _problem(exc):
    return {"error": type(exc).__name__, "message": str(exc)[:300]}


_path = sys.argv[1]
_ns = {"__name__": "anse_component", "__file__": _path}
try:
    with open(_path, encoding="utf-8") as _handle:
        exec(compile(_handle.read(), _path, "exec"), _ns)
except BaseException as _exc:
    traceback.print_exc()
    _send({"fatal": type(_exc).__name__ + ": " + str(_exc)[:300]})
    sys.exit(1)
_send({"ready": sorted(k for k, v in _ns.items() if callable(v) and not k.startswith("_"))})

for _line in _in:
    _request = json.loads(_line)
    try:
        if _request["op"] == "call":
            _a = ast.literal_eval(_request["args"])
            _k = ast.literal_eval(_request["kwargs"])
            _value = _ns[_request["name"]](*_a, **_k)
            _reply = {"ok": repr(_value), "a": repr(_a), "k": repr(_k)}
        else:
            exec(_request["code"], _ns)
            _value = _ns[_request["var"]]
            _reply = {"ok": repr(_value)}
    except BaseException as _exc:
        traceback.print_exc()
        _reply = _problem(_exc)
    _reply["id"] = _request.get("id")
    _send(_reply)
"""

# Trusted side. The header (nonce, component source, tests / workload / calls) is prepended by
# build_driver(); this body never changes. It is the only writer to the sandbox's stdout.
_DRIVER_BODY = r'''
import ast, builtins, json, os, select, subprocess, sys, time

_self = globals().get("__file__", "")
try:
    os.unlink(_self)
except OSError:
    pass
if not _self or os.path.exists(_self):
    sys.exit("anse driver: own source could not be removed; refusing to run the component")
try:
    import ctypes
    ctypes.CDLL(None).prctl(4, 0, 0, 0, 0)  # PR_SET_DUMPABLE=0: /proc/<driver>/{mem,fd} closed to the worker
except (OSError, AttributeError):
    pass


class _WorkerFailure(Exception):
    pass


_deadline = time.monotonic() + _BUDGET_SECONDS
with open("component.py", "w", encoding="utf-8") as _handle:
    _handle.write(_COMPONENT)
_stderr_file = open("_worker_stderr.txt", "wb")
_worker = subprocess.Popen([sys.executable, "-c", _WORKER, "component.py"],
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=_stderr_file)
_fd = _worker.stdout.fileno()
_pending = b""


def _recv():
    global _pending
    while b"\n" not in _pending:
        remaining = _deadline - time.monotonic()
        if remaining <= 0 or not select.select([_fd], [], [], remaining)[0]:
            raise _WorkerFailure("component timed out")
        chunk = os.read(_fd, 1 << 16)
        if not chunk:
            raise _WorkerFailure("component process exited")
        _pending += chunk
        if len(_pending) > (8 << 20):
            raise _WorkerFailure("component reply too large")
    line, _, _pending = _pending.partition(b"\n")
    try:
        message = json.loads(line)
    except ValueError:
        raise _WorkerFailure("malformed reply from the component process")
    if not isinstance(message, dict):
        raise _WorkerFailure("malformed reply from the component process")
    return message


def _request(message):
    """One round trip. The reply must echo a fresh random id, so a reply queued in advance is useless."""
    message["id"] = os.urandom(8).hex()
    _send(message)
    reply = _recv()
    if reply.get("id") != message["id"]:
        raise _WorkerFailure("reply out of sequence from the component process")
    return reply


def _send(message):
    try:
        _worker.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        _worker.stdin.flush()
    except OSError:
        raise _WorkerFailure("component process exited")


def _raise_remote(reply):
    kind = getattr(builtins, str(reply.get("error")), None)
    if not (isinstance(kind, type) and issubclass(kind, Exception)):
        kind = RuntimeError
    raise kind(str(reply.get("message", "")))


def _proxy(name):
    def call(*args, **kwargs):
        reply = _request({"op": "call", "name": name, "args": repr(args), "kwargs": repr(kwargs)})
        if "ok" not in reply:
            _raise_remote(reply)
        try:
            if "a" in reply:
                new_a = ast.literal_eval(reply["a"])
                for orig, new_val in zip(args, new_a):
                    if isinstance(orig, list) and isinstance(new_val, list):
                        orig.clear()
                        orig.extend(new_val)
                    elif isinstance(orig, dict) and isinstance(new_val, dict):
                        orig.clear()
                        orig.update(new_val)
            if "k" in reply:
                new_k = ast.literal_eval(reply["k"])
                for key, orig in kwargs.items():
                    if key in new_k:
                        new_val = new_k[key]
                        if isinstance(orig, list) and isinstance(new_val, list):
                            orig.clear()
                            orig.extend(new_val)
                        elif isinstance(orig, dict) and isinstance(new_val, dict):
                            orig.clear()
                            orig.update(new_val)
            return ast.literal_eval(reply["ok"])  # plain data only: no child-defined object reaches an assert
        except (ValueError, SyntaxError, TypeError):
            raise TypeError(name + " returned a value that is not a Python literal: " + str(reply["ok"])[:80])
    call.__name__ = name
    return call


def _finish(payload, code):
    try:
        _worker.stdin.close()
    except OSError:
        pass
    try:
        _worker.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        _worker.kill()
        _worker.wait()
    _stderr_file.close()
    if payload is None:
        with open("_worker_stderr.txt", "rb") as handle:
            sys.stderr.write(handle.read()[-2000:].decode("utf-8", "replace"))
    else:
        if "peak_ram_mb" in payload:
            import resource
            rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
            payload["peak_ram_mb"] = rss / (1024.0 * 1024.0) if sys.platform == "darwin" else rss / 1024.0
        sys.stdout.write("\n" + _NONCE + " " + json.dumps(payload) + "\n")
        sys.stdout.flush()
    sys.exit(code)


try:
    _hello = _recv()
    if "ready" not in _hello:
        raise _WorkerFailure("component failed to load: " + str(_hello.get("fatal")))
    _names = [str(n) for n in _hello["ready"]]
except (_WorkerFailure, TypeError) as _exc:
    sys.stderr.write("anse driver: " + str(_exc) + "\n")
    _finish(None, 0)

if _MODE == "tests":
    _scope = {name: _proxy(name) for name in _names}
    _failures = []
    import copy
    for _test in _TESTS:
        try:
            if isinstance(_test, str):
                exec(_test, _scope)
            else:
                _call = _test["call"]
                _args = _test.get("args", [])
                _kwargs = _test.get("kwargs", {})
                _args_copy = copy.deepcopy(_args)
                _kwargs_copy = copy.deepcopy(_kwargs)
                _func = _scope[_call]
                
                if "raises" in _test:
                    try:
                        _func(*_args, **_kwargs)
                        raise AssertionError("Expected " + _test["raises"] + ", but no exception was raised")
                    except Exception as _e:
                        if type(_e).__name__ != _test["raises"]:
                            raise AssertionError("Expected " + _test["raises"] + ", but got " + type(_e).__name__)
                else:
                    _res = _func(*_args, **_kwargs)
                    if "expect" in _test:
                        _exp = _test["expect"]
                        if type(_res) is not type(_exp) or _res != _exp:
                            raise AssertionError("Expected " + repr(_exp) + " (type " + type(_exp).__name__ + "), got " + repr(_res) + " (type " + type(_res).__name__ + ")")
                
                if _test.get("args_unchanged"):
                    if _args != _args_copy or _kwargs != _kwargs_copy:
                        raise AssertionError("Arguments were mutated")
        except Exception as _exc:
            _desc = str(_test).strip()
            _failures.append((_desc + " -> " + type(_exc).__name__ + ": " + str(_exc))[:300])
    _finish({"passed": len(_TESTS) - len(_failures), "total": len(_TESTS),
             "failures": _failures[:_MAX_FAILURES]}, 0)

if _MODE == "calls":
    _outcomes = []
    for _name, _args in _CALLS:
        try:
            _reply = _request({"op": "call", "name": _name, "args": repr(tuple(_args)), "kwargs": "{}"})
            _outcomes.append("ok " + str(_reply["ok"])[:_MAX_CHARS] if "ok" in _reply
                             else "raised " + str(_reply.get("error")))
        except _WorkerFailure as _exc:
            _outcomes.append("failed " + str(_exc))
    _finish({"outcomes": _outcomes}, 0)

try:
    _started = time.perf_counter()
    _reply = _request({"op": "exec", "code": _WORKLOAD, "var": _RESULT_VARIABLE})
    _elapsed_ms = (time.perf_counter() - _started) * 1000.0
    if "ok" not in _reply:
        raise _WorkerFailure("benchmark raised " + str(_reply.get("error")) + ": " + str(_reply.get("message")))
except _WorkerFailure as _exc:
    sys.stderr.write("anse driver: " + str(_exc) + "\n")
    _finish(None, 0)
_finish({"output": str(_reply["ok"])[:_MAX_CHARS], "duration_ms": _elapsed_ms, "peak_ram_mb": 0.0}, 0)
'''


def build_driver(
    nonce: str,
    component: str,
    budget_seconds: float,
    *,
    tests: list[dict] | None = None,
    workload: str | None = None,
    calls: list[tuple[str, list[Any]]] | None = None,
) -> str:
    """
    The sandbox script for one verification run: exactly one of *tests* (hidden tests),
    *workload* (timed benchmark) or *calls* (``(function, args)`` pairs to evaluate) is given.
    See the module docstring for why the component is not simply appended to the checks.
    """
    given = [
        name
        for name, value in (("tests", tests), ("workload", workload), ("calls", calls))
        if value is not None
    ]
    if len(given) != 1:
        raise ValueError(f"exactly one of tests/workload/calls is required, got {given or 'none'}")
    header = {
        "_NONCE": nonce,
        "_COMPONENT": component,
        "_WORKER": _WORKER_SOURCE,
        "_BUDGET_SECONDS": float(budget_seconds),
        "_MODE": given[0],
        "_TESTS": list(tests or []),
        "_WORKLOAD": workload or "",
        "_CALLS": [(name, list(args)) for name, args in (calls or [])],
        "_RESULT_VARIABLE": RESULT_VARIABLE,
        "_MAX_CHARS": _MAX_RESULT_CHARS,
        "_MAX_FAILURES": _MAX_REPORTED_FAILURES,
    }
    return "".join(f"{name} = {value!r}\n" for name, value in header.items()) + _DRIVER_BODY


def trusted_payload(result: ExecutionResult, nonce: str) -> str | None:
    """
    The driver's report line, or None when the run cannot be trusted: it timed out, did not exit 0,
    or the nonce-tagged report is not the LAST line on stdout (something else wrote after it).
    """
    if result.timed_out or result.returncode != 0:
        return None
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines or not lines[-1].startswith(nonce + " "):
        return None
    return lines[-1]
