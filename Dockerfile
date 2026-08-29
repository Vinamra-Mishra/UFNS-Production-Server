# Multi-stage production build for UFNS Polyglot Architecture
FROM python:3.12-slim-bookworm AS base

# Install system dependencies & C++ build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    g++ \
    libgomp1 \
    curl \
    git \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged system user
RUN useradd -u 1001 -r -s /bin/false appuser

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source tree
COPY . .

# Compile C++20 Shared Library for Linux
RUN cd cpp_core && \
    g++ -std=c++20 -O3 -fopenmp -fPIC -shared \
    solver_2d.cpp optical_flow.cpp routing.cpp physics_engine.cpp \
    -o libufns_physics.so && \
    cd ..

# Grant ownership only to directories requiring runtime writes
RUN mkdir -p /app/data && chown -R appuser:appuser /app/data /app/services

# Expose FastAPI port
EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8000

USER appuser

CMD ["uvicorn", "apps.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
