# Build context : la racine du dépôt (needs packages/revkit + engine-rs).
#   docker build -f backend/Dockerfile -t traversal-backend .

# --- Bot natif : module Python `traversal_rs` compilé depuis engine-rs (Rust) ----------
FROM python:3.12-slim AS engine
RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain 1.83.0
ENV PATH=/root/.cargo/bin:$PATH PIP_NO_CACHE_DIR=1
RUN pip install maturin==1.7.8
COPY engine-rs /engine
RUN cd /engine/py && maturin build --release --locked -o /wheels

# --- Backend ---------------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Shared framework first (better layer caching).
COPY packages/revkit /src/revkit
RUN pip install /src/revkit

COPY --from=engine /wheels /wheels
RUN pip install /wheels/*.whl

# Site backend.
COPY backend /src/backend
RUN pip install /src/backend

WORKDIR /src/backend
EXPOSE 8000
# Scaleway Serverless Containers inject $PORT.
# Flux SSE ouverts : sans délai, un arrêt (redéploiement, scale-down) attendrait leur fin
# indéfiniment. Les navigateurs se reconnectent tout seuls à une autre instance.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-graceful-shutdown 5"]
