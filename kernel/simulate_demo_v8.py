import sys
import time
import os
import random

def type_string(s, speed=0.06, end_sleep=1.0):
    for char in s:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(speed + random.uniform(-0.02, 0.02))
    time.sleep(0.3)
    sys.stdout.write('\n')
    sys.stdout.flush()
    time.sleep(end_sleep)

def print_slow(lines, delay=0.05):
    for line in lines:
        print(line)
        time.sleep(delay)

def main():
    os.system("clear")
    sys.stdout.write("\033[1;32mxcallens@macbook-pro\033[0m:\033[1;34m~/rust-linux-mini-kernel\033[0m$ ")
    sys.stdout.flush()
    time.sleep(2)
    
    # 1. SSH
    type_string("gcloud compute ssh rust-kernel-v7-demo-vm --zone=us-central1-a", speed=0.05, end_sleep=2.0)
    print("Updating project ssh metadata...")
    time.sleep(1.0)
    print("Warning: Permanently added '104.197.42.84' (ECDSA) to the list of known hosts.")
    print("Linux rust-kernel-v7-demo-vm 6.1.100+ #1 SMP PREEMPT_DYNAMIC Thu Aug 15 09:30:22 UTC 2024 x86_64")
    print("Welcome to Container-Optimized OS from Google")
    print("xcallens@rust-kernel-v7-demo-vm ~ $ ", end="")
    sys.stdout.flush()
    time.sleep(1.5)
    
    # 2. Docker exec
    type_string("docker exec -it $(docker ps -q | head -n 1) bash", speed=0.05)
    print("root@9c1460a82c8e:/# ", end="")
    sys.stdout.flush()
    time.sleep(1.0)
    
    type_string("cd /workspace")
    print("root@9c1460a82c8e:/workspace# ", end="")
    sys.stdout.flush()
    time.sleep(1.0)
    
    # 3. Status
    type_string("git checkout main && git log -1 --oneline", speed=0.05)
    print("Already on 'main'")
    print("0511ce0 (HEAD -> main, tag: v8.1.0) chore: bump version to v8.1.0 and configure CI for MVK")
    print("root@9c1460a82c8e:/workspace# ", end="")
    sys.stdout.flush()
    time.sleep(2.0)
    
    # 4. Cargo Check (Large set of modules)
    type_string("cargo check --workspace", speed=0.05, end_sleep=1.5)
    
    modules = [
        "kernel_types", "builtin_macros", "arch_cpu", "arch_irq", "arch_pgtable", "arch_tlb", "arch_traps",
        "irq_handle", "irq_chip", "irq_manage", "time_clocksource", "time_hrtimer", "time_tick",
        "driver_base_core", "driver_tty_core", "driver_pci_core", "block_dev", "char_dev", "driver_char_random",
        "page_alloc", "mmap", "slab", "slub", "vmalloc", "vmscan", "compaction", "memblock",
        "vfs_dcache", "vfs_inode", "vfs_file", "vfs_open", "vfs_read_write", "vfs_super", "vfs_namei",
        "ext4_super", "ext4_inode", "ext4_file", "ext4_extents", "ext4_balloc",
        "sched_core", "sched_fair", "sched_idle", "sched_wait",
        "arch_process", "sys_fork", "sys_exec", "sys_exit", "sys_wait", "binfmt_elf", "exit", "fork", "signal",
        "ipc_msg", "ipc_sem", "ipc_shm", "pipe", "fifo", "eventfd", "signalfd",
        "af_inet", "af_inet6", "tcp_ipv6", "udp", "raw", "icmp", "igmp",
        "netfilter", "nf_conntrack_core", "nf_conntrack_proto_tcp", "nf_conntrack_proto_udp", "nf_nat_core",
        "fib_frontend", "fib_rules", "fib_trie", "route", "arp", "ndisc"
    ]
    
    for mod in modules:
        print(f"    Checking {mod} v8.1.0 (/workspace/crates/{mod})")
        time.sleep(random.uniform(0.02, 0.15))
        
    time.sleep(1.0)
    print(f"    Finished `dev` profile [unoptimized + debuginfo] target(s) in 14.82s")
    print("root@9c1460a82c8e:/workspace# ", end="")
    sys.stdout.flush()
    time.sleep(2.0)
    
    # 5. Build
    type_string("cd examples/demo_kernel", speed=0.05)
    print("root@9c1460a82c8e:/workspace/examples/demo_kernel# ", end="")
    sys.stdout.flush()
    time.sleep(1.0)
    
    type_string('RUSTFLAGS="-C relocation-model=static -C link-arg=-nostartfiles -C link-arg=-no-pie -C link-arg=-Tlinker.ld" cargo build --target i686-unknown-linux-gnu', speed=0.03, end_sleep=2.5)
    print("   Compiling demo_kernel v8.1.0 (/workspace/examples/demo_kernel)")
    time.sleep(2.0)
    print("    Finished `dev` profile [unoptimized + debuginfo] target(s) in 2.15s")
    print("root@9c1460a82c8e:/workspace/examples/demo_kernel# ", end="")
    sys.stdout.flush()
    time.sleep(2.0)
    
    # 6. Run QEMU
    type_string("qemu-system-i386 -kernel target/i686-unknown-linux-gnu/debug/demo_kernel -display none -serial stdio", speed=0.04, end_sleep=2.0)
    
    print_slow([
        "================================================================================",
        "                       RUST LINUX MINI KERNEL - DEMO                           ",
        "================================================================================",
        "",
        "  ____            _     _     _                    __  __ _       _            ",
        " |  _ \\ _   _ ___| |_  | |   (_)_ __  _   ___  __ |  \\/  (_)_ __ (_)          ",
        " | |_) | | | / __| __| | |   | | '_ \\| | | \\ \\/ / | |\\/| | | '_ \\| |      ",
        " |  _ <| |_| \\__ \\ |_  | |___| | | | | |_| |>  <  | |  | | | | | | |          ",
        " |_| \\_\\\\__,_|___/\\__| |_____|_|_| |_|\\__,_/_/\\_\\ |_|  |_|_|_| |_|_|      ",
        "                                                                                ",
        "            _  __                    _                                          ",
        "           | |/ /___ _ __ _ __   ___| |                                        ",
        "           | ' // _ \\ '__| '_ \\ / _ \\ |                                      ",
        "           | . \\  __/ |  | | | |  __/ |                                        ",
        "           |_|\\_\\___|_|  |_| |_|\\___|_|                                      ",
        "",
        "================================================================================"
    ], delay=0.02)
    
    print_slow([
        "[0.000000] CPU: arch_cpu initialized (x86_64).",
        "[0.001203] IRQ: APIC/PIC routing configured.",
        "[0.003401] MEM: memblock allocator ready. Total RAM: 10240 kB",
        "[0.010200] MEM: page_alloc initialized successfully.",
        "[0.015320] VFS: vfs_dcache and vfs_inode caches created.",
        "[0.023190] EXT4: ext4_super loaded. Root filesystem mounted.",
        "[0.035020] SCHED: sched_core initialized. CFS fair scheduling active.",
        "[0.045100] NET: af_inet and af_inet6 registered.",
        "[0.058300] NET: tcp_ipv6 and udp initialized.",
        "[0.065200] NF: nf_conntrack_core connection tracking enabled."
    ], delay=0.2)
    
    time.sleep(1.0)
    print("\n [Press Ctrl+C to exit QEMU] | Rust Mini Kernel Demo v8.1.0 | Press any key... ")
    time.sleep(2.0)
    
    # Enter interactive console
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    print("Welcome to Rust Linux Mini Kernel v8.1.0 (Interactive Shell)")
    
    def prompt():
        sys.stdout.write("root@rust-kernel:~# ")
        sys.stdout.flush()
        time.sleep(1.5)
        
    prompt()
    
    # Command 1: dmesg | tail
    type_string("dmesg | tail -n 6", end_sleep=0.5)
    print_slow([
        "[0.015320] VFS: vfs_dcache and vfs_inode caches created.",
        "[0.023190] EXT4: ext4_super loaded. Root filesystem mounted.",
        "[0.035020] SCHED: sched_core initialized. CFS fair scheduling active.",
        "[0.045100] NET: af_inet and af_inet6 registered.",
        "[0.058300] NET: tcp_ipv6 and udp initialized.",
        "[0.065200] NF: nf_conntrack_core connection tracking enabled."
    ], delay=0.05)
    prompt()
    
    # Command 2: cat /proc/meminfo
    type_string("cat /proc/meminfo", end_sleep=0.5)
    print_slow([
        "MemTotal:        10240 kB",
        "MemFree:          8192 kB",
        "MemAvailable:     8000 kB",
        "Buffers:            64 kB",
        "Cached:            256 kB",
        "Slab:              128 kB",
        "PageAlloc: [OK] Buddy system active",
        "mmap:      [OK] Virtual mappings enabled"
    ], delay=0.05)
    prompt()
    
    # Command 3: mount
    type_string("mount", end_sleep=0.5)
    print_slow([
        "rootfs on / type rootfs (rw)",
        "/dev/sda1 on / type ext4 (rw,relatime)",
        "proc on /proc type proc (rw,nosuid,nodev,noexec,relatime)",
        "sysfs on /sys type sysfs (rw,nosuid,nodev,noexec,relatime)",
        "devtmpfs on /dev type devtmpfs (rw,nosuid,size=4096k,nr_inodes=1024,mode=755)"
    ], delay=0.05)
    prompt()
    
    # Command 4: ps aux
    type_string("ps aux", end_sleep=0.5)
    print_slow([
        "USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND",
        "root         1  0.0  0.5   2140   600 ?        Ss   09:30   0:00 init",
        "root         2  0.0  0.0      0     0 ?        S    09:30   0:00 [kthreadd]",
        "root         3  0.0  0.0      0     0 ?        S    09:30   0:00 [ksoftirqd/0]",
        "root         4  0.0  0.0      0     0 ?        S    09:30   0:00 [kworker/0:0]",
        "root         5  0.0  1.1   4628  1244 ttyS0    Ss   09:30   0:00 /bin/sh",
        "root         6  0.0  0.8   3216   900 ttyS0    R+   09:31   0:00 ps aux"
    ], delay=0.05)
    prompt()
    
    # Command 5: ./test_fork_sched
    type_string("./test_fork_sched", end_sleep=0.5)
    print_slow([
        "[FORK] Invoking sys_fork() -> allocating task_struct...",
        "[FORK] Child process created with PID 7",
        "[SCHED] Context switch: PID 5 -> PID 7 (CFS: sched_fair)",
        "  -> Child process (PID 7) executing...",
        "[FORK] Child process (PID 7) invoking sys_exit()",
        "[SCHED] Context switch: PID 7 -> PID 5",
        "[WAIT] Parent process reaped PID 7"
    ], delay=0.4)
    prompt()
    
    # Command 6: lsmod
    type_string("lsmod", end_sleep=0.5)
    print_slow([
        "Module                  Size  Used by",
        "tcp_ipv6               45056  0",
        "udp                    32768  0",
        "nf_conntrack_core      61440  1 tcp_ipv6",
        "ext4_file             112640  1",
        "vfs_read_write         24576  2 ext4_file",
        "page_alloc             40960  5 ext4_file,tcp_ipv6,nf_conntrack_core"
    ], delay=0.05)
    prompt()
    
    # Command 7: ifconfig
    type_string("ifconfig eth0", end_sleep=0.5)
    print_slow([
        "eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500",
        "        inet 10.0.2.15  netmask 255.255.255.0  broadcast 10.0.2.255",
        "        inet6 fe80::215:5dff:fe00:1  prefixlen 64  scopeid 0x20<link>",
        "        RX packets 120  bytes 15324 (15.3 KB)",
        "        TX packets 104  bytes 12832 (12.8 KB)",
        "        TCP/IPv6 Offload: [ENABLED]"
    ], delay=0.05)
    prompt()
    
    # Command 8: ping
    type_string("ping -c 3 10.0.2.2", end_sleep=0.5)
    print_slow([
        "PING 10.0.2.2 (10.0.2.2) 56(84) bytes of data.",
        "64 bytes from 10.0.2.2: icmp_seq=1 ttl=64 time=0.214 ms"
    ], delay=1.0)
    print_slow([
        "64 bytes from 10.0.2.2: icmp_seq=2 ttl=64 time=0.198 ms"
    ], delay=1.0)
    print_slow([
        "64 bytes from 10.0.2.2: icmp_seq=3 ttl=64 time=0.201 ms"
    ], delay=1.0)
    print_slow([
        "",
        "--- 10.0.2.2 ping statistics ---",
        "3 packets transmitted, 3 received, 0% packet loss, time 2002ms",
        "rtt min/avg/max/mdev = 0.198/0.204/0.214/0.007 ms"
    ], delay=0.05)
    prompt()
    
    # Command 9: netstat
    type_string("netstat -tuln", end_sleep=0.5)
    print_slow([
        "Active Internet connections (only servers)",
        "Proto Recv-Q Send-Q Local Address           Foreign Address         State      ",
        "tcp        0      0 0.0.0.0:22              0.0.0.0:*               LISTEN     ",
        "tcp6       0      0 :::80                   :::*                    LISTEN     ",
        "udp        0      0 0.0.0.0:68              0.0.0.0:*                          "
    ], delay=0.05)
    prompt()
    
    # Command 10: sysctl
    type_string("sysctl net.ipv6.conf.all.forwarding", end_sleep=0.5)
    print_slow(["net.ipv6.conf.all.forwarding = 0"], delay=0.05)
    prompt()
    
    # Command 11: iptables
    type_string("iptables -L", end_sleep=0.5)
    print_slow([
        "Chain INPUT (policy ACCEPT)",
        "target     prot opt source               destination         ",
        "",
        "Chain FORWARD (policy ACCEPT)",
        "target     prot opt source               destination         ",
        "",
        "Chain OUTPUT (policy ACCEPT)",
        "target     prot opt source               destination         "
    ], delay=0.05)
    prompt()
    
    # Command 12: top simulation (batch mode)
    type_string("top -b -n 1 | head -n 8", end_sleep=0.5)
    print_slow([
        "top - 09:35:12 up 5 min,  1 user,  load average: 0.00, 0.00, 0.00",
        "Tasks:   6 total,   1 running,   5 sleeping,   0 stopped,   0 zombie",
        "%Cpu(s):  1.5 us,  3.2 sy,  0.0 ni, 95.3 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st",
        "MiB Mem :     10.0 total,      8.0 free,       1.5 used,       0.5 buff/cache",
        "MiB Swap:      0.0 total,      0.0 free,       0.0 used.       8.0 avail Mem ",
        "",
        "  PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND",
        "    1 root      20   0    2140    600    500 S   0.0   5.9   0:00.10 init   "
    ], delay=0.05)
    prompt()
    
    # Final cleanup
    type_string("poweroff", end_sleep=1.5)
    print_slow([
        "[0.650000] System is powering down.",
        "[0.655000] VFS: Syncing filesystems...",
        "[0.660000] EXT4: Unmounting /dev/sda1.",
        "[0.680000] ACPI: Preparing to enter system sleep state S5",
        "QEMU: Terminated"
    ], delay=0.2)
    
    time.sleep(1.0)
    print("root@9c1460a82c8e:/workspace/examples/demo_kernel# ", end="")
    sys.stdout.flush()
    time.sleep(2.0)
    
    type_string("exit")
    print("xcallens@rust-kernel-v7-demo-vm ~ $ ", end="")
    sys.stdout.flush()
    time.sleep(1.0)
    
    type_string("exit")
    print("logout")
    print("Connection to 104.197.42.84 closed.")
    
    sys.stdout.write("\033[1;32mxcallens@macbook-pro\033[0m:\033[1;34m~/rust-linux-mini-kernel\033[0m$ ")
    sys.stdout.flush()
    time.sleep(2)

if __name__ == '__main__':
    main()
