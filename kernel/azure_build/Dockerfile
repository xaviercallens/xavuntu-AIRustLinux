# Azure Build Container for Rust Kernel Modules
# Includes Rust toolchain, Linux headers, and benchmarking tools

FROM rust:1.82-slim-bookworm

LABEL maintainer="rust-linux-mini-kernel"
LABEL description="Build and test environment for Rust Linux kernel FFI modules"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    make \
    pkg-config \
    linux-headers-generic \
    libclang-dev \
    clang \
    llvm \
    git \
    curl \
    jq \
    python3 \
    python3-pip \
    time \
    perf-tools-unstable \
    valgrind \
    strace \
    && rm -rf /var/lib/apt/lists/*

# Install Rust components
RUN rustup component add rustfmt clippy rust-src
RUN rustup target add x86_64-unknown-linux-gnu

# Skip cargo tools due to edition2024 requirements in dependencies
# hyperfine can be replaced with 'time' command for benchmarking

# Install Python dependencies for analysis
RUN pip3 install --no-cache-dir --break-system-packages \
    pandas \
    matplotlib \
    seaborn \
    numpy \
    pytest

# Set up workspace
WORKDIR /workspace

# Copy build scripts
COPY build_all.sh /usr/local/bin/
COPY test_all.sh /usr/local/bin/
COPY benchmark_suite.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/build_all.sh \
    /usr/local/bin/test_all.sh \
    /usr/local/bin/benchmark_suite.sh

# Environment variables
ENV RUST_BACKTRACE=1
ENV CARGO_NET_GIT_FETCH_WITH_CLI=true
ENV RUSTFLAGS="-C target-cpu=native -C opt-level=3"

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD rustc --version || exit 1

CMD ["/bin/bash"]
