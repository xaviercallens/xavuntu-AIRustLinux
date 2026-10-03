#!/bin/bash
set -e
docker build -t anse-sandbox:latest -f Dockerfile.sandbox .
DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' anse-sandbox:latest 2>/dev/null || echo "anse-sandbox:latest")
echo "Built image digest: $DIGEST"
