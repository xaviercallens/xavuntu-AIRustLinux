#!/bin/bash
# Monitor compilation status every 5 minutes

WORKSPACE="/Users/xcallens/rust-linux-mini-kernel"
LOG_FILE="$WORKSPACE/compilation_monitoring.log"
INTERVAL=300  # 5 minutes

cd "$WORKSPACE"

echo "========================================" | tee -a "$LOG_FILE"
echo "🔍 Compilation Status Monitor Started" | tee -a "$LOG_FILE"
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
echo "Interval: 5 minutes" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Function to check compilation status
check_compilation() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    echo "========================================" | tee -a "$LOG_FILE"
    echo "📊 Compilation Check - $timestamp" | tee -a "$LOG_FILE"
    echo "========================================" | tee -a "$LOG_FILE"

    # Sample a few modules to check status
    local modules=("netfilter" "af_inet" "udp" "tcp" "core")
    local success=0
    local failed=0
    local total=${#modules[@]}

    for module in "${modules[@]}"; do
        echo "Checking $module..." | tee -a "$LOG_FILE"

        if cargo check --manifest-path "crates/$module/Cargo.toml" > /dev/null 2>&1; then
            echo "  ✅ $module compiles" | tee -a "$LOG_FILE"
            ((success++))
        else
            # Get error count
            error_count=$(cargo check --manifest-path "crates/$module/Cargo.toml" 2>&1 | grep -c "^error")
            echo "  ❌ $module has $error_count errors" | tee -a "$LOG_FILE"
            ((failed++))
        fi
    done

    local success_rate=$(awk "BEGIN {printf \"%.1f\", ($success / $total) * 100}")

    echo "" | tee -a "$LOG_FILE"
    echo "Summary:" | tee -a "$LOG_FILE"
    echo "  ✅ Compiling: $success/$total ($success_rate%)" | tee -a "$LOG_FILE"
    echo "  ❌ Failing: $failed/$total" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"

    # Full workspace check (every 30 minutes)
    local minute=$(date '+%M')
    if [ "$minute" = "00" ] || [ "$minute" = "30" ]; then
        echo "⏱️  Running full workspace check..." | tee -a "$LOG_FILE"

        # Count how many modules compile
        local all_success=0
        local all_total=0

        for manifest in crates/*/Cargo.toml; do
            crate=$(basename $(dirname "$manifest"))
            if [ "$crate" = "kernel_types" ]; then
                continue
            fi

            ((all_total++))
            if cargo check --manifest-path "$manifest" > /dev/null 2>&1; then
                ((all_success++))
            fi
        done

        local all_rate=$(awk "BEGIN {printf \"%.1f\", ($all_success / $all_total) * 100}")

        echo "" | tee -a "$LOG_FILE"
        echo "🌐 Full Workspace Results:" | tee -a "$LOG_FILE"
        echo "  Total modules: $all_total" | tee -a "$LOG_FILE"
        echo "  Compiling: $all_success ($all_rate%)" | tee -a "$LOG_FILE"
        echo "  Failing: $((all_total - all_success))" | tee -a "$LOG_FILE"
        echo "" | tee -a "$LOG_FILE"

        # Check if improvement happened
        if [ -f "$WORKSPACE/.last_success_count" ]; then
            last_count=$(cat "$WORKSPACE/.last_success_count")
            if [ "$all_success" -gt "$last_count" ]; then
                improvement=$((all_success - last_count))
                echo "📈 IMPROVEMENT: +$improvement modules now compile!" | tee -a "$LOG_FILE"
            elif [ "$all_success" -lt "$last_count" ]; then
                regression=$((last_count - all_success))
                echo "📉 REGRESSION: -$regression modules stopped compiling" | tee -a "$LOG_FILE"
            else
                echo "➡️  No change since last full check" | tee -a "$LOG_FILE"
            fi
        fi

        # Save current count
        echo "$all_success" > "$WORKSPACE/.last_success_count"
    fi

    echo "" | tee -a "$LOG_FILE"
}

# Run initial check
check_compilation

# Loop every 5 minutes
while true; do
    sleep $INTERVAL
    check_compilation
done
