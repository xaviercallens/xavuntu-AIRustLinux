#!/usr/bin/env bash
# Captures with -i (instruction pointer per call) so the output is
# directly usable by scripts/telemetry/parse_replay_events.py and
# examples/firewall_replay -- real IPs are needed to exercise
# ebpf_firewall::evaluate_syscall's kernel-address-spoofing check
# honestly, rather than leaving it untested or feeding it a fabricated
# placeholder. See docs/roadmap/ML_WORKLOAD_FIREWALL_REPLAY.md.
set -euo pipefail
N=10
WORK="$HOME/ml_traces"
mkdir -p "$WORK/device_enum" "$WORK/matmul"

echo "iter,wall_seconds" > "$WORK/device_enum_timing.csv"
for i in $(seq 1 "$N"); do
  START=$(date +%s.%N)
  strace -f -tt -i -o "$WORK/device_enum/trace_$i.log" python3 "$HOME/ml_workload_device_enum.py" > "$WORK/device_enum/stdout_$i.log" 2>&1
  END=$(date +%s.%N)
  echo "$i,$(echo "$END - $START" | bc)" >> "$WORK/device_enum_timing.csv"
  echo "device_enum run $i/$N done"
done

echo "iter,wall_seconds" > "$WORK/matmul_timing.csv"
for i in $(seq 1 "$N"); do
  START=$(date +%s.%N)
  strace -f -tt -i -o "$WORK/matmul/trace_$i.log" python3 "$HOME/ml_workload_matmul.py" > "$WORK/matmul/stdout_$i.log" 2>&1
  END=$(date +%s.%N)
  echo "$i,$(echo "$END - $START" | bc)" >> "$WORK/matmul_timing.csv"
  echo "matmul run $i/$N done"
done

tar -C "$HOME" -czf "$HOME/ml_traces.tar.gz" ml_traces
echo "Wrote $HOME/ml_traces.tar.gz"
du -sh "$HOME/ml_traces.tar.gz"
