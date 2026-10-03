# Parallel Code Improvement Monitor

Real-time monitoring system for parallel code improvement processes with checkpoint/retry and GitHub integration.

## Features

- ✅ **Parallel Processing** - Run up to 4 modules simultaneously
- ✅ **Checkpoint & Retry** - Auto-save state every 10 minutes, retry failed modules up to 3 times
- ✅ **Progress Monitoring** - Real-time updates every 10 minutes
- ✅ **GitHub Integration** - Auto-commit successful fixes and push to remote
- ✅ **Baseline Comparison** - Compare with previous runs (e.g., Mistral vs GPT-5.3)
- ✅ **Comprehensive Reports** - Interim and final reports in Markdown + JSON

## Quick Start

### Monitor Running Azure Codex Batch

```bash
cd /Users/xcallens/rust-linux-mini-kernel

# Check current Codex container status
az container show \
  --resource-group rg-rust-kernel \
  --name codex-compiler-20260517-084058 \
  --query "containers[0].instanceView.currentState.state" \
  -o tsv

# Follow logs in real-time
az container logs \
  --resource-group rg-rust-kernel \
  --name codex-compiler-20260517-084058 \
  --follow
```

### Run Local Parallel Improvement

```bash
# Run on all modules with 4 parallel workers
python3 benchmarks/parallel_improvement_monitor.py

# Run on specific workspace
python3 benchmarks/parallel_improvement_monitor.py /path/to/workspace

# Run with baseline comparison
python3 benchmarks/parallel_improvement_monitor.py \
  /path/to/workspace \
  benchmarks/baselines/mistral_baseline.json
```

## Checkpoint System

### How It Works

1. **Auto-Save**: State saved every 10 minutes to `benchmarks/checkpoints/`
2. **Resume**: Automatically resumes from latest checkpoint on restart
3. **Retry Logic**: Failed modules retried up to 3 times with exponential backoff

### Checkpoint Files

```
benchmarks/checkpoints/
├── checkpoint_latest.json          # Always points to most recent
├── checkpoint_1715933100.json      # Timestamped checkpoints
└── checkpoint_1715933700.json
```

### Checkpoint Structure

```json
{
  "timestamp": "2026-05-17T10:00:00",
  "modules_completed": ["netfilter", "af_inet"],
  "modules_failed": ["xfrm6_tunnel"],
  "modules_pending": ["tcp", "udp", "..."],
  "total_fixes": 145,
  "total_errors": 1523,
  "elapsed_time_seconds": 3600,
  "git_commit_hash": "a69ccaa"
}
```

### Manual Checkpoint Management

```bash
# View latest checkpoint
cat benchmarks/checkpoints/checkpoint_latest.json | jq

# List all checkpoints
ls -lh benchmarks/checkpoints/

# Resume from specific checkpoint
cp benchmarks/checkpoints/checkpoint_1715933100.json \
   benchmarks/checkpoints/checkpoint_latest.json

python3 benchmarks/parallel_improvement_monitor.py
```

## Progress Monitoring

### Real-Time Updates (Every 10 Minutes)

```
================================================================================
📊 PROGRESS UPDATE - 10:30:00
================================================================================
⏱️  Elapsed: 45.2 minutes
✅ Completed: 28/121 (23.1%)
❌ Failed: 3
⏳ Pending: 90
🔧 Total Fixes: 342
🐛 Remaining Errors: 1834
```

### Interim Reports

Generated every 10 minutes at:
- `benchmarks/results/interim_report_<timestamp>.md`

Contains:
- Progress summary
- Quality metrics
- Top improvements so far
- Next checkpoint time

## Baseline Comparison

### Create Baseline File

From previous run results:

```bash
# From Mistral run
cat > benchmarks/baselines/mistral_baseline.json << 'EOF'
{
  "model": "Mistral-7B",
  "timestamp": "2026-05-15T14:30:00",
  "success_rate": 68.5,
  "avg_improvement": 55.2,
  "total_fixes": 1834,
  "avg_duration": 45.3
}
EOF
```

### Run with Comparison

```bash
python3 benchmarks/parallel_improvement_monitor.py \
  /Users/xcallens/rust-linux-mini-kernel \
  benchmarks/baselines/mistral_baseline.json
```

### Comparison Metrics

| Metric | Current (GPT-5.3) | Baseline (Mistral) | Δ | Better? |
|--------|-------------------|---------------------|---|---------|
| Success Rate | 76.0% | 68.5% | +7.5% | ✅ |
| Avg Improvement | 62.3% | 55.2% | +7.1% | ✅ |
| Total Fixes | 2245 | 1834 | +22.4% | ✅ |
| Avg Duration | 38.4s | 45.3s | -15.2% | ✅ |

## Git Integration

### Auto-Commit

Each successfully fixed module is automatically committed:

```bash
Fix 15 compilation errors in netfilter

Auto-fixed by Azure Codex GPT-5.3

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

### Auto-Push

After all modules complete, automatically pushes to GitHub:

```bash
git push origin master
```

**Note:** If push fails (e.g., conflicts), run manually:

```bash
cd /Users/xcallens/rust-linux-mini-kernel
git pull --rebase origin master
git push origin master
```

## Retry Logic

### Strategy

1. **First Attempt**: Normal processing
2. **Retry 1** (after 2s): If failed, retry with same config
3. **Retry 2** (after 4s): If failed again, retry with adjusted timeout
4. **Retry 3** (after 8s): Final attempt
5. **Mark Failed**: If all retries exhausted

### Exponential Backoff

- 1st retry: 2 seconds
- 2nd retry: 4 seconds
- 3rd retry: 8 seconds

### Common Failure Modes

| Failure | Auto-Retry | Solution |
|---------|------------|----------|
| API Timeout | ✅ Yes | Extends timeout on retry |
| Rate Limit | ✅ Yes | Waits for backoff period |
| Network Error | ✅ Yes | Retries connection |
| Invalid Module | ❌ No | Marks as failed immediately |
| Compilation Timeout | ✅ Yes | Increases timeout |

## Reports

### Interim Report (Every 10 Min)

**File:** `benchmarks/results/interim_report_<timestamp>.md`

**Contents:**
- Progress summary (X/Y completed)
- Quality metrics (errors fixed, improvement %)
- Top 10 improvements so far
- Next checkpoint time

### Final Report

**Files:**
- `benchmarks/results/final_improvement_report.md`
- `benchmarks/results/final_improvement_report.json`

**Contents:**
- Executive summary
- Overall results (success rate, total fixes)
- Performance metrics (duration, throughput)
- Top 20 improvements
- Failed modules list
- Baseline comparison (if provided)
- Git integration summary
- Recommendations

### Example Final Report

```markdown
# Parallel Code Improvement - Final Report

**Generated:** 2026-05-17 16:45:00
**Total Duration:** 387.2 minutes
**Model:** Azure OpenAI GPT-5.3-codex

## Executive Summary

| Metric | Value |
|--------|-------|
| **Total Modules** | 121 |
| **Successful** | 92 (76.0%) |
| **Failed** | 29 (24.0%) |
| **Total Errors Fixed** | 2,245 |
| **Avg Improvement** | 62.3% |
| **Total Commits** | 92 |

## Performance

| Metric | Value |
|--------|-------|
| **Total Duration** | 387.2 minutes |
| **Avg per Module** | 192.1 seconds |
| **Throughput** | 18.7 modules/hour |
| **Retry Rate** | 0.43 retries/module |
```

## Monitoring Commands

### Check Container Status

```bash
# Get current state
az container show \
  --resource-group rg-rust-kernel \
  --name codex-compiler-20260517-084058 \
  --query "containers[0].instanceView.currentState"

# Count processed modules (from logs)
az container logs \
  --resource-group rg-rust-kernel \
  --name codex-compiler-20260517-084058 \
  2>&1 | grep "Processing:" | wc -l

# Check for errors
az container logs \
  --resource-group rg-rust-kernel \
  --name codex-compiler-20260517-084058 \
  2>&1 | grep "❌" | tail -20
```

### Monitor Local Process

```bash
# Watch interim reports
watch -n 600 'ls -lh benchmarks/results/interim_report_*.md | tail -1'

# Monitor checkpoint updates
watch -n 600 'cat benchmarks/checkpoints/checkpoint_latest.json | jq ".modules_completed | length"'

# Check progress percentage
watch -n 600 'python3 -c "import json; data=json.load(open(\"benchmarks/checkpoints/checkpoint_latest.json\")); total=len(data[\"modules_completed\"])+len(data[\"modules_pending\"])+len(data[\"modules_failed\"]); print(f\"{len(data[\"modules_completed\"])}/{total} ({len(data[\"modules_completed\"])/total*100:.1f}%)\")"'
```

## Troubleshooting

### Resume After Failure

If process crashes or is interrupted:

```bash
# Check for checkpoint
ls benchmarks/checkpoints/checkpoint_latest.json

# Resume (automatically loads checkpoint)
python3 benchmarks/parallel_improvement_monitor.py
```

### Clear Checkpoints (Start Fresh)

```bash
# Backup old checkpoints
mv benchmarks/checkpoints benchmarks/checkpoints.backup

# Start fresh
python3 benchmarks/parallel_improvement_monitor.py
```

### Failed Module Analysis

```bash
# Extract failed modules from report
grep "^|" benchmarks/results/final_improvement_report.md | \
  grep -A100 "Failed Modules" | \
  tail -n +4 | \
  awk -F'|' '{print $2}' | \
  xargs

# Retry specific failed modules
for module in $(cat failed_modules.txt); do
  python3 benchmarks/parallel_improvement_monitor.py --module $module
done
```

## Configuration

### Adjust Parallelism

Edit `parallel_improvement_monitor.py`:

```python
# Change max_parallel parameter
monitor = ParallelImprovementMonitor(workspace, max_parallel=8)  # Default: 4
```

### Adjust Checkpoint Interval

```python
# Change checkpoint_interval (in seconds)
self.checkpoint_interval = 300  # 5 minutes (default: 600)
```

### Adjust Retry Count

```python
# Change max_retries
self.max_retries = 5  # Default: 3
```

## Cost Estimates

### Azure Container Instance

**Current Run:**
- Duration: 6-8 hours
- Cost: ~$0.40-0.64/hour
- **Total: ~$3-5 per run**

### API Costs

**GPT-5.3-codex:**
- ~363 requests (121 modules × 3 attempts)
- ~$0.06-0.10 per request
- **Total: ~$22-36 per run**

### Combined Cost

**Full 121-module run:** ~$25-40

## Integration with CI/CD

### GitHub Actions

```yaml
name: Parallel Code Improvement

on:
  schedule:
    - cron: '0 2 * * 0'  # Weekly on Sunday 2 AM

jobs:
  improve:
    runs-on: ubuntu-latest
    timeout-minutes: 480  # 8 hours

    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install Rust
        uses: actions-rust-lang/setup-rust-toolchain@v1

      - name: Run Parallel Improvement
        env:
          AZURE_OPENAI_ENDPOINT_1: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
          AZURE_OPENAI_KEY_1: ${{ secrets.AZURE_OPENAI_KEY }}
          AZURE_OPENAI_DEPLOYMENT_1: gpt-5.3-codex
        run: |
          python3 benchmarks/parallel_improvement_monitor.py

      - name: Upload Reports
        uses: actions/upload-artifact@v3
        with:
          name: improvement-reports
          path: benchmarks/results/

      - name: Push Changes
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git push origin master
```

## Support

**Issues:** https://github.com/xaviercallens/rust-linux-mini-kernel/issues  
**Documentation:** This file + DEPLOYMENT_SUCCESS.md  
**Contact:** Xavier Callens

---

**Created:** 2026-05-17  
**Version:** 1.0  
**Status:** Production Ready
