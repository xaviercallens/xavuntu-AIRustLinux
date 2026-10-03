#!/bin/sh
# KASAN/UBSAN & Kernel Panic Telemetry Monitor Script for MVK
# Continuous log scraper sidecar

set -e

LOG_FILE=""
INTERVAL=5

# Parse arguments
while [ "$#" -gt 0 ]; do
    case "$1" in
        --log-file)
            LOG_FILE="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 --log-file <file> [--interval <seconds>]"
            exit 1
            ;;
    esac
done

if [ -z "$LOG_FILE" ]; then
    echo "Error: --log-file is required."
    exit 1
fi

echo "============================================================"
echo " Starting MVK KASAN/UBSAN Telemetry Monitor"
echo " Target Log File: $LOG_FILE"
echo " Sampling Interval: $INTERVAL seconds"
echo "============================================================"

# Create log file if it doesn't exist
touch "$LOG_FILE"

# Track read offset
LAST_LINE_COUNT=0

while true; do
    CURRENT_LINE_COUNT=$(wc -l < "$LOG_FILE")
    
    if [ "$CURRENT_LINE_COUNT" -gt "$LAST_LINE_COUNT" ]; then
        DIFF_LINES=$((CURRENT_LINE_COUNT - LAST_LINE_COUNT))
        
        # Extract new lines
        tail -n "$DIFF_LINES" "$LOG_FILE" | while read -r line; do
            # 1. Look for KASAN memory corruption patterns
            if echo "$line" | grep -q "BUG: KASAN:"; then
                echo "[ALERT] [KASAN ERROR detected] -> $line"
            fi
            
            # 2. Look for UBSAN undefined behavior patterns
            if echo "$line" | grep -q "UBSAN:"; then
                echo "[WARN] [UBSAN Undefined Behavior detected] -> $line"
            fi
            
            # 3. Look for standard Linux Kernel Panics
            if echo "$line" | grep -q "Kernel panic - not syncing"; then
                echo "[CRITICAL] [KERNEL PANIC detected] -> $line"
            fi
        done
        
        LAST_LINE_COUNT=$CURRENT_LINE_COUNT
    fi
    
    sleep "$INTERVAL"
done
