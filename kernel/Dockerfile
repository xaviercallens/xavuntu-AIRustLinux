# Stage 1: Builder
FROM rust:1.80-slim as builder
WORKDIR /usr/src/app
COPY . .
# Note: we are passing TARGET_DIR to avoid conflicting with the local host
RUN cargo build -p micro_kernel_demo --release --target-dir=/tmp/target

# Stage 2: Runtime
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y ca-certificates python3 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /tmp/target/release/micro_kernel_hosted /app/micro_kernel_demo

# Cloud Run wrapper script
RUN echo '#!/bin/bash\n\
/app/micro_kernel_demo &\n\
echo "micro_kernel_demo running in background."\n\
echo -e "HTTP/1.1 200 OK\\n\\nKernel Demo Running!" > index.html\n\
python3 -m http.server ${PORT:-8080}\n\
' > /app/run.sh && chmod +x /app/run.sh

CMD ["/app/run.sh"]
