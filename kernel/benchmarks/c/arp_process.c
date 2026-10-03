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
