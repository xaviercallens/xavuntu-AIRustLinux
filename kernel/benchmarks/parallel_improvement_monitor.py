#!/usr/bin/env python3
"""
Parallel Code Improvement Monitor with Checkpoint & Retry
Monitors multiple concurrent improvement processes with GitHub integration
"""

import asyncio
import json
import subprocess
import time
import os
import re
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import hashlib

@dataclass
class CheckpointState:
    """State saved at each checkpoint"""
    timestamp: str
    modules_completed: List[str]
    modules_failed: List[str]
    modules_pending: List[str]
    total_fixes: int
    total_errors: int
    elapsed_time_seconds: float
    git_commit_hash: Optional[str]

    def to_dict(self):
        return asdict(self)

@dataclass
class ImprovementMetrics:
    """Metrics for a single module improvement"""
    module_name: str
    initial_errors: int
    final_errors: int
    errors_fixed: int
    improvement_percent: float
    attempts: int
    success: bool
    duration_seconds: float
    model_used: str
    git_commit: Optional[str]

    def to_dict(self):
        return asdict(self)

@dataclass
class ComparisonMetrics:
    """Comparison with baseline (e.g., Mistral)"""
    metric_name: str
    current_value: float
    baseline_value: float
    improvement_percent: float
    better: bool

class ParallelImprovementMonitor:
    """Monitor parallel code improvement processes"""

    def __init__(self, workspace_root: str, max_parallel: int = 4):
        self.workspace_root = Path(workspace_root)
        self.checkpoint_dir = self.workspace_root / "benchmarks" / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        self.max_parallel = max_parallel
        self.max_retries = 3
        self.checkpoint_interval = 600  # 10 minutes

        self.current_state: Optional[CheckpointState] = None
        self.metrics: List[ImprovementMetrics] = []
        self.start_time = time.time()

        # Azure OpenAI Codex configuration
        self.azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT_1", "")
        self.azure_key = os.environ.get("AZURE_OPENAI_KEY_1", "")
        self.azure_deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_1", "gpt-5.3-codex")
        self.azure_api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")

        # Load previous checkpoint if exists
        self.load_checkpoint()

    def save_checkpoint(self):
        """Save current state to checkpoint file"""
        if not self.current_state:
            return

        checkpoint_file = self.checkpoint_dir / f"checkpoint_{int(time.time())}.json"
        with open(checkpoint_file, 'w') as f:
            json.dump(self.current_state.to_dict(), f, indent=2)

        # Also save as "latest"
        latest_file = self.checkpoint_dir / "checkpoint_latest.json"
        with open(latest_file, 'w') as f:
            json.dump(self.current_state.to_dict(), f, indent=2)

        print(f"💾 Checkpoint saved: {checkpoint_file.name}")

    def load_checkpoint(self) -> bool:
        """Load latest checkpoint if exists"""
        latest_file = self.checkpoint_dir / "checkpoint_latest.json"

        if not latest_file.exists():
            return False

        try:
            with open(latest_file, 'r') as f:
                data = json.load(f)

            self.current_state = CheckpointState(**data)
            print(f"📥 Loaded checkpoint from {data['timestamp']}")
            print(f"   Completed: {len(data['modules_completed'])} modules")
            print(f"   Failed: {len(data['modules_failed'])} modules")
            print(f"   Pending: {len(data['modules_pending'])} modules")
            return True

        except Exception as e:
            print(f"⚠️  Failed to load checkpoint: {e}")
            return False

    async def improve_module_with_retry(
        self,
        module_name: str,
        model: str = "gpt-5.3-codex"
    ) -> ImprovementMetrics:
        """Improve a single module with retry logic"""

        for attempt in range(1, self.max_retries + 1):
            print(f"🔧 {module_name} - Attempt {attempt}/{self.max_retries}")

            start_time = time.time()

            try:
                # Get initial error count
                initial_errors = await self.count_errors(module_name)

                # Run improvement (call to Codex)
                success = await self.run_codex_fix(module_name, model)

                # Get final error count
                final_errors = await self.count_errors(module_name) if success else initial_errors

                duration = time.time() - start_time

                # Calculate improvement
                errors_fixed = max(0, initial_errors - final_errors)
                improvement_percent = (errors_fixed / initial_errors * 100) if initial_errors > 0 else 0

                # Get git commit if successful
                git_commit = None
                if success and errors_fixed > 0:
                    git_commit = await self.commit_changes(module_name, errors_fixed)

                metrics = ImprovementMetrics(
                    module_name=module_name,
                    initial_errors=initial_errors,
                    final_errors=final_errors,
                    errors_fixed=errors_fixed,
                    improvement_percent=improvement_percent,
                    attempts=attempt,
                    success=success,
                    duration_seconds=duration,
                    model_used=model,
                    git_commit=git_commit
                )

                if success or attempt >= self.max_retries:
                    return metrics

                # Wait before retry (exponential backoff)
                await asyncio.sleep(2 ** attempt)

            except Exception as e:
                print(f"❌ {module_name} - Error on attempt {attempt}: {e}")

                if attempt >= self.max_retries:
                    return ImprovementMetrics(
                        module_name=module_name,
                        initial_errors=0,
                        final_errors=0,
                        errors_fixed=0,
                        improvement_percent=0,
                        attempts=attempt,
                        success=False,
                        duration_seconds=time.time() - start_time,
                        model_used=model,
                        git_commit=None
                    )

                await asyncio.sleep(2 ** attempt)

    async def count_errors(self, module_name: str) -> int:
        """Count compilation errors in a module"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "cargo", "build", "--package", module_name,
                cwd=self.workspace_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            _, stderr = await proc.communicate()
            error_lines = [line for line in stderr.decode().split('\n') if line.startswith('error[')]
            return len(error_lines)

        except Exception as e:
            print(f"⚠️  Error counting errors for {module_name}: {e}")
            return 0

    async def call_codex(self, prompt: str, max_tokens: int = 2000) -> Optional[str]:
        """Call Azure OpenAI Codex API"""
        try:
            headers = {
                "Content-Type": "application/json",
                "api-key": self.azure_key
            }

            payload = {
                "model": self.azure_deployment,
                "input": prompt,
                "max_tokens": max_tokens
            }

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{self.azure_endpoint}/openai/responses?api-version={self.azure_api_version}",
                    headers=headers,
                    json=payload,
                    timeout=120,
                    verify=False
                )
            )

            if response.status_code != 200:
                return None

            result = response.json()
            if result.get("output") and len(result["output"]) > 0:
                content = result["output"][0].get("content", [])
                if content and len(content) > 0:
                    return content[0].get("text", "")

            return None

        except Exception as e:
            print(f"⚠️  Codex API error: {e}")
            return None

    async def run_codex_fix(self, module_name: str, model: str) -> bool:
        """Run Codex fix on a module"""
        try:
            module_path = self.workspace_root / "crates" / module_name / "src" / "lib.rs"

            if not module_path.exists():
                return False

            # Read current code
            code = module_path.read_text()

            # Get compilation errors
            proc = await asyncio.create_subprocess_exec(
                "cargo", "build",
                cwd=module_path.parent.parent,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await proc.communicate()
            errors = stderr.decode()

            if "error" not in errors.lower():
                return True  # Already compiles

            # Extract first 5 errors
            error_lines = [line for line in errors.split('\n') if 'error[E' in line][:5]
            error_summary = '\n'.join(error_lines)

            # Build prompt
            prompt = f"""You are an expert Rust systems programmer fixing Linux kernel networking code translation errors.

Current code has these compilation errors:
{error_summary}

Full error output:
{errors[:2000]}

Current code excerpt (first 100 lines):
```rust
{''.join(code.split(chr(10))[:100])}
```

Please provide ONLY the corrected Rust code that fixes these errors. Do not include explanations, just the fixed code wrapped in ```rust blocks."""

            # Call Codex
            fixed_code = await self.call_codex(prompt, max_tokens=4000)

            if not fixed_code:
                return False

            # Extract code from response
            code_match = re.search(r'```rust\n(.*?)```', fixed_code, re.DOTALL)
            if code_match:
                new_code = code_match.group(1)
                module_path.write_text(new_code)
                return True

            return False

        except asyncio.TimeoutError:
            print(f"⏱️  {module_name} - Timeout after 5 minutes")
            return False
        except Exception as e:
            print(f"❌ {module_name} - Fix failed: {e}")
            return False

    async def commit_changes(self, module_name: str, errors_fixed: int) -> Optional[str]:
        """Commit changes for a module"""
        try:
            # Stage changes
            await asyncio.create_subprocess_exec(
                "git", "add", f"crates/{module_name}/src/lib.rs",
                cwd=self.workspace_root
            )

            # Commit
            commit_msg = f"Fix {errors_fixed} compilation errors in {module_name}\n\nAuto-fixed by Azure Codex GPT-5.3\n\nCo-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

            proc = await asyncio.create_subprocess_exec(
                "git", "commit", "-m", commit_msg,
                cwd=self.workspace_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            await proc.wait()

            # Get commit hash
            proc = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "HEAD",
                cwd=self.workspace_root,
                stdout=asyncio.subprocess.PIPE
            )

            stdout, _ = await proc.communicate()
            return stdout.decode().strip()[:8]

        except Exception as e:
            print(f"⚠️  Failed to commit {module_name}: {e}")
            return None

    async def monitor_progress(self):
        """Monitor progress every 10 minutes"""
        while True:
            await asyncio.sleep(self.checkpoint_interval)

            if not self.current_state:
                continue

            elapsed = time.time() - self.start_time
            completed = len(self.current_state.modules_completed)
            total = completed + len(self.current_state.modules_pending) + len(self.current_state.modules_failed)

            progress = (completed / total * 100) if total > 0 else 0

            print(f"\n{'='*80}")
            print(f"📊 PROGRESS UPDATE - {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'='*80}")
            print(f"⏱️  Elapsed: {elapsed/60:.1f} minutes")
            print(f"✅ Completed: {completed}/{total} ({progress:.1f}%)")
            print(f"❌ Failed: {len(self.current_state.modules_failed)}")
            print(f"⏳ Pending: {len(self.current_state.modules_pending)}")
            print(f"🔧 Total Fixes: {self.current_state.total_fixes}")
            print(f"🐛 Remaining Errors: {self.current_state.total_errors}")

            # Save checkpoint
            self.save_checkpoint()

            # Generate interim report
            await self.generate_interim_report()

    async def generate_interim_report(self):
        """Generate interim progress report"""
        if not self.metrics:
            return

        report_file = self.workspace_root / "benchmarks" / "results" / f"interim_report_{int(time.time())}.md"

        successful = [m for m in self.metrics if m.success]
        failed = [m for m in self.metrics if not m.success]

        avg_improvement = sum(m.improvement_percent for m in successful) / len(successful) if successful else 0
        total_errors_fixed = sum(m.errors_fixed for m in successful)

        report = f"""# Parallel Improvement - Interim Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Elapsed Time:** {(time.time() - self.start_time)/60:.1f} minutes

## Progress Summary

- **Modules Processed:** {len(self.metrics)}
- **Successful:** {len(successful)}
- **Failed:** {len(failed)}
- **Success Rate:** {len(successful)/len(self.metrics)*100:.1f}%

## Quality Metrics

- **Total Errors Fixed:** {total_errors_fixed}
- **Average Improvement:** {avg_improvement:.1f}%
- **Avg Duration:** {sum(m.duration_seconds for m in self.metrics)/len(self.metrics):.1f}s per module

## Top Improvements

| Module | Errors Fixed | Improvement | Duration |
|--------|--------------|-------------|----------|
"""

        for m in sorted(successful, key=lambda x: x.errors_fixed, reverse=True)[:10]:
            report += f"| {m.module_name} | {m.errors_fixed} | {m.improvement_percent:.1f}% | {m.duration_seconds:.1f}s |\n"

        report += "\n## Next Checkpoint\n\n"
        report += f"- Expected: {datetime.now() + timedelta(seconds=self.checkpoint_interval)}\n"
        report += f"- Remaining modules: {len(self.current_state.modules_pending) if self.current_state else 0}\n"

        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report)

        print(f"📝 Interim report: {report_file.name}")

    async def compare_with_baseline(self, baseline_file: Path) -> List[ComparisonMetrics]:
        """Compare current results with baseline (e.g., Mistral)"""
        if not baseline_file.exists():
            print(f"⚠️  Baseline file not found: {baseline_file}")
            return []

        try:
            with open(baseline_file, 'r') as f:
                baseline_data = json.load(f)

            comparisons = []

            # Calculate current metrics
            successful = [m for m in self.metrics if m.success]
            current_success_rate = len(successful) / len(self.metrics) * 100 if self.metrics else 0
            current_avg_improvement = sum(m.improvement_percent for m in successful) / len(successful) if successful else 0
            current_total_fixes = sum(m.errors_fixed for m in successful)
            current_avg_duration = sum(m.duration_seconds for m in self.metrics) / len(self.metrics) if self.metrics else 0

            # Compare with baseline
            baseline_success_rate = baseline_data.get('success_rate', 0)
            baseline_avg_improvement = baseline_data.get('avg_improvement', 0)
            baseline_total_fixes = baseline_data.get('total_fixes', 0)
            baseline_avg_duration = baseline_data.get('avg_duration', 0)

            comparisons.append(ComparisonMetrics(
                metric_name="Success Rate",
                current_value=current_success_rate,
                baseline_value=baseline_success_rate,
                improvement_percent=(current_success_rate - baseline_success_rate),
                better=(current_success_rate > baseline_success_rate)
            ))

            comparisons.append(ComparisonMetrics(
                metric_name="Avg Improvement",
                current_value=current_avg_improvement,
                baseline_value=baseline_avg_improvement,
                improvement_percent=(current_avg_improvement - baseline_avg_improvement),
                better=(current_avg_improvement > baseline_avg_improvement)
            ))

            comparisons.append(ComparisonMetrics(
                metric_name="Total Fixes",
                current_value=current_total_fixes,
                baseline_value=baseline_total_fixes,
                improvement_percent=((current_total_fixes - baseline_total_fixes) / baseline_total_fixes * 100) if baseline_total_fixes > 0 else 0,
                better=(current_total_fixes > baseline_total_fixes)
            ))

            comparisons.append(ComparisonMetrics(
                metric_name="Avg Duration (s)",
                current_value=current_avg_duration,
                baseline_value=baseline_avg_duration,
                improvement_percent=((baseline_avg_duration - current_avg_duration) / baseline_avg_duration * 100) if baseline_avg_duration > 0 else 0,
                better=(current_avg_duration < baseline_avg_duration)
            ))

            return comparisons

        except Exception as e:
            print(f"❌ Failed to load baseline: {e}")
            return []

    async def generate_final_report(self, baseline_file: Optional[Path] = None):
        """Generate final comprehensive report"""
        successful = [m for m in self.metrics if m.success]
        failed = [m for m in self.metrics if not m.success]

        total_duration = time.time() - self.start_time

        report = f"""# Parallel Code Improvement - Final Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Total Duration:** {total_duration/60:.1f} minutes
**Model:** Azure OpenAI GPT-5.3-codex

---

## Executive Summary

### Overall Results

| Metric | Value |
|--------|-------|
| **Total Modules** | {len(self.metrics)} |
| **Successful** | {len(successful)} ({len(successful)/len(self.metrics)*100:.1f}%) |
| **Failed** | {len(failed)} ({len(failed)/len(self.metrics)*100:.1f}%) |
| **Total Errors Fixed** | {sum(m.errors_fixed for m in successful)} |
| **Avg Improvement** | {sum(m.improvement_percent for m in successful)/len(successful):.1f}% if successful else 0.0% |
| **Total Commits** | {len([m for m in successful if m.git_commit])} |

### Performance

| Metric | Value |
|--------|-------|
| **Total Duration** | {total_duration/60:.1f} minutes |
| **Avg per Module** | {total_duration/len(self.metrics):.1f} seconds |
| **Throughput** | {len(self.metrics)/(total_duration/3600):.1f} modules/hour |
| **Retry Rate** | {sum(m.attempts - 1 for m in self.metrics)/len(self.metrics):.2f} retries/module |

---

## Detailed Results

### Top 20 Improvements

| Rank | Module | Errors Fixed | Improvement % | Duration | Attempts | Commit |
|------|--------|--------------|---------------|----------|----------|--------|
"""

        for i, m in enumerate(sorted(successful, key=lambda x: x.errors_fixed, reverse=True)[:20], 1):
            commit_short = m.git_commit or "N/A"
            report += f"| {i} | {m.module_name} | {m.errors_fixed} | {m.improvement_percent:.1f}% | {m.duration_seconds:.1f}s | {m.attempts} | {commit_short} |\n"

        report += "\n### Failed Modules\n\n"
        report += "| Module | Initial Errors | Attempts | Duration |\n"
        report += "|--------|----------------|----------|----------|\n"

        for m in sorted(failed, key=lambda x: x.initial_errors, reverse=True):
            report += f"| {m.module_name} | {m.initial_errors} | {m.attempts} | {m.duration_seconds:.1f}s |\n"

        # Add baseline comparison if available
        if baseline_file:
            comparisons = await self.compare_with_baseline(baseline_file)

            if comparisons:
                report += "\n---\n\n## Baseline Comparison (vs Mistral)\n\n"
                report += "| Metric | Current (GPT-5.3) | Baseline (Mistral) | Δ | Better? |\n"
                report += "|--------|-------------------|---------------------|---|--------|\n"

                for comp in comparisons:
                    delta_symbol = "+" if comp.improvement_percent >= 0 else ""
                    better_symbol = "✅" if comp.better else "❌"
                    report += f"| {comp.metric_name} | {comp.current_value:.1f} | {comp.baseline_value:.1f} | {delta_symbol}{comp.improvement_percent:.1f}% | {better_symbol} |\n"

        report += "\n---\n\n## Git Integration\n\n"
        report += f"**Total Commits:** {len([m for m in successful if m.git_commit])}\n\n"
        report += "```bash\n"
        report += "# Push all changes\n"
        report += "git push origin master\n\n"
        report += "# View commit history\n"
        report += f"git log --oneline -n {len([m for m in successful if m.git_commit])}\n"
        report += "```\n"

        report += "\n---\n\n## Recommendations\n\n"

        if len(failed) > 0:
            report += f"1. ⚠️  **{len(failed)} modules failed** - Review and retry with different approach\n"

        if sum(m.attempts for m in self.metrics) / len(self.metrics) > 1.5:
            report += "2. ⚠️  **High retry rate** - Consider improving error detection or model prompts\n"

        avg_improvement = sum(m.improvement_percent for m in successful) / len(successful) if successful else 0
        if avg_improvement > 75:
            report += f"3. ✅ **Excellent improvement rate** ({avg_improvement:.1f}%) - Model performing well\n"

        report += "\n---\n\n"
        report += f"**Report Generated:** {datetime.now().isoformat()}\n"

        # Save report
        report_file = self.workspace_root / "benchmarks" / "results" / "final_improvement_report.md"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report)

        # Also save JSON
        json_file = report_file.with_suffix('.json')
        with open(json_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "total_duration_seconds": total_duration,
                "metrics": [m.to_dict() for m in self.metrics],
                "comparisons": [c.to_dict() for c in comparisons] if baseline_file and comparisons else []
            }, f, indent=2)

        print(f"\n{'='*80}")
        print(f"📊 FINAL REPORT")
        print(f"{'='*80}")
        print(f"✅ Successful: {len(successful)}/{len(self.metrics)}")
        print(f"🔧 Total Fixes: {sum(m.errors_fixed for m in successful)}")
        print(f"📈 Avg Improvement: {avg_improvement:.1f}%")
        print(f"📝 Report: {report_file.name}")
        print(f"📊 JSON: {json_file.name}")

        return report_file

    async def run_parallel_improvement(
        self,
        modules: List[str],
        baseline_file: Optional[Path] = None
    ):
        """Run parallel improvement with monitoring"""

        # Initialize state
        pending_modules = list(modules)
        if self.current_state:
            # Resume from checkpoint
            pending_modules = self.current_state.modules_pending
            print(f"📥 Resuming from checkpoint with {len(pending_modules)} pending modules")
        else:
            self.current_state = CheckpointState(
                timestamp=datetime.now().isoformat(),
                modules_completed=[],
                modules_failed=[],
                modules_pending=pending_modules,
                total_fixes=0,
                total_errors=0,
                elapsed_time_seconds=0,
                git_commit_hash=None
            )

        # Start monitoring task
        monitor_task = asyncio.create_task(self.monitor_progress())

        # Process modules in parallel batches
        while pending_modules:
            batch = pending_modules[:self.max_parallel]
            pending_modules = pending_modules[self.max_parallel:]

            print(f"\n🚀 Processing batch of {len(batch)} modules...")

            # Process batch in parallel
            tasks = [
                self.improve_module_with_retry(module)
                for module in batch
            ]

            results = await asyncio.gather(*tasks)

            # Update state
            for result in results:
                self.metrics.append(result)

                if result.success:
                    self.current_state.modules_completed.append(result.module_name)
                    self.current_state.total_fixes += result.errors_fixed
                    self.current_state.total_errors = max(0, self.current_state.total_errors - result.errors_fixed)
                else:
                    self.current_state.modules_failed.append(result.module_name)

            self.current_state.modules_pending = pending_modules
            self.current_state.elapsed_time_seconds = time.time() - self.start_time

            # Save checkpoint after each batch
            self.save_checkpoint()

        # Cancel monitoring
        monitor_task.cancel()

        # Generate final report
        await self.generate_final_report(baseline_file)

        # Try to push to GitHub
        await self.push_to_github()

    async def push_to_github(self):
        """Push all commits to GitHub"""
        try:
            print(f"\n🚀 Pushing {len([m for m in self.metrics if m.git_commit])} commits to GitHub...")

            proc = await asyncio.create_subprocess_exec(
                "git", "push", "origin", "master",
                cwd=self.workspace_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                print("✅ Successfully pushed to GitHub")
            else:
                print(f"⚠️  Push failed: {stderr.decode()}")
                print("Run manually: git push origin master")

        except Exception as e:
            print(f"❌ Failed to push: {e}")


async def main():
    """Main entry point"""
    import sys

    workspace = sys.argv[1] if len(sys.argv) > 1 else "/Users/xcallens/rust-linux-mini-kernel"
    baseline_file = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    monitor = ParallelImprovementMonitor(workspace, max_parallel=4)

    # Get modules to improve
    crates_dir = Path(workspace) / "crates"
    modules = [d.name for d in crates_dir.iterdir() if d.is_dir()]

    print(f"{'='*80}")
    print(f"PARALLEL CODE IMPROVEMENT MONITOR")
    print(f"{'='*80}")
    print(f"Workspace: {workspace}")
    print(f"Modules: {len(modules)}")
    print(f"Max Parallel: {monitor.max_parallel}")
    print(f"Checkpoint Interval: {monitor.checkpoint_interval}s (10 min)")
    if baseline_file:
        print(f"Baseline: {baseline_file}")
    print(f"{'='*80}\n")

    await monitor.run_parallel_improvement(modules, baseline_file)


if __name__ == "__main__":
    asyncio.run(main())
