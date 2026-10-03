#!/usr/bin/env bash
# ==============================================================================
# Xavuntu 1-Hour Performance Endurance Benchmark Launcher
# System: Xavuntu 24.04 LTS (Ubuntu User-Space on RunuX Rust Kernel v13.0)
# Storage: /data (1TB NVMe Dedicated Storage)
# ==============================================================================

set -e

BENCHMARK_BIN="/usr/local/bin/xavuntu-1hr-benchmark"
PYTHON_ENV="/opt/xavuntu-ai-env/bin/python3"
TMUX_SESSION="xavuntu-bench"
DATA_DIR="/data/xavuntu_benchmark"
SUMMARY_TXT="$DATA_DIR/xavuntu_1hr_benchmark_summary.txt"
REPORT_JSON="$DATA_DIR/xavuntu_1hr_benchmark_report.json"
LOG_FILE="$DATA_DIR/benchmark.log"

DURATION=3600
MODE="foreground"

show_help() {
    echo "==========================================================================="
    echo "  🚀 XAVUNTU 1-HOUR PERFORMANCE BENCHMARK CONTROL TOOL"
    echo "==========================================================================="
    echo "Usage: ./launch_1hr_benchmark.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --foreground, -f     Run interactively in the current terminal (Default)"
    echo "  --background, -b     Run detached in background tmux session ('$TMUX_SESSION')"
    echo "  --duration, -d SEC   Set custom test duration in seconds (Default: 3600 = 1 hour)"
    echo "  --quick, -q          Run quick 60-second test instead of 1 hour"
    echo "  --attach, -a         Attach to active background tmux session"
    echo "  --status, -s         Check status and progress of running benchmark"
    echo "  --stop               Gracefully stop the running benchmark"
    echo "  --view-report, -r    Display latest completed benchmark report"
    echo "  --help, -h           Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./launch_1hr_benchmark.sh                 # Launch 1-hour test in current terminal"
    echo "  ./launch_1hr_benchmark.sh --background    # Launch 1-hour test in background"
    echo "  ./launch_1hr_benchmark.sh --attach        # Reattach to background test"
    echo "  ./launch_1hr_benchmark.sh --status        # View current status"
    echo "==========================================================================="
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --foreground|-f)
            MODE="foreground"
            shift
            ;;
        --background|-b)
            MODE="background"
            shift
            ;;
        --duration|-d)
            DURATION="$2"
            shift 2
            ;;
        --quick|-q)
            DURATION=60
            shift
            ;;
        --attach|-a)
            if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
                exec tmux attach -t "$TMUX_SESSION"
            else
                echo "[!] No active background benchmark session found ($TMUX_SESSION)."
                exit 1
            fi
            ;;
        --status|-s)
            echo "=== Xavuntu Benchmark Status ==="
            if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
                echo "Status: RUNNING in background tmux session ($TMUX_SESSION)"
                echo "Tip: Run './launch_1hr_benchmark.sh --attach' to view live dashboard"
            elif pgrep -f "xavuntu-1hr-benchmark" >/dev/null; then
                echo "Status: RUNNING (PID: $(pgrep -f "xavuntu-1hr-benchmark" | head -n1))"
            else
                echo "Status: NOT RUNNING"
            fi
            if [ -f "$SUMMARY_TXT" ]; then
                echo ""
                echo "Latest Summary Report: $SUMMARY_TXT"
                echo "Last modified: $(stat -c %y "$SUMMARY_TXT" 2>/dev/null || stat -f "%Sm" "$SUMMARY_TXT" 2>/dev/null)"
            fi
            exit 0
            ;;
        --stop)
            echo "Stopping benchmark processes..."
            pkill -INT -f "xavuntu-1hr-benchmark" || true
            sleep 2
            pkill -TERM -f "xavuntu-1hr-benchmark" || true
            echo "Stopped."
            exit 0
            ;;
        --view-report|-r)
            if [ -f "$SUMMARY_TXT" ]; then
                cat "$SUMMARY_TXT"
            else
                echo "[!] No benchmark report found at $SUMMARY_TXT yet."
            fi
            exit 0
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Ensure output directory exists
mkdir -p "$DATA_DIR"

if [ "$MODE" = "background" ]; then
    if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        echo "[!] A benchmark is ALREADY running in tmux session '$TMUX_SESSION'."
        echo "Attach to it with: ./launch_1hr_benchmark.sh --attach"
        exit 1
    fi
    echo "--> Starting 1-Hour Benchmark in background tmux session: '$TMUX_SESSION'..."
    echo "    Duration: $DURATION seconds ($((DURATION / 60)) minutes)"
    echo "    Log File: $LOG_FILE"
    echo "    Target:   $DATA_DIR"
    echo ""
    tmux new-session -d -s "$TMUX_SESSION" "$PYTHON_ENV $BENCHMARK_BIN --duration $DURATION"
    echo "✅ Benchmark successfully launched in background!"
    echo "   • To attach and view the live dashboard: ./launch_1hr_benchmark.sh --attach"
    echo "   • To check status:                       ./launch_1hr_benchmark.sh --status"
    echo "   • To stop anytime:                       ./launch_1hr_benchmark.sh --stop"
    echo "   • To view report once completed:         ./launch_1hr_benchmark.sh --view-report"
else
    echo "--> Starting 1-Hour Benchmark in interactive foreground..."
    exec "$PYTHON_ENV" "$BENCHMARK_BIN" --duration "$DURATION"
fi
