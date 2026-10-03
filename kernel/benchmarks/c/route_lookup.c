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
