//! Replays real captured ML-workload syscall events through this
//! project's real, unmodified `ebpf_firewall::evaluate_syscall` (the
//! Ring-0 rule-based filter) and `ai_detector::evaluate_pid_event` (the
//! TinyML sliding-window classifier) -- offline, no hardware, no
//! kernel boot needed, since both are pure computation over a
//! `SyscallAuditEvent`.
//!
//! Input: a CSV with columns
//! `workload,run,seq,pid,syscall,syscall_nr,ip_hex,prot` produced by
//! `docs/roadmap/ml_workload_traces/parse_replay_events.py` from real
//! `strace -i` captures. Every input field (pid, syscall number,
//! instruction pointer, PROT flags for mmap/mprotect) is real, parsed
//! from real captured hardware/software behavior -- nothing here is
//! synthesized. `entropy_score` is NOT captured (would need real
//! buffer contents, not just syscall metadata) and is honestly left at
//! 0 for every event via `SyscallAuditEvent::new`, which cannot trigger
//! either detector's entropy-based checks -- a real, disclosed scope
//! limit, not a hidden one.
//!
//! Since every event in this dataset comes from known-benign JAX/TPU
//! workloads, any non-`Pass` verdict from either detector is by
//! definition a false positive on this dataset.

use ai_detector::evaluate_pid_event;
use ebpf_firewall::{evaluate_syscall, Verdict};
use std::collections::HashMap;
use std::env;
use std::fs::File;
use std::io::{BufRead, BufReader, Write};

#[derive(Clone)]
struct Event {
    seq: usize,
    pid: u32,
    syscall: String,
    syscall_nr: u32,
    ip: u64,
    prot: u64,
}

fn verdict_name(v: Verdict) -> &'static str {
    match v {
        Verdict::Pass => "Pass",
        Verdict::InspectDeep => "InspectDeep",
        Verdict::BlockKill => "BlockKill",
        Verdict::Rollback => "Rollback",
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!("Usage: firewall_replay EVENTS_CSV OUT_DIR");
        std::process::exit(1);
    }
    let events_path = &args[1];
    let out_dir = &args[2];
    std::fs::create_dir_all(out_dir).expect("create out_dir");

    let file = File::open(events_path).unwrap_or_else(|e| panic!("open {events_path}: {e}"));
    let reader = BufReader::new(file);

    // workload -> run -> Vec<Event>, preserving CSV row order (== real capture order)
    let mut runs: HashMap<(String, u32), Vec<Event>> = HashMap::new();

    for (i, line) in reader.lines().enumerate() {
        let line = line.expect("read line");
        if i == 0 {
            continue; // header
        }
        let cols: Vec<&str> = line.splitn(8, ',').collect();
        assert_eq!(cols.len(), 8, "malformed row: {line}");
        let workload = cols[0].to_string();
        let run: u32 = cols[1].parse().expect("run");
        let seq: usize = cols[2].parse().expect("seq");
        let pid: u32 = cols[3].parse().expect("pid");
        let syscall = cols[4].to_string();
        let syscall_nr: u32 = cols[5].parse().expect("syscall_nr");
        let ip = u64::from_str_radix(cols[6], 16).expect("ip_hex");
        let prot: u64 = cols[7].parse().expect("prot");

        runs.entry((workload, run)).or_default().push(Event { seq, pid, syscall, syscall_nr, ip, prot });
    }

    // Two output files: per-workload verdict tallies, and every individual
    // non-Pass verdict with full context (which syscall, which layer).
    let mut summary_path = std::path::PathBuf::from(out_dir);
    summary_path.push("firewall_replay_summary.csv");
    let mut summary = File::create(&summary_path).expect("create summary");
    writeln!(summary, "workload,run,total_events,firewall_pass,firewall_inspect_deep,firewall_block_kill,firewall_rollback,classifier_pass,classifier_inspect_deep,classifier_block_kill,classifier_rollback").unwrap();

    let mut flags_path = std::path::PathBuf::from(out_dir);
    flags_path.push("firewall_replay_flags.csv");
    let mut flags = File::create(&flags_path).expect("create flags");
    writeln!(flags, "workload,run,seq,pid,syscall,layer,verdict").unwrap();

    let mut workload_run_keys: Vec<_> = runs.keys().cloned().collect();
    workload_run_keys.sort();

    for key @ (workload, run) in &workload_run_keys {
        let events = &runs[key];
        let mut fw_counts: HashMap<&str, u32> = HashMap::new();
        let mut clf_counts: HashMap<&str, u32> = HashMap::new();

        for e in events {
            let args = [0u64, 0, e.prot, 0, 0, 0];

            // SAFETY: pure computation, no hardware access; evaluate_syscall
            // is a plain function despite the crate's kernel context.
            let fw_verdict = evaluate_syscall(e.pid, e.syscall_nr, args, e.ip);
            *fw_counts.entry(verdict_name(fw_verdict)).or_insert(0) += 1;
            if fw_verdict != Verdict::Pass {
                writeln!(flags, "{workload},{run},{},{},{},firewall,{}", e.seq, e.pid, e.syscall, verdict_name(fw_verdict)).unwrap();
            }

            let event = ebpf_firewall::SyscallAuditEvent::new(e.pid, e.syscall_nr, args, e.ip);
            let clf_verdict = evaluate_pid_event(e.pid, event);
            *clf_counts.entry(verdict_name(clf_verdict)).or_insert(0) += 1;
            if clf_verdict != Verdict::Pass {
                writeln!(flags, "{workload},{run},{},{},{},classifier,{}", e.seq, e.pid, e.syscall, verdict_name(clf_verdict)).unwrap();
            }
        }

        writeln!(
            summary,
            "{workload},{run},{},{},{},{},{},{},{},{},{}",
            events.len(),
            fw_counts.get("Pass").unwrap_or(&0),
            fw_counts.get("InspectDeep").unwrap_or(&0),
            fw_counts.get("BlockKill").unwrap_or(&0),
            fw_counts.get("Rollback").unwrap_or(&0),
            clf_counts.get("Pass").unwrap_or(&0),
            clf_counts.get("InspectDeep").unwrap_or(&0),
            clf_counts.get("BlockKill").unwrap_or(&0),
            clf_counts.get("Rollback").unwrap_or(&0),
        )
        .unwrap();

        println!(
            "{workload} run {run}: {} events, firewall={:?}, classifier={:?}",
            events.len(),
            fw_counts,
            clf_counts
        );
    }

    println!("\nWrote {} and {}", summary_path.display(), flags_path.display());
}
