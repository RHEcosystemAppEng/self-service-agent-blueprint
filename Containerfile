# ---------- Backend Build ----------
FROM registry.access.redhat.com/ubi9/python-312:latest

USER root
RUN dnf update -y && dnf clean all
RUN pip3 install --no-cache-dir uv
WORKDIR /app

COPY test/ ./test
COPY asset-manager/ ./asset-manager
COPY scripts/containers/entrypoint.sh ./entrypoint.sh
COPY pyproject.toml .
COPY uv.lock .
RUN uv sync --frozen --no-cache

# Set up paths
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/asset-manager/src:$PYTHONPATH"

USER 1001

CMD ["./entrypoint.sh"]
