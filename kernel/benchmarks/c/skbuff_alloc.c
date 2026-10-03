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
