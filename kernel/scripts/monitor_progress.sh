#!/bin/bash
# Monitor parallel improvement progress every 5 minutes

WORKSPACE="/Users/xcallens/rust-linux-mini-kernel"
CHECKPOINT="$WORKSPACE/benchmarks/checkpoints/checkpoint_latest.json"
LOG_FILE="$WORKSPACE/monitoring.log"

echo "=================================" | tee -a "$LOG_FILE"
echo "🔍 Progress Monitor - $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
echo "=================================" | tee -a "$LOG_FILE"

# Check if process is running
if ! pgrep -f parallel_improvement_monitor > /dev/null; then
    echo "❌ Monitor not running!" | tee -a "$LOG_FILE"
    exit 1
fi

echo "✅ Process running (PID: $(pgrep -f parallel_improvement_monitor))" | tee -a "$LOG_FILE"

# Check if checkpoint exists
if [ ! -f "$CHECKPOINT" ]; then
    echo "⏳ Waiting for first checkpoint..." | tee -a "$LOG_FILE"
    exit 0
fi

# Parse checkpoint data
TIMESTAMP=$(jq -r '.timestamp' "$CHECKPOINT")
COMPLETED=$(jq -r '.modules_completed | length' "$CHECKPOINT")
FAILED=$(jq -r '.modules_failed | length' "$CHECKPOINT")
PENDING=$(jq -r '.modules_pending | length' "$CHECKPOINT")
TOTAL=$(( COMPLETED + FAILED + PENDING ))
PROGRESS=$(awk "BEGIN {printf \"%.1f\", ($COMPLETED / $TOTAL) * 100}")
ELAPSED=$(jq -r '.elapsed_time_seconds' "$CHECKPOINT")
ELAPSED_MIN=$(awk "BEGIN {printf \"%.1f\", $ELAPSED / 60}")

echo "" | tee -a "$LOG_FILE"
echo "📊 Progress Summary:" | tee -a "$LOG_FILE"
echo "   Timestamp: $TIMESTAMP" | tee -a "$LOG_FILE"
echo "   Completed: $COMPLETED/$TOTAL ($PROGRESS%)" | tee -a "$LOG_FILE"
echo "   Failed: $FAILED" | tee -a "$LOG_FILE"
echo "   Pending: $PENDING" | tee -a "$LOG_FILE"
echo "   Elapsed: ${ELAPSED_MIN} minutes" | tee -a "$LOG_FILE"

# Calculate estimated time remaining
if [ "$COMPLETED" -gt 0 ]; then
    AVG_TIME_PER_MODULE=$(awk "BEGIN {printf \"%.1f\", $ELAPSED / ($COMPLETED + $FAILED)}")
    REMAINING_MODULES=$PENDING
    EST_REMAINING=$(awk "BEGIN {printf \"%.1f\", ($AVG_TIME_PER_MODULE * $REMAINING_MODULES) / 60}")
    echo "   Estimated remaining: ${EST_REMAINING} minutes" | tee -a "$LOG_FILE"
fi

# Check for recent successes
if [ "$COMPLETED" -gt 0 ]; then
    echo "" | tee -a "$LOG_FILE"
    echo "✅ Successful modules:" | tee -a "$LOG_FILE"
    jq -r '.modules_completed[]' "$CHECKPOINT" | tail -5 | sed 's/^/   - /' | tee -a "$LOG_FILE"
fi

# Check latest interim report
LATEST_REPORT=$(ls -t "$WORKSPACE/benchmarks/results/interim_report_"*.md 2>/dev/null | head -1)
if [ -f "$LATEST_REPORT" ]; then
    echo "" | tee -a "$LOG_FILE"
    echo "📄 Latest report: $(basename $LATEST_REPORT)" | tee -a "$LOG_FILE"
fi

echo "" | tee -a "$LOG_FILE"
