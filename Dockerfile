FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

# Install system dependencies for OpenCV and SQLite
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    sqlite3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install lean production dependencies
COPY requirements.txt /workspace/
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# Copy ONNX model asset and verify session initialization
COPY yolov8n.onnx /workspace/
RUN python3 -c "import onnxruntime as ort; ort.InferenceSession('yolov8n.onnx')"

# Copy application source code
COPY detection/ /workspace/detection/
COPY server/ /workspace/server/
COPY storage/ /workspace/storage/
COPY simulation/ /workspace/simulation/
COPY tools/ /workspace/tools/
COPY tests/ /workspace/tests/
COPY config/ /workspace/config/

# Copy entrypoint script
COPY docker-entrypoint.sh /workspace/docker-entrypoint.sh
RUN chmod +x /workspace/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/workspace/docker-entrypoint.sh"]
CMD ["server"]
