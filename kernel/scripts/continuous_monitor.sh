#!/bin/bash
# Continuously monitor progress every 5 minutes

WORKSPACE="/Users/xcallens/rust-linux-mini-kernel"
MONITOR_SCRIPT="$WORKSPACE/scripts/monitor_progress.sh"

echo "🚀 Starting continuous monitoring (every 5 minutes)"
echo "📍 Press Ctrl+C to stop"
echo ""

# Run immediately first time
bash "$MONITOR_SCRIPT"

# Then every 5 minutes
while true; do
    sleep 300  # 5 minutes
    bash "$MONITOR_SCRIPT"

    # Check if process is still running
    if ! pgrep -f parallel_improvement_monitor > /dev/null; then
        echo ""
        echo "✅ Process completed or stopped"

        # Show final summary
        CHECKPOINT="$WORKSPACE/benchmarks/checkpoints/checkpoint_latest.json"
        if [ -f "$CHECKPOINT" ]; then
            COMPLETED=$(jq -r '.modules_completed | length' "$CHECKPOINT")
            FAILED=$(jq -r '.modules_failed | length' "$CHECKPOINT")
            TOTAL=$(( COMPLETED + FAILED ))
            SUCCESS_RATE=$(awk "BEGIN {printf \"%.1f\", ($COMPLETED / $TOTAL) * 100}")

            echo ""
            echo "================================="
            echo "📊 FINAL RESULTS"
            echo "================================="
            echo "✅ Successful: $COMPLETED"
            echo "❌ Failed: $FAILED"
            echo "📈 Success Rate: ${SUCCESS_RATE}%"
            echo ""
            echo "📄 Check final report:"
            echo "   cat $WORKSPACE/benchmarks/results/final_improvement_report.md"
        fi

        break
    fi
done
