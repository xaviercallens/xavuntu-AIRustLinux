#!/bin/bash
#
# Deploy Azure Codex Compilation Fixer as Overnight Batch Job
# Runs on Azure Container Instances with 3 parallel endpoints
#

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-rust-kernel}"
LOCATION="${LOCATION:-swedencentral}"
CONTAINER_NAME="codex-compiler-$(date +%Y%m%d-%H%M%S)"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-ruststore64044}"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     AZURE CODEX COMPILATION FIXER - OVERNIGHT BATCH           ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check required environment variables
if [ -z "${AZURE_OPENAI_ENDPOINT_1:-}" ] || [ -z "${AZURE_OPENAI_KEY_1:-}" ]; then
    echo "❌ Azure OpenAI credentials not set"
    echo ""
    echo "Required environment variables:"
    echo "  AZURE_OPENAI_ENDPOINT_1, AZURE_OPENAI_KEY_1"
    echo "  AZURE_OPENAI_ENDPOINT_2, AZURE_OPENAI_KEY_2 (optional)"
    echo "  AZURE_OPENAI_ENDPOINT_3, AZURE_OPENAI_KEY_3 (optional)"
    exit 1
fi

echo "✅ Azure OpenAI credentials configured"
echo ""

# Get storage account key
STORAGE_KEY=$(az storage account keys list \
    --resource-group "$RESOURCE_GROUP" \
    --account-name "$STORAGE_ACCOUNT" \
    --query "[0].value" -o tsv)

echo "✅ Storage account accessed"
echo ""

# Create Docker image for compilation fixer
echo "Building Docker image..."
cat > Dockerfile.codex << 'EOF'
FROM rust:1.82-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    make \
    pkg-config \
    linux-headers-generic \
    libclang-dev \
    python3 \
    python3-pip \
    git \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install Rust components
RUN rustup component add rustfmt clippy rust-src

# Install Python dependencies
RUN pip3 install --no-cache-dir --break-system-packages \
    requests \
    openai

# Copy workspace code
WORKDIR /workspace
COPY Cargo.toml ./
COPY crates ./crates/

# Copy compilation fixer script
COPY azure_codex_compiler/codex_compilation_fixer.py /usr/local/bin/
RUN chmod +x /usr/local/bin/codex_compilation_fixer.py

# Set environment
ENV RUST_BACKTRACE=1

CMD ["/usr/local/bin/codex_compilation_fixer.py"]
EOF

# Build and push to ACR
ACR_NAME="rustkernel64044"
IMAGE_NAME="codex-compiler:latest"

echo "Building Docker image in ACR..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
az acr build \
    --registry "$ACR_NAME" \
    --image "$IMAGE_NAME" \
    --file azure_codex_compiler/Dockerfile.codex \
    . \
    --no-logs

echo "✅ Docker image built"
echo ""

# Deploy as Azure Container Instance for overnight batch run
echo "Deploying as Azure Container Instance..."

az container create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$CONTAINER_NAME" \
    --image "${ACR_NAME}.azurecr.io/${IMAGE_NAME}" \
    --os-type Linux \
    --cpu 4 \
    --memory 16 \
    --restart-policy Never \
    --registry-login-server "${ACR_NAME}.azurecr.io" \
    --registry-username "$(az acr credential show --name $ACR_NAME --query username -o tsv)" \
    --registry-password "$(az acr credential show --name $ACR_NAME --query 'passwords[0].value' -o tsv)" \
    --environment-variables \
        AZURE_OPENAI_ENDPOINT_1="$AZURE_OPENAI_ENDPOINT_1" \
        AZURE_OPENAI_KEY_1="$AZURE_OPENAI_KEY_1" \
        AZURE_OPENAI_DEPLOYMENT_1="${AZURE_OPENAI_DEPLOYMENT_1:-gpt-4}" \
        AZURE_OPENAI_ENDPOINT_2="${AZURE_OPENAI_ENDPOINT_2:-}" \
        AZURE_OPENAI_KEY_2="${AZURE_OPENAI_KEY_2:-}" \
        AZURE_OPENAI_DEPLOYMENT_2="${AZURE_OPENAI_DEPLOYMENT_2:-gpt-4}" \
        AZURE_OPENAI_ENDPOINT_3="${AZURE_OPENAI_ENDPOINT_3:-}" \
        AZURE_OPENAI_KEY_3="${AZURE_OPENAI_KEY_3:-}" \
        AZURE_OPENAI_DEPLOYMENT_3="${AZURE_OPENAI_DEPLOYMENT_3:-gpt-4}" \
        WORKSPACE_ROOT="/workspace"

echo "✅ Container instance deployed: $CONTAINER_NAME"
echo ""

# Monitor execution
echo "Monitor with:"
echo "  az container logs --resource-group $RESOURCE_GROUP --name $CONTAINER_NAME --follow"
echo ""
echo "Check status:"
echo "  az container show --resource-group $RESOURCE_GROUP --name $CONTAINER_NAME --query instanceView.state"
echo ""
echo "Expected runtime: 6-8 hours overnight"
echo "Results will be saved to /workspace/compilation_fixes/"
