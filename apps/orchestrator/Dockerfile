FROM python:3.11-slim

# cadquery's OpenCascade bindings (OCP) dynamically link against OpenGL/X11
# libraries even for headless STEP/STL export - without these the import
# fails at container startup, not at request time.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglu1-mesa libxrender1 libxext6 libsm6 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
RUN uv sync --frozen --no-dev

# Project data (uploaded planos, generated STEP/STL/G-code, project JSON).
# Mount a persistent volume here in production or it resets on every deploy.
ENV AXISCAM_STORAGE_DIR=/data
VOLUME ["/data"]

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
