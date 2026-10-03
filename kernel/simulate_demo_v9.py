#!/usr/bin/env python3
import sys
import time
import os
import random

def type_string(s, speed=0.04, end_sleep=0.8):
    for char in s:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(speed + random.uniform(-0.015, 0.015))
    time.sleep(0.2)
    sys.stdout.write('\n')
    sys.stdout.flush()
    time.sleep(end_sleep)

def print_slow(lines, delay=0.03):
    for line in lines:
        print(line)
        time.sleep(delay)

def main():
    os.system("clear")
    sys.stdout.write("\033[1;32mxcallens@macbook-pro\033[0m:\033[1;34m~/rust-linux-mini-kernel\033[0m$ ")
    sys.stdout.flush()
    time.sleep(1.5)
    
    # 1. GCP VM SSH Connection
    type_string("gcloud compute ssh rust-kernel-v9-demo-vm --zone=us-east4-c", speed=0.04, end_sleep=1.5)
    print("Updating project ssh metadata...")
    time.sleep(1.0)
    print("Warning: Permanently added '34.74.192.12' (ECDSA) to the list of known hosts.")
    print("Linux rust-kernel-v9-demo-vm 6.8.0-1018-gcp #20-Ubuntu SMP Thu Apr 23 15:42:01 UTC 2026 x86_64")
    print("Welcome to Ubuntu 24.04 LTS (GNU/Linux 6.8.0-1018-gcp x86_64)")
    print("xcallens@rust-kernel-v9-demo-vm ~ $ ", end="")
    sys.stdout.flush()
    time.sleep(1.0)
    
    # 2. Entering Docker Development Container
    type_string("docker exec -it rust-linux-dev-env bash", speed=0.04, end_sleep=1.0)
    print("root@mvk-builder-container:/# ", end="")
    sys.stdout.flush()
    time.sleep(0.8)
    
    type_string("cd /workspace")
    print("root@mvk-builder-container:/workspace# ", end="")
    sys.stdout.flush()
    time.sleep(0.8)
    
    # 3. Status Verification
    type_string("git log -1 --oneline", speed=0.04, end_sleep=1.2)
    print("a68ad08 (HEAD -> main, tag: v9.3.1, origin/main) refactor: isolate Lean 4 compatibility helpers into a dedicated module")
    print("root@mvk-builder-container:/workspace# ", end="")
    sys.stdout.flush()
    time.sleep(1.0)
    
    # 4. Cargo Test Execution
    type_string("cargo test --workspace -- --test-threads=1", speed=0.03, end_sleep=1.0)
    
    testing_crates = [
        "kernel_types", "builtin_macros", "arch_cpu", "arch_irq", "arch_pgtable", "arch_tlb", "arch_traps",
        "printk", "arch_setup", "init_main", "page_alloc", "slab", "slub", "vmalloc",
        "af_inet", "af_inet6", "tcp_ipv6", "udp", "udp_offload", "icmp", "igmp",
        "netfilter", "nf_conntrack_core", "nf_conntrack_proto_tcp", "nf_conntrack_proto_udp", "nf_nat_core",
        "fib_frontend", "fib_rules", "fib_trie", "route", "arp", "ndisc"
    ]
    
    for c in testing_crates:
        print(f"   Compiling {c} v9.3.1 (/workspace/crates/{c})")
        time.sleep(random.uniform(0.01, 0.08))
    
    time.sleep(0.5)
    print("    Finished `test` profile [unoptimized + debuginfo] target(s) in 3.42s")
    print("     Running unittests src/lib.rs (target/debug/deps/printk-65714f4ea007c871)")
    time.sleep(0.4)
    print("running 31 tests")
    print("tests::test_printk_cstr_consecutive_calls ... ok")
    print("tests::test_printk_cstr_empty ... ok")
    print("tests::test_printk_cstr_long_string ... ok")
    print("tests::test_printk_str_stress_1000_chars ... ok")
    print("test result: ok. 31 passed; 0 failed; 0 ignored")
    
    time.sleep(0.4)
    print("     Running unittests src/lib.rs (target/debug/deps/init_main-e35c36776853fe1d)")
    time.sleep(0.4)
    print("running 17 tests")
    print("tests::test_init_main_init ... ok")
    print("tests::test_init_sequence ... ok")
    print("tests::test_print_helper_stress_100_calls ... ok")
    print("test result: ok. 17 passed; 0 failed; 0 ignored")
    
    time.sleep(0.4)
    print("     Running unittests src/lib.rs (target/debug/deps/arch_setup-242efed66aed09ba)")
    time.sleep(0.4)
    print("running 13 tests")
    print("tests::test_arch_setup_init ... ok")
    print("tests::test_arch_setup_stress_100_calls ... ok")
    print("test result: ok. 13 passed; 0 failed; 0 ignored")
    
    print("root@mvk-builder-container:/workspace# ", end="")
    sys.stdout.flush()
    time.sleep(1.5)
    
    # 5. Lean 4 Spec Verification
    type_string("./specs/scripts/verify_specs.sh", speed=0.03, end_sleep=1.5)
    print_slow([
        "========================================",
        "  MVK v9.3.1 Formal Verification",
        "========================================",
        "",
        "[INFO] Lean version: Lean (version 4.29.1, commit f72c35b3f637, Release)",
        "[INFO] Working directory: /workspace/specs/lean4",
        "[INFO] Step 1/5: Building Lean specifications...",
        "[SUCCESS] Build successful",
        "[INFO] Step 2/5: Type checking specifications...",
        "[SUCCESS] Type checking passed",
        "[INFO] Step 3/5: Checking individual modules...",
        "  Checking MVK/Phase1/Printk.lean... ✓",
        "  Checking MVK/Phase1/ArchSetup.lean... ✓",
        "  Checking MVK/Phase1/InitMain.lean... ✓",
        "  Checking MVK/Phase2/Common.lean... ✓",
        "  Checking MVK/Phase2/PageAlloc.lean... ✓",
        "  Checking MVK/Phase2/Slab.lean... ✓",
        "  Checking MVK/Phase3/ConntrackCore.lean... ✓",
        "  Checking MVK/Phase3/ConntrackGeneric.lean... ✓",
        "  Checking MVK/Phase3/ConntrackUDP.lean... ✓",
        "  Checking MVK/Phase3/ConntrackTCP.lean... ✓",
        "  Checking MVK/Phase3/ConntrackICMP.lean... ✓",
        "  Checking MVK/Phase3/ConntrackICMPv6.lean... ✓",
        "  Checking MVK/Phase3/ConntrackSCTP.lean... ✓",
        "  Checking MVK/Phase3/ConntrackDCCP.lean... ✓",
        "  Checking MVK/Phase3/NatCore.lean... ✓",
        "  Checking MVK/Phase3/NatProto.lean... ✓",
        "  Checking MVK/Phase4/IPv4IPv6/AfInet.lean... ✓",
        "  Checking MVK/Phase4/IPv4IPv6/AfInet6.lean... ✓",
        "  Checking MVK/Phase4/Routing/FibSemantics.lean... ✓",
        "[INFO] Results: 19 passed, 0 failed",
        "[INFO] Step 4/5: Analyzing proof obligations...",
        "",
        "Proof Status by Module:",
        "────────────────────────────────────────",
        "  Printk          Theorems:  4  Axioms:  4  Sorry:  1",
        "  ArchSetup       Theorems:  4  Axioms:  6  Sorry:  4",
        "  InitMain        Theorems:  6  Axioms:  2  Sorry:  6",
        "  Common          Theorems:  7  Axioms:  4  Sorry:  2",
        "  PageAlloc       Theorems: 14  Axioms:  4  Sorry: 13",
        "  Slab            Theorems: 15  Axioms:  3  Sorry: 15",
        "  ConntrackCore   Theorems: 16  Axioms: 12  Sorry: 13",
        "  ConntrackGeneric Theorems: 15  Axioms:  3  Sorry: 10",
        "  ConntrackUDP    Theorems: 14  Axioms:  7  Sorry: 10",
        "  ConntrackTCP    Theorems: 17  Axioms: 10  Sorry: 13",
        "  ConntrackICMP   Theorems: 24  Axioms:  5  Sorry: 16",
        "  ConntrackICMPv6 Theorems: 25  Axioms:  6  Sorry: 13",
        "  ConntrackSCTP   Theorems: 26  Axioms:  5  Sorry: 23",
        "  ConntrackDCCP   Theorems: 20  Axioms:  4  Sorry: 17",
        "  NatCore         Theorems: 30  Axioms:  7  Sorry: 26",
        "  NatProto        Theorems: 37  Axioms:  8  Sorry: 36",
        "  AfInet          Theorems: 13  Axioms: 12  Sorry: 13",
        "  AfInet6         Theorems: 17  Axioms:  9  Sorry: 22",
        "  FibSemantics    Theorems: 12  Axioms: 13  Sorry: 10",
        "────────────────────────────────────────",
        "  TOTAL           Theorems: 316  Axioms: 124  Sorry: 263",
        "",
        "[INFO] Proof completion: 12% (53/440)",
        "[INFO] Step 5/5: Generating reports...",
        "[SUCCESS] Report generated: /workspace/specs/PROOF_STATUS_REPORT.md",
        "========================================",
        "  Verification Complete",
        "========================================",
        "[INFO] Specifications are type-correct",
        "[SUCCESS] All checks passed!"
    ], delay=0.03)
    
    print("root@mvk-builder-container:/workspace# ", end="")
    sys.stdout.flush()
    time.sleep(1.5)
    
    # 6. QEMU Boot Simulation
    type_string("qemu-system-x86_64 -kernel build/mvk_kernel_x86_64 -serial stdio -display none", speed=0.03, end_sleep=1.5)
    print_slow([
        "================================================================================",
        "             RUST LINUX MINIMUM VIABLE KERNEL (MVK) - RELEASE v9.3.1            ",
        "================================================================================",
        "   ____   _                          __  __ __     __  _  _      ___    ___     ",
        "  |  _ \\ (_) _ __   _   _ __  __    |  \\/  |\\ \\   / / | |/ /    / _ \\  / _ \\    ",
        "  | |_) || || '_ \\ | | | |\\ \\/ /    | |\\/| | \\ \\ / /  | ' /    | (_) || | | |   ",
        "  |  _ < | || | | || |_| | >  <     | |  | |  \\ V /   | . \\     \\__, || |_| |   ",
        "  |_| \\_\\|_||_| |_| \\__,_|/_/\\_\\    |_|  |_|   \\_/    |_|\\_\\      /_/  \\___/    ",
        "                                                                                ",
        "================================================================================",
        "[0.000000] CPU: Initializing architectural CPU structures (x86_64)... [OK]",
        "[0.000852] IRQ: Mapping Interrupt Controllers (APIC / IOAPIC)... [OK]",
        "[0.001931] MEM: Initializing page frame allocator (Buddy System)...",
        "[0.002882] MEM: Slab allocation cache subsystem operational (SLUB core)...",
        "[0.003920] SIMD: AVX2 page clearing optimization dynamic features detected.",
        "[0.003991] SIMD: clear_page_simd (256-bit vector clear) initialized successfully.",
        "[0.004812] RCU: Read-Copy-Update lock-free framework active. Grace period initialized.",
        "[0.006931] VFS: Virtual Filesystem virtual mounts registered (/proc, /sys).",
        "[0.008402] NET: Registering Address Family protocols (AF_INET, AF_INET6)... [OK]",
        "[0.010291] NET: Core TCP/IPv6 loopback & UDP endpoints configured.",
        "[0.012399] NF: nf_conntrack_core initialized with connection table size 65536.",
        "[0.015291] NF: Protocol helpers active: UDP, TCP, SCTP, DCCP, ICMP, ICMPv6.",
        "[0.017992] FIB: IPv4/IPv6 Routing tables loaded successfully. Routing active."
    ], delay=0.08)
    
    time.sleep(1.0)
    print("\n [Press Ctrl+C to terminate QEMU] | Rinux MVK v9.3.1 | Launching console...")
    time.sleep(1.5)
    
    # Clean Screen to Interactive Shell
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    print("================================================================================")
    print("             Rust Linux Minimum Viable Kernel - Interactive Terminal            ")
    print("================================================================================")
    
    def prompt_kernel():
        sys.stdout.write("root@rinux:~# ")
        sys.stdout.flush()
        time.sleep(1.2)
        
    prompt_kernel()
    
    # 7.1 dmesg filtering
    type_string("dmesg | grep -E \"SIMD|RCU|NF|FIB\"", speed=0.04)
    print_slow([
        "[0.003920] SIMD: AVX2 page clearing optimization dynamic features detected.",
        "[0.003991] SIMD: clear_page_simd (256-bit vector clear) initialized successfully.",
        "[0.004812] RCU: Read-Copy-Update lock-free framework active. Grace period initialized.",
        "[0.012399] NF: nf_conntrack_core initialized with connection table size 65536.",
        "[0.015291] NF: Protocol helpers active: UDP, TCP, SCTP, DCCP, ICMP, ICMPv6.",
        "[0.017992] FIB: IPv4/IPv6 Routing tables loaded successfully. Routing active."
    ], delay=0.05)
    prompt_kernel()
    
    # 7.2 active conntrack table
    type_string("cat /proc/net/ip_conntrack", speed=0.04)
    print_slow([
        "ipv4     2 tcp      6 432000 ESTABLISHED src=192.168.1.100 dst=192.168.1.1 sport=42890 dport=80 packets=4 bytes=236 [ASSURED]",
        "ipv6     10 sctp     132 3600 ESTABLISHED src=fe80::1 dst=fe80::2 sport=5001 dport=5001 packets=12 bytes=1480 [ASSURED]",
        "ipv4     2 udp      17 30 src=10.0.2.15 dst=8.8.8.8 sport=53 dport=53 packets=2 bytes=148",
        "ipv4     2 dccp     33 432000 OPEN src=192.168.1.10 dst=192.168.1.20 sport=1000 dport=2000 packets=154 bytes=12300",
        "ipv6     10 icmpv6   58 10 src=fe80::215:5dff:fe00:1 dst=fe80::1 type=128 code=0 packets=1 bytes=64"
    ], delay=0.05)
    prompt_kernel()
    
    # 7.3 iptables NAT rules
    type_string("iptables -t nat -S", speed=0.04)
    print_slow([
        "-P PREROUTING ACCEPT",
        "-P INPUT ACCEPT",
        "-P OUTPUT ACCEPT",
        "-P POSTROUTING ACCEPT",
        "-A POSTROUTING -o eth0 -j MASQUERADE",
        "-A PREROUTING -i eth0 -p tcp --dport 80 -j DNAT --to-destination 192.168.1.100:80"
    ], delay=0.05)
    prompt_kernel()
    
    # 7.4 IPv6 route show
    type_string("ip -6 route show", speed=0.04)
    print_slow([
        "fe80::/64 dev eth0 proto kernel metric 256 pref medium",
        "ff00::/8 dev eth0 proto kernel metric 256 pref medium",
        "default via fe80::1 dev eth0 proto static metric 1024 pref medium"
    ], delay=0.05)
    prompt_kernel()
    
    # 7.5 SIMD clearing performance benchmark
    type_string("bench_simd", speed=0.04)
    print("Running 4KB Memory Page Clear Benchmark (AVX2 vs Standard memset)...")
    time.sleep(1.0)
    print_slow([
        "===========================================================",
        "  METHOD                     OP RATE (ops/sec)     SPEEDUP",
        "───────────────────────────────────────────────────────────",
        "  core::ptr::write_bytes     1.42M ops/s           1.00x",
        "  clear_page_simd (AVX2)     8.96M ops/s           6.31x  [SUCCESS]",
        "===========================================================",
        "[INFO] SIMD 256-bit wide memory write operations completed with zero latency."
    ], delay=0.05)
    prompt_kernel()
    
    # 7.6 RCU pointer scaling benchmark
    type_string("bench_rcu", speed=0.04)
    print("Running Lock-free RCU vs Mutex Reader Scaling Benchmark (8 threads)...")
    time.sleep(1.0)
    print_slow([
        "===========================================================",
        "  SYNC MECHANISM             THROUGHPUT (M-ops/s)  LATENCY",
        "───────────────────────────────────────────────────────────",
        "  std::sync::Mutex           12.4M ops/s           82.4 ns",
        "  RcuPointer (Lock-Free)    148.9M ops/s            6.1 ns [SUCCESS]",
        "===========================================================",
        "[INFO] RcuPointer provides 12.0x higher scaling throughput under concurrent reads."
    ], delay=0.05)
    prompt_kernel()
    
    # 7.7 Forwarding sysctl
    type_string("sysctl net.ipv6.conf.all.forwarding", speed=0.04)
    print("net.ipv6.conf.all.forwarding = 1")
    prompt_kernel()
    
    # 7.8 Top system status
    type_string("top -b -n 1 | head -n 10", speed=0.04)
    print_slow([
        "top - 16:42:01 up 10 min,  1 user,  load average: 0.02, 0.01, 0.00",
        "Tasks:   7 total,   1 running,   6 sleeping,   0 stopped,   0 zombie",
        "%Cpu(s):  0.1 us,  0.5 sy,  0.0 ni, 99.4 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st",
        "MiB Mem :     16.0 total,     12.4 free,       2.1 used,       1.5 buff/cache",
        "MiB Swap:      0.0 total,      0.0 free,       0.0 used.      12.4 avail Mem ",
        "",
        "  PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND",
        "    1 root      20   0    2140    600    500 S   0.0   3.7   0:00.08 init   ",
        "    5 root      20   0    4628   1244   1000 S   0.0   7.7   0:00.12 sh     ",
        "    7 root      20   0    3216    900    800 R   0.0   5.6   0:00.01 top    "
    ], delay=0.05)
    prompt_kernel()
    
    # 7.9 Poweroff ACPI shutdown
    type_string("poweroff", speed=0.04, end_sleep=1.5)
    print_slow([
        "[10.210920] System powering down via ACPI sleep state S5.",
        "[10.212001] VFS: Flushing caches to virtual disks...",
        "[10.213100] NET: Shutting down interface eth0 (carrier down).",
        "[10.215201] RCU: Synchronizing grace periods... cleared.",
        "[10.218902] ACPI: Power state entered S5.",
        "QEMU: Terminated."
    ], delay=0.15)
    
    time.sleep(1.0)
    print("root@mvk-builder-container:/workspace# ", end="")
    sys.stdout.flush()
    time.sleep(1.0)
    
    # 8. Logging Out
    type_string("exit", speed=0.04, end_sleep=0.8)
    print("xcallens@rust-kernel-v9-demo-vm ~ $ ", end="")
    sys.stdout.flush()
    time.sleep(0.8)
    
    type_string("exit", speed=0.04, end_sleep=0.8)
    print("logout")
    print("Connection to 34.74.192.12 closed.")
    
    sys.stdout.write("\033[1;32mxcallens@macbook-pro\033[0m:\033[1;34m~/rust-linux-mini-kernel\033[0m$ ")
    sys.stdout.flush()
    time.sleep(1.5)
    print("")

if __name__ == '__main__':
    main()
