# ---------- Backend Build ----------
FROM registry.access.redhat.com/ubi9/python-312:latest

USER root
RUN dnf update -y && dnf clean all
RUN pip3 install --no-cache-dir uv
WORKDIR /app

COPY test/ ./test
COPY asset-manager/ ./asset-manager
COPY slack-service/src/ ./slack-service/src/
COPY session-manager/src/ ./session-manager/src/
COPY pyproject.toml .
COPY uv.lock .
RUN uv sync --frozen --no-cache

# Set up paths
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/asset-manager/src:/app/slack-service/src:/app/session-manager/src:$PYTHONPATH"

USER 1001

EXPOSE 8080

WORKDIR /app/slack-service/src

CMD ["gunicorn", "--workers", "1", "--bind", "0.0.0.0:8080", "--timeout", "120", "slack_service.app:create_app()"]
