#!/bin/bash
#
# Deploy Rust Kernel Build System to Azure
# Creates Container App with build, test, and benchmark capabilities
#

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-rust-kernel}"
LOCATION="${LOCATION:-swedencentral}"
ACR_NAME="${ACR_NAME:-rustkernel}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-rustkernelstore}"
CONTAINER_ENV="${CONTAINER_ENV:-rust-kernel-env}"
CONTAINER_APP="${CONTAINER_APP:-rust-kernel-builder}"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║      DEPLOYING RUST KERNEL BUILD SYSTEM TO AZURE              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "ACR: $ACR_NAME"
echo ""

# Check Azure CLI
if ! command -v az &> /dev/null; then
    echo "❌ Azure CLI not found. Install from: https://docs.microsoft.com/cli/azure/install-azure-cli"
    exit 1
fi

# Login check
if ! az account show &> /dev/null; then
    echo "Please login to Azure..."
    az login
fi

SUBSCRIPTION_ID=$(az account show --query id -o tsv)
echo "Using subscription: $SUBSCRIPTION_ID"
echo ""

# Step 1: Create Resource Group
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Creating Resource Group"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

az group create \
    --name "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --tags project=rust-kernel-build purpose=ci-cd

echo "✅ Resource group created"
echo ""

# Step 2: Create Container Registry
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Creating Azure Container Registry"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

az acr create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$ACR_NAME" \
    --sku Basic \
    --admin-enabled true

echo "✅ Container registry created"
echo ""

# Step 3: Build and Push Docker Image
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Building and Pushing Docker Image"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Login to ACR
az acr login --name "$ACR_NAME"

# Build image
docker build -t "${ACR_NAME}.azurecr.io/rust-kernel-builder:latest" .

# Push image
docker push "${ACR_NAME}.azurecr.io/rust-kernel-builder:latest"

echo "✅ Docker image built and pushed"
echo ""

# Step 4: Create Storage Account
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4: Creating Storage Account"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

az storage account create \
    --name "$STORAGE_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --sku Standard_LRS \
    --kind StorageV2

# Create file share
STORAGE_KEY=$(az storage account keys list \
    --resource-group "$RESOURCE_GROUP" \
    --account-name "$STORAGE_ACCOUNT" \
    --query "[0].value" -o tsv)

az storage share create \
    --name workspace \
    --account-name "$STORAGE_ACCOUNT" \
    --account-key "$STORAGE_KEY" \
    --quota 100

az storage share create \
    --name results \
    --account-name "$STORAGE_ACCOUNT" \
    --account-key "$STORAGE_KEY" \
    --quota 50

echo "✅ Storage account and file shares created"
echo ""

# Step 5: Create Container Apps Environment
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 5: Creating Container Apps Environment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

az containerapp env create \
    --name "$CONTAINER_ENV" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION"

# Add storage to environment
az containerapp env storage set \
    --name "$CONTAINER_ENV" \
    --resource-group "$RESOURCE_GROUP" \
    --storage-name rust-kernel-storage \
    --azure-file-account-name "$STORAGE_ACCOUNT" \
    --azure-file-account-key "$STORAGE_KEY" \
    --azure-file-share-name workspace \
    --access-mode ReadWrite

echo "✅ Container Apps environment created"
echo ""

# Step 6: Create Container App
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 6: Creating Container App"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Get ACR credentials
ACR_USERNAME=$(az acr credential show --name "$ACR_NAME" --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)

az containerapp create \
    --name "$CONTAINER_APP" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINER_ENV" \
    --image "${ACR_NAME}.azurecr.io/rust-kernel-builder:latest" \
    --cpu 4.0 \
    --memory 8Gi \
    --min-replicas 0 \
    --max-replicas 1 \
    --registry-server "${ACR_NAME}.azurecr.io" \
    --registry-username "$ACR_USERNAME" \
    --registry-password "$ACR_PASSWORD" \
    --env-vars \
        WORKSPACE_ROOT=/workspace \
        PARALLEL_JOBS=4 \
        RUST_BACKTRACE=1

echo "✅ Container app created"
echo ""

# Step 7: Upload Repository Code
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 7: Uploading Repository Code"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Clone repo to temp directory
TEMP_DIR=$(mktemp -d)
cd "$TEMP_DIR"

git clone https://github.com/xaviercallens/rust-linux-mini-kernel.git
cd rust-linux-mini-kernel

# Upload to Azure Files
az storage file upload-batch \
    --destination workspace \
    --source . \
    --account-name "$STORAGE_ACCOUNT" \
    --account-key "$STORAGE_KEY" \
    --pattern "*" \
    --max-connections 10

cd ..
rm -rf "$TEMP_DIR"

echo "✅ Repository code uploaded"
echo ""

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              DEPLOYMENT COMPLETE                               ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Resource Group: $RESOURCE_GROUP"
echo "Container App: $CONTAINER_APP"
echo "Storage Account: $STORAGE_ACCOUNT"
echo ""
echo "Next Steps:"
echo "1. Run build: ./run_azure_build.sh"
echo "2. Run tests: ./run_azure_tests.sh"
echo "3. Run benchmarks: ./run_azure_benchmarks.sh"
echo ""
