"""
Hidden-test harness: independent verification of generated code.

The model never sees these tests up front. They are appended to the candidate
solution, run inside the sandbox, and reported on a nonce-tagged stdout line so
the candidate cannot forge its own report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

_MAX_REPORTED_FAILURES = 3

_HARNESS_TEMPLATE = """

def __anse_run_hidden_tests():
    import json as _json
    _tests = {tests!r}
    _failures = []
    for _test in _tests:
        try:
            exec(_test, globals())
        except BaseException as _exc:
            _failures.append((_test.strip() + " -> " + type(_exc).__name__ + ": " + str(_exc))[:300])
    print("{nonce} " + _json.dumps({{
        "passed": len(_tests) - len(_failures),
        "total": len(_tests),
        "failures": _failures[:{max_failures}],
    }}))


__anse_run_hidden_tests()
"""


@dataclass(frozen=True)
class TestReport:
    __test__ = False  # not a pytest class

    passed: int
    total: int
    failures: list[str] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.passed == self.total


def attach_harness(code: str, tests: list[str], nonce: str) -> str:
    """Return *code* with a harness appended that runs *tests* and prints a nonce-tagged report."""
    return code + _HARNESS_TEMPLATE.format(
        tests=list(tests), nonce=nonce, max_failures=_MAX_REPORTED_FAILURES
    )


def parse_report(stdout: str, nonce: str) -> TestReport | None:
    """Parse the last nonce-tagged report line in *stdout*; None if the harness never ran."""
    for line in reversed(stdout.splitlines()):
        if not line.startswith(nonce + " "):
            continue
        try:
            data = json.loads(line[len(nonce) + 1 :])
            return TestReport(
                passed=int(data["passed"]),
                total=int(data["total"]),
                failures=[str(f) for f in data["failures"]],
            )
        except (ValueError, KeyError, TypeError):
            return None
    return None


def strip_report(stdout: str, nonce: str) -> str:
    """Remove harness report lines so they do not pollute stdout-based energy heuristics."""
    kept = [line for line in stdout.splitlines() if not line.startswith(nonce + " ")]
    return "\n".join(kept)
