FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# The rules classifier (default) needs only the base dependencies below. Serving
# a fine-tuned BanglaBERT checkpoint (PROTIDHONI_FINE_TUNED_MODEL_PATH) needs
# torch/transformers too, which adds ~1GB to the image, so it is opt-in:
#   docker compose build ai-service --build-arg INSTALL_MODEL_EXTRAS=true
ARG INSTALL_MODEL_EXTRAS=false

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN if [ "$INSTALL_MODEL_EXTRAS" = "true" ]; then \
      apt-get update && apt-get install --no-install-recommends -y git \
      && rm -rf /var/lib/apt/lists/* \
      && pip install --no-cache-dir ".[model]"; \
    else \
      pip install --no-cache-dir .; \
    fi

EXPOSE 8001
CMD ["uvicorn", "protidhoni_ai.main:app", "--host", "0.0.0.0", "--port", "8001"]
