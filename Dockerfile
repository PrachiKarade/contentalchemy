# ContentAlchemy - Streamlit app image
#
# Build:  docker build -t contentalchemy .
# Run:    docker compose up -d        (recommended: starts MongoDB and Azurite too)
#
# API keys are never baked into the image. Pass them at runtime with --env-file .env
# or through docker-compose.yml.

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Dependencies first so code changes don't invalidate the pip layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Application code and runtime configuration.
COPY src/ ./src/
COPY .streamlit/ ./.streamlit/
COPY inputs/ ./inputs/
COPY scripts/ ./scripts/

# Run as an unprivileged user. logs/ (src/core/logger.py) and generated/images/
# (local image storage) must be writable.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/logs /app/generated/images \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4).status == 200 else 1)"

CMD ["streamlit", "run", "src/web_app/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
