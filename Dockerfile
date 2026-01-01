# =============================
# Base Image (Python 3.10)
# =============================
FROM python:3.10-slim

# =============================
# Environment
# =============================
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# =============================
# Workdir
# =============================
WORKDIR /app

# =============================
# System Dependencies
# (minimal but enough for faiss + llama-cpp)
# =============================
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# =============================
# Python Dependencies
# Install in STAGES to reduce RAM peak
# =============================

# 1️⃣ Core scientific stack (must be first)
COPY requirements.txt .
RUN pip install --prefer-binary \
    numpy \
    scipy \
    scikit-learn \
    joblib \
    threadpoolctl

# 2️⃣ Heavy native ML deps
RUN pip install --prefer-binary \
    faiss-cpu \
    llama-cpp-python

# 3️⃣ Remaining dependencies
RUN pip install --prefer-binary -r requirements.txt

# =============================
# App Source
# =============================
COPY . .

# =============================
# App Directories
# =============================
RUN mkdir -p /app/models /app/data

# =============================
# Expose Port (Render sets PORT)
# =============================
EXPOSE 8000

# =============================
# Start Server (Gunicorn)
# =============================
CMD gunicorn \
    -w 1 \
    -k sync \
    --timeout 180 \
    -b 0.0.0.0:${PORT:-8000} \
    app:app
