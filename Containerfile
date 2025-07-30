# ---------- Backend Build ----------
FROM registry.access.redhat.com/ubi9/python-312:latest

USER root
# Set working directory
WORKDIR /app

COPY test/ ./test
RUN pip install --no-cache-dir -r ./test/requirements.txt

COPY scripts/containers/entrypoint.sh ./entrypoint.sh

USER 1001

CMD ["./entrypoint.sh"]
