# Streamable-HTTP container for shelly-mcp (see src/shelly_mcp/http.py).
# Pin the base by digest when building for production: --build-arg PY_IMAGE=python:3.12-slim@sha256:...
ARG PY_IMAGE=python:3.12-slim
FROM ${PY_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    XDG_CONFIG_HOME=/config XDG_STATE_HOME=/state \
    SHELLY_MCP_HOST=0.0.0.0 SHELLY_MCP_PORT=8765

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir uv \
 && uv pip install --system --no-cache . \
 && pip uninstall -y uv

USER 99:100
EXPOSE 8765
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/healthz').status==200 else 1)"
CMD ["shelly-mcp-http"]
