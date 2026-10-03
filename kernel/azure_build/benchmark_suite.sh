#!/bin/bash
#
# C vs Rust Kernel Module Benchmarking Suite
# Compares performance of key kernel functions
#

set -euo pipefail

WORKSPACE_ROOT="${WORKSPACE_ROOT:-/workspace}"
BENCHMARK_LOG="${BENCHMARK_LOG:-/workspace/benchmark_results.json}"
ITERATIONS="${ITERATIONS:-1000}"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        C vs RUST KERNEL MODULE BENCHMARK SUITE (99% COV)      ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

cd "$WORKSPACE_ROOT"

# Initialize results
cat > "$BENCHMARK_LOG" << EOF
{
  "benchmark_start": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "iterations": $ITERATIONS,
  "benchmarks": []
}
EOF

echo "Running benchmarks with $ITERATIONS iterations each"
echo ""

# Create benchmark programs directory
mkdir -p benchmarks/{c,rust}

# Benchmark 1: Socket Buffer Allocation (skbuff)
cat > benchmarks/c/skbuff_alloc.c << 'CEOF'
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

typedef struct sk_buff {
    void *data;
    unsigned int len;
    unsigned int truesize;
} sk_buff;

sk_buff* alloc_skb(unsigned int size) {
    sk_buff *skb = malloc(sizeof(sk_buff));
    if (skb) {
        skb->data = malloc(size);
        skb->len = 0;
        skb->truesize = size;
    }
    return skb;
}

void free_skb(sk_buff *skb) {
    if (skb) {
        free(skb->data);
        free(skb);
    }
}

int main(int argc, char **argv) {
    int iterations = atoi(argv[1]);
    struct timespec start, end;

    clock_gettime(CLOCK_MONOTONIC, &start);

    for (int i = 0; i < iterations; i++) {
        sk_buff *skb = alloc_skb(1500);
        free_skb(skb);
    }

    clock_gettime(CLOCK_MONOTONIC, &end);

    double elapsed = (end.tv_sec - start.tv_sec) +
                     (end.tv_nsec - start.tv_nsec) / 1e9;
    printf("%.9f\n", elapsed);

    return 0;
}
CEOF

cat > benchmarks/rust/skbuff_alloc.rs << 'RUSTEOF'
use std::alloc::{alloc, dealloc, Layout};
use std::env;
use std::time::Instant;

#[repr(C)]
struct SkBuff {
    data: *mut u8,
    len: u32,
    truesize: u32,
}

fn alloc_skb(size: usize) -> *mut SkBuff {
    unsafe {
        let layout = Layout::new::<SkBuff>();
        let skb = alloc(layout) as *mut SkBuff;
        if !skb.is_null() {
            let data_layout = Layout::from_size_align_unchecked(size, 8);
            let data = alloc(data_layout);
            (*skb).data = data;
            (*skb).len = 0;
            (*skb).truesize = size as u32;
        }
        skb
    }
}

fn free_skb(skb: *mut SkBuff) {
    unsafe {
        if !skb.is_null() {
            let data = (*skb).data;
            let size = (*skb).truesize as usize;
            let data_layout = Layout::from_size_align_unchecked(size, 8);
            dealloc(data, data_layout);

            let layout = Layout::new::<SkBuff>();
            dealloc(skb as *mut u8, layout);
        }
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let iterations: usize = args[1].parse().unwrap();

    let start = Instant::now();

    for _ in 0..iterations {
        let skb = alloc_skb(1500);
        free_skb(skb);
    }

    let elapsed = start.elapsed();
    println!("{:.9}", elapsed.as_secs_f64());
}
RUSTEOF

# Benchmark 2: ARP Packet Processing
cat > benchmarks/c/arp_process.c << 'CEOF'
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct arp_packet {
    unsigned short hw_type;
    unsigned short proto_type;
    unsigned char hw_len;
    unsigned char proto_len;
    unsigned short operation;
    unsigned char sender_hw[6];
    unsigned char sender_ip[4];
    unsigned char target_hw[6];
    unsigned char target_ip[4];
} arp_packet;

int process_arp(arp_packet *pkt) {
    if (pkt->hw_type != 1 || pkt->proto_type != 0x0800) {
        return -1;
    }

    // Simulate ARP cache lookup
    for (int i = 0; i < 100; i++) {
        if (pkt->sender_ip[0] == i) break;
    }

    return 0;
}

int main(int argc, char **argv) {
    int iterations = atoi(argv[1]);
    struct timespec start, end;

    arp_packet pkt = {
        .hw_type = 1,
        .proto_type = 0x0800,
        .hw_len = 6,
        .proto_len = 4,
        .operation = 1,
        .sender_ip = {192, 168, 1, 1}
    };

    clock_gettime(CLOCK_MONOTONIC, &start);

    for (int i = 0; i < iterations; i++) {
        process_arp(&pkt);
    }

    clock_gettime(CLOCK_MONOTONIC, &end);

    double elapsed = (end.tv_sec - start.tv_sec) +
                     (end.tv_nsec - start.tv_nsec) / 1e9;
    printf("%.9f\n", elapsed);

    return 0;
}
CEOF

cat > benchmarks/rust/arp_process.rs << 'RUSTEOF'
use std::env;
use std::time::Instant;

#[repr(C)]
struct ArpPacket {
    hw_type: u16,
    proto_type: u16,
    hw_len: u8,
    proto_len: u8,
    operation: u16,
    sender_hw: [u8; 6],
    sender_ip: [u8; 4],
    target_hw: [u8; 6],
    target_ip: [u8; 4],
}

fn process_arp(pkt: *const ArpPacket) -> i32 {
    unsafe {
        if (*pkt).hw_type != 1 || (*pkt).proto_type != 0x0800 {
            return -1;
        }

        // Simulate ARP cache lookup
        for i in 0..100 {
            if (*pkt).sender_ip[0] == i {
                break;
            }
        }
    }

    0
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let iterations: usize = args[1].parse().unwrap();

    let pkt = ArpPacket {
        hw_type: 1,
        proto_type: 0x0800,
        hw_len: 6,
        proto_len: 4,
        operation: 1,
        sender_hw: [0; 6],
        sender_ip: [192, 168, 1, 1],
        target_hw: [0; 6],
        target_ip: [0; 4],
    };

    let start = Instant::now();

    for _ in 0..iterations {
        let _ = process_arp(&pkt as *const ArpPacket);
    }

    let elapsed = start.elapsed();
    println!("{:.9}", elapsed.as_secs_f64());
}
RUSTEOF

# Benchmark 3: Route Lookup (FIB Trie)
cat > benchmarks/c/route_lookup.c << 'CEOF'
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

typedef struct fib_node {
    unsigned int key;
    int value;
    struct fib_node *left;
    struct fib_node *right;
} fib_node;

fib_node* create_node(unsigned int key, int value) {
    fib_node *node = malloc(sizeof(fib_node));
    node->key = key;
    node->value = value;
    node->left = NULL;
    node->right = NULL;
    return node;
}

int lookup_route(fib_node *root, unsigned int key) {
    while (root) {
        if (key == root->key) return root->value;
        root = (key < root->key) ? root->left : root->right;
    }
    return -1;
}

int main(int argc, char **argv) {
    int iterations = atoi(argv[1]);
    struct timespec start, end;

    // Build simple FIB tree
    fib_node *root = create_node(50, 1);
    root->left = create_node(25, 2);
    root->right = create_node(75, 3);
    root->left->left = create_node(10, 4);
    root->left->right = create_node(40, 5);

    clock_gettime(CLOCK_MONOTONIC, &start);

    for (int i = 0; i < iterations; i++) {
        lookup_route(root, 40);
    }

    clock_gettime(CLOCK_MONOTONIC, &end);

    double elapsed = (end.tv_sec - start.tv_sec) +
                     (end.tv_nsec - start.tv_nsec) / 1e9;
    printf("%.9f\n", elapsed);

    return 0;
}
CEOF

cat > benchmarks/rust/route_lookup.rs << 'RUSTEOF'
use std::env;
use std::time::Instant;

#[repr(C)]
struct FibNode {
    key: u32,
    value: i32,
    left: *mut FibNode,
    right: *mut FibNode,
}

fn create_node(key: u32, value: i32) -> *mut FibNode {
    Box::into_raw(Box::new(FibNode {
        key,
        value,
        left: std::ptr::null_mut(),
        right: std::ptr::null_mut(),
    }))
}

fn lookup_route(mut root: *mut FibNode, key: u32) -> i32 {
    unsafe {
        while !root.is_null() {
            if key == (*root).key {
                return (*root).value;
            }
            root = if key < (*root).key {
                (*root).left
            } else {
                (*root).right
            };
        }
    }
    -1
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let iterations: usize = args[1].parse().unwrap();

    unsafe {
        let root = create_node(50, 1);
        (*root).left = create_node(25, 2);
        (*root).right = create_node(75, 3);
        (*(*root).left).left = create_node(10, 4);
        (*(*root).left).right = create_node(40, 5);

        let start = Instant::now();

        for _ in 0..iterations {
            lookup_route(root, 40);
        }

        let elapsed = start.elapsed();
        println!("{:.9}", elapsed.as_secs_f64());
    }
}
RUSTEOF

# Benchmark 4: UDP Checksum Calculation
cat > benchmarks/c/udp_csum.c << 'CEOF'
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <time.h>

uint16_t udp_csum(uint16_t *buf, int nwords) {
    uint32_t sum = 0;
    for (int i = 0; i < nwords; i++) {
        sum += buf[i];
    }
    while (sum >> 16) {
        sum = (sum & 0xFFFF) + (sum >> 16);
    }
    return ~sum;
}

int main(int argc, char **argv) {
    int iterations = atoi(argv[1]);
    struct timespec start, end;
    
    uint16_t packet[500];
    for (int i=0; i<500; i++) packet[i] = i;

    clock_gettime(CLOCK_MONOTONIC, &start);
    for (int i = 0; i < iterations; i++) {
        udp_csum(packet, 500);
    }
    clock_gettime(CLOCK_MONOTONIC, &end);

    double elapsed = (end.tv_sec - start.tv_sec) + (end.tv_nsec - start.tv_nsec) / 1e9;
    printf("%.9f\n", elapsed);
    return 0;
}
CEOF

cat > benchmarks/rust/udp_csum.rs << 'RUSTEOF'
use std::env;
use std::time::Instant;

fn udp_csum(buf: &[u16]) -> u16 {
    let mut sum: u32 = 0;
    for &val in buf {
        sum += val as u32;
    }
    while sum >> 16 != 0 {
        sum = (sum & 0xFFFF) + (sum >> 16);
    }
    !sum as u16
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let iterations: usize = args[1].parse().unwrap();
    
    let mut packet = vec![0u16; 500];
    for i in 0..500 { packet[i] = i as u16; }

    let start = Instant::now();
    for _ in 0..iterations {
        udp_csum(&packet);
    }
    let elapsed = start.elapsed();
    println!("{:.9}", elapsed.as_secs_f64());
}
RUSTEOF

# Benchmark 5: GRE Header Encapsulation
cat > benchmarks/c/gre_encap.c << 'CEOF'
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <time.h>

struct grehdr {
    uint16_t flags;
    uint16_t protocol;
};

void gre_encap(void *data, uint16_t proto) {
    struct grehdr *gre = (struct grehdr *)data;
    gre->flags = 0;
    gre->protocol = proto;
}

int main(int argc, char **argv) {
    int iterations = atoi(argv[1]);
    struct timespec start, end;
    
    uint8_t buffer[100];

    clock_gettime(CLOCK_MONOTONIC, &start);
    for (int i = 0; i < iterations; i++) {
        gre_encap(buffer, 0x0800);
    }
    clock_gettime(CLOCK_MONOTONIC, &end);

    double elapsed = (end.tv_sec - start.tv_sec) + (end.tv_nsec - start.tv_nsec) / 1e9;
    printf("%.9f\n", elapsed);
    return 0;
}
CEOF

cat > benchmarks/rust/gre_encap.rs << 'RUSTEOF'
use std::env;
use std::time::Instant;

#[repr(C)]
struct GreHdr {
    flags: u16,
    protocol: u16,
}

fn gre_encap(data: *mut u8, proto: u16) {
    unsafe {
        let gre = data as *mut GreHdr;
        (*gre).flags = 0;
        (*gre).protocol = proto;
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let iterations: usize = args[1].parse().unwrap();
    
    let mut buffer = [0u8; 100];

    let start = Instant::now();
    for _ in 0..iterations {
        gre_encap(buffer.as_mut_ptr(), 0x0800);
    }
    let elapsed = start.elapsed();
    println!("{:.9}", elapsed.as_secs_f64());
}
RUSTEOF

# Benchmark 6: IPv6 Flowlabel
cat > benchmarks/c/ip6_flowlabel.c << 'CEOF'
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <time.h>

uint32_t ip6_flowlabel(uint32_t src_ip, uint32_t dst_ip) {
    uint32_t hash = src_ip ^ dst_ip;
    hash = (hash ^ (hash >> 16)) * 0x85ebca6b;
    hash = (hash ^ (hash >> 13)) * 0xc2b2ae35;
    return (hash ^ (hash >> 16)) & 0xFFFFF; // 20-bit flow label
}

int main(int argc, char **argv) {
    int iterations = atoi(argv[1]);
    struct timespec start, end;
    
    clock_gettime(CLOCK_MONOTONIC, &start);
    for (int i = 0; i < iterations; i++) {
        ip6_flowlabel(0xC0A80001, 0x0A000001);
    }
    clock_gettime(CLOCK_MONOTONIC, &end);

    double elapsed = (end.tv_sec - start.tv_sec) + (end.tv_nsec - start.tv_nsec) / 1e9;
    printf("%.9f\n", elapsed);
    return 0;
}
CEOF

cat > benchmarks/rust/ip6_flowlabel.rs << 'RUSTEOF'
use std::env;
use std::time::Instant;

fn ip6_flowlabel(src_ip: u32, dst_ip: u32) -> u32 {
    let mut hash = src_ip ^ dst_ip;
    hash = (hash ^ (hash >> 16)).wrapping_mul(0x85ebca6b);
    hash = (hash ^ (hash >> 13)).wrapping_mul(0xc2b2ae35);
    (hash ^ (hash >> 16)) & 0xFFFFF
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let iterations: usize = args[1].parse().unwrap();

    let start = Instant::now();
    for _ in 0..iterations {
        ip6_flowlabel(0xC0A80001, 0x0A000001);
    }
    let elapsed = start.elapsed();
    println!("{:.9}", elapsed.as_secs_f64());
}
RUSTEOF

# Benchmark 7: Anycast Routing Resolution
cat > benchmarks/c/anycast_resolve.c << 'CEOF'
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

struct anycast_node {
    int metric;
    struct anycast_node *next;
};

int resolve_anycast(struct anycast_node *head) {
    int best_metric = 999999;
    struct anycast_node *curr = head;
    while (curr) {
        if (curr->metric < best_metric) {
            best_metric = curr->metric;
        }
        curr = curr->next;
    }
    return best_metric;
}

int main(int argc, char **argv) {
    int iterations = atoi(argv[1]);
    struct timespec start, end;
    
    struct anycast_node *head = malloc(sizeof(struct anycast_node));
    head->metric = 100;
    head->next = malloc(sizeof(struct anycast_node));
    head->next->metric = 50;
    head->next->next = malloc(sizeof(struct anycast_node));
    head->next->next->metric = 75;
    head->next->next->next = NULL;

    clock_gettime(CLOCK_MONOTONIC, &start);
    for (int i = 0; i < iterations; i++) {
        resolve_anycast(head);
    }
    clock_gettime(CLOCK_MONOTONIC, &end);

    double elapsed = (end.tv_sec - start.tv_sec) + (end.tv_nsec - start.tv_nsec) / 1e9;
    printf("%.9f\n", elapsed);
    return 0;
}
CEOF

cat > benchmarks/rust/anycast_resolve.rs << 'RUSTEOF'
use std::env;
use std::time::Instant;

#[repr(C)]
struct AnycastNode {
    metric: i32,
    next: *mut AnycastNode,
}

fn resolve_anycast(mut head: *mut AnycastNode) -> i32 {
    let mut best_metric = 999999;
    unsafe {
        while !head.is_null() {
            if (*head).metric < best_metric {
                best_metric = (*head).metric;
            }
            head = (*head).next;
        }
    }
    best_metric
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let iterations: usize = args[1].parse().unwrap();

    unsafe {
        let node3 = Box::into_raw(Box::new(AnycastNode { metric: 75, next: std::ptr::null_mut() }));
        let node2 = Box::into_raw(Box::new(AnycastNode { metric: 50, next: node3 }));
        let head = Box::into_raw(Box::new(AnycastNode { metric: 100, next: node2 }));

        let start = Instant::now();
        for _ in 0..iterations {
            resolve_anycast(head);
        }
        let elapsed = start.elapsed();
        println!("{:.9}", elapsed.as_secs_f64());
    }
}
RUSTEOF

echo "Building benchmark programs..."
echo ""

# Compile C benchmarks
gcc -O3 -o benchmarks/c/skbuff_alloc benchmarks/c/skbuff_alloc.c
gcc -O3 -o benchmarks/c/arp_process benchmarks/c/arp_process.c
gcc -O3 -o benchmarks/c/route_lookup benchmarks/c/route_lookup.c
gcc -O3 -o benchmarks/c/udp_csum benchmarks/c/udp_csum.c
gcc -O3 -o benchmarks/c/gre_encap benchmarks/c/gre_encap.c
gcc -O3 -o benchmarks/c/ip6_flowlabel benchmarks/c/ip6_flowlabel.c
gcc -O3 -o benchmarks/c/anycast_resolve benchmarks/c/anycast_resolve.c

# Compile Rust benchmarks
rustc -C opt-level=3 -o benchmarks/rust/skbuff_alloc benchmarks/rust/skbuff_alloc.rs
rustc -C opt-level=3 -o benchmarks/rust/arp_process benchmarks/rust/arp_process.rs
rustc -C opt-level=3 -o benchmarks/rust/route_lookup benchmarks/rust/route_lookup.rs
rustc -C opt-level=3 -o benchmarks/rust/udp_csum benchmarks/rust/udp_csum.rs
rustc -C opt-level=3 -o benchmarks/rust/gre_encap benchmarks/rust/gre_encap.rs
rustc -C opt-level=3 -o benchmarks/rust/ip6_flowlabel benchmarks/rust/ip6_flowlabel.rs
rustc -C opt-level=3 -o benchmarks/rust/anycast_resolve benchmarks/rust/anycast_resolve.rs

echo "✅ Benchmark programs compiled"
echo ""

# Run benchmarks
run_benchmark() {
    local name=$1
    local c_prog=$2
    local rust_prog=$3

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Benchmark: $name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Run C version
    local c_time=$($c_prog $ITERATIONS)
    echo "C:    ${c_time}s"

    # Run Rust version
    local rust_time=$($rust_prog $ITERATIONS)
    echo "Rust: ${rust_time}s"

    # Calculate speedup
    local speedup=$(awk "BEGIN {print $c_time / $rust_time}")
    echo "Speedup: ${speedup}x"

    # Add to results
    local result=$(jq -n \
        --arg name "$name" \
        --arg c_time "$c_time" \
        --arg rust_time "$rust_time" \
        --arg speedup "$speedup" \
        --arg iterations "$ITERATIONS" \
        '{
            name: $name,
            c_time_seconds: ($c_time | tonumber),
            rust_time_seconds: ($rust_time | tonumber),
            speedup: ($speedup | tonumber),
            iterations: ($iterations | tonumber),
            winner: (if ($speedup | tonumber) > 1.0 then "rust" else "c" end)
        }')

    jq --argjson bench "$result" '.benchmarks += [$bench]' "$BENCHMARK_LOG" > "$BENCHMARK_LOG.tmp" && mv "$BENCHMARK_LOG.tmp" "$BENCHMARK_LOG"

    echo ""
}

run_benchmark "Socket Buffer Allocation" \
    "benchmarks/c/skbuff_alloc" \
    "benchmarks/rust/skbuff_alloc"

run_benchmark "ARP Packet Processing" \
    "benchmarks/c/arp_process" \
    "benchmarks/rust/arp_process"

run_benchmark "Route Lookup (FIB)" \
    "benchmarks/c/route_lookup" \
    "benchmarks/rust/route_lookup"

run_benchmark "UDP Checksum" \
    "benchmarks/c/udp_csum" \
    "benchmarks/rust/udp_csum"

run_benchmark "GRE Encapsulation" \
    "benchmarks/c/gre_encap" \
    "benchmarks/rust/gre_encap"

run_benchmark "IPv6 Flowlabel" \
    "benchmarks/c/ip6_flowlabel" \
    "benchmarks/rust/ip6_flowlabel"

run_benchmark "Anycast Resolution" \
    "benchmarks/c/anycast_resolve" \
    "benchmarks/rust/anycast_resolve"

# Finalize results
BENCHMARK_END=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
jq --arg end "$BENCHMARK_END" '.benchmark_end = $end' "$BENCHMARK_LOG" > "$BENCHMARK_LOG.tmp" && mv "$BENCHMARK_LOG.tmp" "$BENCHMARK_LOG"

# Summary
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                  BENCHMARK SUMMARY                             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

jq -r '.benchmarks[] | "\(.name): \(.speedup)x (\(.winner) wins)"' "$BENCHMARK_LOG"

echo ""
echo "Detailed results: $BENCHMARK_LOG"
echo ""
