#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/mman.h>
#include <stdint.h>
#include <time.h>
#include <string.h>
#include <fcntl.h>

#define ITERATIONS 100000
#define PAGE_SIZE 4096

static inline uint64_t rdtsc() {
    unsigned int lo, hi;
    __asm__ __volatile__ ("rdtsc" : "=a" (lo), "=d" (hi));
    return ((uint64_t)hi << 32) | lo;
}

int main() {
    uint64_t start, end;
    
    // 4. IPC (Pipe) Benchmark
    int fd[2];
    pipe(fd);
    char buf[1] = {'x'};
    start = rdtsc();
    for (int i = 0; i < ITERATIONS; i++) {
        write(fd[1], buf, 1);
        read(fd[0], buf, 1);
    }
    end = rdtsc();
    printf("C-Kernel Baseline - IPC (Pipe R/W): %lu cycles/op\n", (end - start) / ITERATIONS);
    close(fd[0]);
    close(fd[1]);

    // 5. Page Fault Benchmark
    start = rdtsc();
    for (int i = 0; i < ITERATIONS/100; i++) {
        char *ptr = mmap(NULL, PAGE_SIZE, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        // Force a page fault by writing to unpopulated page
        ptr[0] = 'a';
        munmap(ptr, PAGE_SIZE);
    }
    end = rdtsc();
    printf("C-Kernel Baseline - Page Fault Latency: %lu cycles/op\n", (end - start) / (ITERATIONS/100));

    // 6. I/O Benchmark (/dev/null write)
    int null_fd = open("/dev/null", O_WRONLY);
    start = rdtsc();
    for (int i = 0; i < ITERATIONS; i++) {
        write(null_fd, buf, 1);
    }
    end = rdtsc();
    printf("C-Kernel Baseline - I/O (/dev/null): %lu cycles/op\n", (end - start) / ITERATIONS);
    close(null_fd);

    return 0;
}
