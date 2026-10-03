#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/mman.h>
#include <pthread.h>
#include <stdint.h>
#include <time.h>

#define ITERATIONS 1000000

static inline uint64_t rdtsc() {
    unsigned int lo, hi;
    __asm__ __volatile__ ("rdtsc" : "=a" (lo), "=d" (hi));
    return ((uint64_t)hi << 32) | lo;
}

void* thread_func(void* arg) {
    return NULL;
}

int main() {
    uint64_t start, end;
    
    // 1. Syscall Benchmark (getpid)
    start = rdtsc();
    for (int i = 0; i < ITERATIONS; i++) {
        getpid();
    }
    end = rdtsc();
    printf("C-Kernel Baseline - Syscall (getpid): %lu cycles/op\n", (end - start) / ITERATIONS);
    
    // 2. Memory Allocation Benchmark (mmap)
    start = rdtsc();
    for (int i = 0; i < ITERATIONS/100; i++) {
        void* ptr = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        munmap(ptr, 4096);
    }
    end = rdtsc();
    printf("C-Kernel Baseline - Mem Alloc (mmap): %lu cycles/op\n", (end - start) / (ITERATIONS/100));

    // 3. Thread Spawning Benchmark (pthread)
    start = rdtsc();
    for (int i = 0; i < ITERATIONS/1000; i++) {
        pthread_t t;
        pthread_create(&t, NULL, thread_func, NULL);
        pthread_join(t, NULL);
    }
    end = rdtsc();
    printf("C-Kernel Baseline - Thread Spawn/Join: %lu cycles/op\n", (end - start) / (ITERATIONS/1000));

    return 0;
}
