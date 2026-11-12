# Ephemeral execution sandbox image for CodeClan (codeclan-sandbox:latest)
# Supports: Python 3.11, C (gcc), C++17 (g++), Java (OpenJDK), JavaScript (Node.js)
#
# Containers launched from this image run with:
#   --network none --read-only --tmpfs /work:rw,exec,nosuid,nodev,size=32m
#   --memory 256m --cpus 0.5 --pids-limit 64 --cap-drop ALL
#   --security-opt no-new-privileges --user 65534:65534
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libc6-dev \
        default-jdk-headless \
        nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /work \
    && chmod 1777 /work

COPY sandbox_runner.py /usr/local/bin/sandbox-runner
RUN sed -i 's/\r$//' /usr/local/bin/sandbox-runner && chmod 0755 /usr/local/bin/sandbox-runner

WORKDIR /work
USER 65534:65534
