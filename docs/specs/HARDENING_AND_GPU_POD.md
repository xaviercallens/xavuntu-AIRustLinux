# Spec: security hardening and remote GPU pod (RunPod)

Audience: an autonomous coding agent (Antigravity) working on branch `antigravity`.
Status: proposal accepted by the owner; nothing below is implemented yet.
Language of code and docs: English. Follow `.antigravity/rules.md` (especially section 8) and `.agents/AGENTS.md`.

## 0. Why

Three facts, each verified in the code on 2026-09-21:

1. The Phase 1 hidden-test harness (`anse/symbolic/hidden_tests.py: attach_harness`) is appended to the candidate's own source and runs in the same process. Code that reads its own `__file__` finds the nonce and can print a forged all-passed report. Phase 3 already fixed this with an out-of-process trusted driver (`anse/autopoiesis/hypervisor.py`: `build_driver`, `trusted_payload`, `_run_driver`, `differential_test`); Phase 1 has not adopted it.
2. When code imports a blocklisted module and Docker is unavailable, `anse/symbolic/sandbox.py` (around line 256-260) silently falls back to Tier 1, which has no filesystem or network isolation. The blocklist is bypassable (`__import__`, `importlib`), so it is not a security boundary. Docker is not installed on the development machine.
3. `anse/core/encoder.py` (lines 113, 125, 134) loads models with `trust_remote_code=True` and `revision="main"`: unpinned remote code execution. On a GPU pod this would run with the pod's privileges.

Goal: make it safe to (a) train or fine-tune against the hidden-test harness, and (b) run the evolution benchmarks with a 7B model on a rented GPU, without ever executing model-generated code on the GPU host.

## 1. Baseline (record before changing anything)

```bash
uv sync --all-extras
uv run pytest tests/phase1 tests/phase2 tests/phase3 tests/autopoiesis tests/web tests/performance -q -p no:cacheprovider
uv run python test_rigor_guard.py
uv run python antigravity_guard.py
```

Expected on 2026-09-21: at least 443 tests pass (before `--all-extras` some test files could not import); rigor guard passes 53 files; `antigravity_guard.py` should report no hallucinated imports once all extras are installed (it reported 24 before). If `uv sync` fails, stop and report; do not edit `uv.lock` by hand.

Store the output tails in the PR description of each work package (WP).

## 2. Architecture decision: where things run

| Component | Runs on | Why |
|---|---|---|
| Code, git, Antigravity, Claude Code | developer machine | secrets and review stay local |
| Sandbox that executes model-generated code (Tier 2 container) | developer machine (or another disposable host) | RunPod pods are themselves containers; nested Docker is very likely unavailable there. Verify in RunPod's docs, but design as if it is. |
| LLM inference and hidden-state extraction, later LoRA/GRPO training | RunPod pod | needs the GPU |

Rule: the pod never executes model-generated code and holds no repository secret. The pod returns text and vectors; the local machine verifies.

## 3. Work packages

Order: WP1, WP2, WP3 are independent (parallelizable, one commit each). WP5, WP6, WP7 follow. WP4 (pod) depends on WP3. One commit per WP on branch `antigravity`; never force-push; never use `--no-verify`.

### WP0 - Owner prerequisites (not for the agent; the agent must check and stop with a clear message if missing)

- Docker Engine installed locally and usable by the current user (`docker info` works). Currently absent.
- `uv sync --all-extras` run once.
- RunPod account with a spend limit configured in the account settings, an SSH keypair dedicated to the pod, and the RunPod API key stored in the git-ignored `.env`. Never print or read `.env` contents in logs. Prefer Secure Cloud over Community Cloud because prompts and code transit the host.

### WP1 - Out-of-process hidden-test harness for Phase 1

Problem: see 0.1. Also note the current tests are strings executed with `exec` in the candidate's namespace, which allows checks such as "the input list was not modified" (`median`, `merge_intervals`, `second_largest` in `tasks/phase1_evolution.yaml`). A trusted driver that sends arguments over a pipe cannot express those as free-form asserts.

Required behaviour:
1. Extract the trusted driver from `hypervisor.py` into a shared module `anse/symbolic/trusted_driver.py`; `hypervisor.py` imports it. No behaviour change for Phase 3.
2. Phase 1 evaluation (`AgentLoop._execute`, `run_phase1_evolution.py: verify`) uses the trusted driver. `attach_harness` remains only for the documented forgery control test.
3. New declarative test-case format in the task YAML, replacing free-form assert strings:
   ```yaml
   tests:
     - {call: "rotate_list", args: [[1,2,3,4,5], 2], expect: [4,5,1,2,3]}
     - {call: "chunk_list", args: [[1], 0], raises: "ValueError"}
     - {call: "median", args: [[3,1,2]], expect: 2, args_unchanged: true}
   ```
   `expect` compares with `==` plus exact type equality for bool/int/str/list/dict; `raises` matches the exception type name; `args_unchanged` compares the arguments after the call with a pre-call deep copy, both inside the driver. Values must be Python literals (`ast.literal_eval`-able).
4. Migrate all 20 tasks. Every reference solution must still pass 100% of its tests (existing test `tests/phase1/test_evolution_suite.py` must be adapted, not weakened). Keep one test per original behaviour; do not drop cases.
5. `EnergyEvaluator.evaluate_hidden_tests` keeps graded energy `50 * failed / total`.
6. The model must never see test cases (system prompt unchanged).

Acceptance tests (new, in `tests/phase1/`):
- A candidate that opens `__file__` and prints a forged report scores its honest fraction, never 100%.
- A candidate that returns an object with `__eq__` always True fails `expect` (type check).
- A candidate that mutates its argument fails `args_unchanged`.
- A candidate that calls `os._exit(0)` or `sys.exit(0)` before tests yields "tests never ran" energy 50, not a pass.
- All 20 reference solutions pass; a deliberately wrong solution per family scores less than 100%.

Definition of done: the Phase 1 runner works end to end on a 2-task smoke run against the local Ollama model, and `docs/EVOLUTION_LAB.md` "Known limitations" no longer lists the Phase 1 forgery weakness.

### WP2 - Fail-closed sandbox

Required behaviour:
1. `SandboxConfig` gains `tier1_fallback: Literal["deny", "allow_with_warning"] = "deny"` and `untrusted_requires_container: bool = True`.
2. `SandboxExecutor.execute(code, trusted=False)`: model-generated code (`trusted=False`) must run in a container. If Docker is unavailable and policy is `deny`, return an `ExecutionResult` with `returncode=-1`, `stderr="SANDBOX_UNAVAILABLE: ..."`, a new field `isolation="none"`, and category energy at the maximum (never PASS, never crash the loop). Only code written by the repository itself (references, hand-written children, Phase 3 registry payloads) may pass `trusted=True` and use Tier 1.
3. `ExecutionResult.isolation` is `"process"` (Tier 1) or `"container"` (Tier 2) and is recorded in every trace's metadata and in `results.json` rows.
4. Harden the Tier 2 container. Verify each docker-py kwarg against the installed docker-py source before use; earlier review flagged `cpu_count` as Windows-only and `timeout` as not a valid argument of `containers.run`. Target settings: network disabled, read-only root filesystem, `tmpfs` for `/tmp` with `noexec`, non-root user, `cap_drop=["ALL"]`, `no-new-privileges`, PID limit, memory limit with swap equal to memory, CPU quota via `nano_cpus`, `remove=True`, image referenced by digest (`name@sha256:...`), no bind mounts other than the read-only code directory. Run detached and use `container.wait(timeout=...)` then kill on expiry; return real exit code and separated stdout/stderr (today a non-zero exit is reported as `returncode=-1` with empty stdout). Catch `docker.errors.DockerException` (not only `OSError`) around `docker.from_env()`.
5. Add `Dockerfile.sandbox` (slim Python base pinned by digest, non-root user, no network tools, numpy only) and `scripts/build_sandbox.sh` that prints the resulting digest to paste into config.
6. The AST import blocklist stays as a triage signal only. Rewrite its docstring and `docs` to say it is not a security boundary.

Acceptance tests:
- Docker-dependent tests carry `@pytest.mark.docker` and are reported as SKIPPED with an explicit reason when Docker is absent. They are never silently passing. A separate CI/manual step must run them where Docker exists.
- Without Docker: model-generated code returns `SANDBOX_UNAVAILABLE` and the agent loop finishes without exception (extend the UC5 robustness scenarios).
- With Docker: code that tries to read `/etc/passwd`-adjacent host files outside the mount, open a socket, write outside `/tmp`, fork-bomb, or allocate above the limit is contained and reported; the host is unaffected.
- Audit the existing test suite for tests that relied on the silent fallback; fix them by passing `trusted=True` where the code is repository-authored, not by changing policy.

### WP3 - Supply chain

1. `ModelConfig` gains `model_revision: str` (required, must match `^[0-9a-f]{40}$`) and `trust_remote_code: bool = False`. `encoder.py` refuses to load when the revision is missing, `main` or `master`. Qwen2.5-Coder loads natively in `transformers`, so remote code should not be needed; if a chosen model needs it, document the exact reviewed commit instead.
2. Verify the real `hidden_size` from the model's `config.json` and fix `ModelConfig.hidden_dim` (it is 4096; Qwen2.5-Coder-7B is likely 3584). Add a startup assertion that the extracted vector length equals the configured `hidden_dim`.
3. Dockerfiles (`Dockerfile.gateway`, `Dockerfile.trainer`) install from the lock: `uv export --frozen --no-dev` with hashes and `pip install --require-hashes`, or `uv sync --frozen`. No unpinned `pip install fastapi uvicorn ...`.
4. `scripts/audit.sh`: `uv run pip-audit`, `uv run bandit -r anse -ll`, `uv run vulture anse --min-confidence 80`; wire it into `.pre-commit-config.yaml` (advisory locally, blocking in the release checklist).
5. On any machine that downloads models: prefetch at the pinned revision, then run with `HF_HUB_OFFLINE=1`.

Acceptance: a test proving `encoder` rejects `revision="main"` and a missing revision; `uv sync --frozen` works from a clean checkout.

### WP4 - RunPod GPU pod (inference and later training)

Read RunPod's current documentation before writing any provider-specific code; do not guess endpoints, CLI flags or template fields. Do not hard-code prices.

Deliverables:
1. `pod/README.md`: the runbook (choose Secure Cloud; a 24 GB GPU class is enough for 7B fp16 inference and hidden states, 48 GB only for GRPO; attach a network volume for model weights; open only the SSH TCP port; no public HTTP port).
2. `pod/bootstrap.sh`, idempotent: check `nvidia-smi`; clone the repository with a read-only deploy key (or `git archive` pushed from the developer machine); `uv sync --frozen --extra training`; prefetch the model at the pinned revision to the volume; write `pod.env`; start services below. Must not require any secret other than the inference API key generated locally and passed at launch.
3. `pod/inference_server.py`: a small FastAPI app that loads the model with `transformers` (reuse `HiddenStateExtractor` internals), binds `127.0.0.1` only, requires a bearer token, and exposes `GET /health` and `POST /generate` returning `{text, hidden_state: list[float], token_count, model_id, model_revision, seed}`. No endpoint may execute code or shell commands; add a test that scans the app's routes for this.
4. For plain generation at speed, `vllm serve <model> --revision <sha> --host 127.0.0.1 --port 8000 --api-key <token>` (verify flags against the vLLM version pinned in the lock). Adapters for later LoRA work go through the existing `vllm_reloader.py`.
5. Local side: `APIExtractor` gains `backend="pod"` (calls `/generate`, so Phase 1 traces contain true last-token hidden states instead of an embedding of the reply text) and keeps `ollama_native`. The sampling seed is passed through; a start-up check confirms two seeds give two samples.
6. `scripts/pod.sh` with subcommands `tunnel` (`ssh -N -L 8000:127.0.0.1:8000 -i ~/.ssh/<pod key> ...`), `status`, `run <phase>` (runs the chosen `run_phase*_evolution.py` locally against the tunnelled endpoint), `sync-results` (rsync over ssh into a quarantine directory, then WP5 verification before anything lands in `results/`), and `down`.
7. Cost control: the owner sets the spend cap in the RunPod account (WP0). `pod.sh run` refuses to start if the pod has been up longer than a configurable number of hours without activity, and `down` is the documented end of every session. Any pod-side idle shutdown that needs a RunPod API key must use a key scoped as narrowly as the provider allows; otherwise keep the timer local.
8. Extend `restart.sh` with `pod-tunnel`, `pod-run`, `pod-sync` that call `scripts/pod.sh`.

Security acceptance: the pod holds no `.env`, no write token, no RunPod account-level key; the inference server is unreachable from outside the SSH tunnel; the runbook states that generated code is executed only by the local sandbox.

Definition of done: Phase 1 smoke run (2 tasks, 2 seeds) through the tunnel with a 7B model produces traces whose `hidden_state` length equals `ModelConfig.hidden_dim`; then a full Phase 1 run is executed for real, and Phase 2 is re-run on those traces.

### WP5 - Result provenance

1. Every runner writes `results.json["provenance"]`: `git_commit`, `git_dirty` (bool), `runner_sha256`, `tasks_sha256`, `uv_lock_sha256`, `model_id`, `model_revision`, `backend` (`ollama_native` | `pod` | ...), `isolation` counts per tier, `seeds_honoured_by_backend`, `python`, `started`, `finished`.
2. `scripts/verify_results.py` recomputes the hashes and exits non-zero on mismatch or missing fields; `web/evolution_data.py` shows "unverified" (never hides the results) when provenance is missing or does not match the working tree.
3. Results that arrive through `pod.sh sync-results` are validated against the same schema before being moved into `results/`.

### WP6 - Gates and attestation

1. `.pre-commit-config.yaml`: run `test_rigor_guard.py`, `antigravity_guard.py` and a fast test subset; keep `--no-verify` forbidden.
2. `tests/phase3/test_neuro_surgeon.py` currently rewrites the tracked file `.antigravity_attestation` (via `execution_attestation.generate_attestation_proof`, called from `anse/autopoiesis/neuro_surgeon.py` lines 173 and 437). Add an `ANSE_ATTESTATION_PATH` override and an autouse fixture in `tests/conftest.py` pointing it at `tmp_path`. After this, `git status` is clean after a full test run (add a test or CI step that asserts this).
3. Bind the attestation proof token to the SHA-256 of the staged diff and to the test-run summary, so a token cannot be replayed on different code.
4. Mutation testing (`check_mutants.sh`, mutmut) scoped to `anse/symbolic/hidden_tests.py`, `anse/symbolic/trusted_driver.py`, `anse/autopoiesis/hypervisor.py` and `anse/autopoiesis/registry.py`; surviving mutants must be killed or justified with `# pragma: no mutate`.

### WP7 - Training-data hygiene and reward-hacking detection

1. `export_training_data.py` and `extract_dpo_pairs.py` accept only traces whose metadata contains `tests_total` and whose energy is 0 (positives) or a verified failure (negatives). Traces from the legacy self-graded loop (`traces_uc1_legacy.jsonl`) are never used.
2. Private hold-out: `tasks/private/` (git-ignored) with the same YAML format, located through `ANSE_PRIVATE_TASKS`. The runners report the gap between public-suite and private-suite pass rates as `provenance` metadata and as a gate: a gap above a configured threshold is a reward-hacking flag. Document how to create the private set; do not commit it.
3. Any future GRPO/LoRA reward must be computed by the trusted driver (WP1), never by in-process asserts.

### WP8 - Storage hardening and Redis schema partitioning

1. Discovered vulnerability: `gateway.py`, `mcp_guard_server.py`, and `antigravity_harness` co-write incompatible payloads to `antigravity:trace:*`, causing unhandled deserialization crashes in `TraceRecord.from_dict()`.
2. Partition Redis namespaces:
   - `antigravity:harness:trace:{trace_id}` for DPO/RL pipeline traces
   - `antigravity:gateway:trace:{event_id}` for API Gateway ingress audit traces
   - `antigravity:ltm:lesson:{task_id}` for Long-Term Memory
3. Strong typing and schema versioning: `TraceRecord` gains `schema_version: int = 2` and Pydantic discriminated union decoding.
4. Quarantine dead-letter pattern: unparseable trace keys are moved to `antigravity:quarantine:{id}` with error metadata rather than silently ignored or terminating the harvester.

### WP9 - Long-Term Lesson Memory (LTM) quality gates & negative-transfer mitigation

1. Discovered vulnerability: non-monotonic retry loops previously stored degraded code into `LessonMemory`, and injecting multi-shot lessons into sub-3B parameter models (Phase 1 UC4) caused pass@1 to regress from 33.3% to 22.2%.
2. Implement Gate-Before-Store contract in `anse/memory/lessons.py`:
   - 100% passed hidden tests required
   - Energy below strict cap ($E < 35.0$)
   - Anti-stub AST validation (no `ast.Pass`, no placeholder docstrings)
3. Model capability gate: automatically suppress lesson prompt injection for models < 3B parameters unless explicitly enabled.
4. Typed vector store with strict dimension checking: replace silent vector dropouts in `redis_bus.py: search_vectors` with validated index shapes.

## 4. Guardrails for the implementing agent

- Do not move a gate threshold, edit a `results.json`, or choose seeds to obtain a pass. A failing gate is a result.
- Do not edit `.claude/`, `.mcp.json` or `CLAUDE.md` unless the owner asks; those belong to the Claude Code environment.
- Do not read or print `.env`. Reference secret names only.
- Do not run `uv sync` against a `pyproject.toml` without a `[project]` table (it would uninstall the environment).
- Every WP ends with: tests for the new behaviour (at least two real assertions each, no mocking of `anse.*` internals), `test_rigor_guard.py`, `antigravity_guard.py`, the baseline command from section 1, and an update to `docs/EVOLUTION_LAB.md` and `memory.md`.
- Report only real command output.

## 5. Not verified by the author of this spec

Treat as questions to answer first, then record the answer in the WP's PR:

- Docker is absent locally (verified); everything about Tier 2 behaviour (docker-py kwargs, digests, tmpfs options) is untested here.
- RunPod specifics (nested Docker unavailability, SSH TCP port exposure, stop/terminate API, Secure vs Community isolation guarantees, volume behaviour) are from general knowledge, not from RunPod's current documentation.
- Qwen2.5-Coder-7B `hidden_size` (3584 assumed) and the vLLM flag set.
- Which existing tests silently depend on the Tier 1 fallback.
- Whether `execution_attestation.py` hard-codes its output path.
