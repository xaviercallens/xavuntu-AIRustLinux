# Baseline Files

This directory contains baseline comparison files for parallel improvement monitoring.

## Creating a Baseline

After completing a run, extract metrics from the final report:

```bash
# From the final JSON report
cat benchmarks/results/final_improvement_report.json | jq '{
  model: .model,
  timestamp: .timestamp,
  success_rate: .summary.success_rate,
  avg_improvement: .summary.avg_improvement,
  total_fixes: .summary.total_fixes,
  avg_duration: .performance.avg_duration_seconds
}' > benchmarks/baselines/baseline_$(date +%Y%m%d).json
```

## Example Baseline Format

**File:** `mistral_baseline.json`

```json
{
  "model": "Mistral-7B",
  "timestamp": "2026-05-15T14:30:00",
  "success_rate": 68.5,
  "avg_improvement": 55.2,
  "total_fixes": 1834,
  "avg_duration": 45.3
}
```

## Using a Baseline

```bash
python3 benchmarks/parallel_improvement_monitor.py \
  /Users/xcallens/rust-linux-mini-kernel \
  benchmarks/baselines/mistral_baseline.json
```

## Available Baselines

- **mistral_baseline.json** - Mistral-7B run (pending)
- **gpt53_baseline.json** - Current Azure Codex GPT-5.3 run (in progress)

## Notes

- Baselines must have the same 121-module set for accurate comparison
- Success rate is percentage of modules compiling after fixes
- Avg improvement is percentage of errors fixed per module
- Total fixes is sum of all errors fixed across all successful modules
- Avg duration is seconds per module (including retries)
