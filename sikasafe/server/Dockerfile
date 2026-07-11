# SikaSafe community backend — dependency-free (Python standard library + SQLite).
# No pip install, no build step. SQLite lives on a mounted volume so reports
# survive restarts and redeploys.
FROM python:3.12-slim

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 sika
WORKDIR /app
COPY server.py .

ENV SIKA_DB=/data/sikasafe.db \
    PORT=8791 \
    PYTHONUNBUFFERED=1

RUN mkdir -p /data && chown sika:sika /data
VOLUME ["/data"]
USER sika
EXPOSE 8791

# Container-level health check hits the app's own endpoint.
HEALTHCHECK --interval=30s --timeout=4s --start-period=5s --retries=3 \
  CMD python3 -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8791')+'/api/health', timeout=3)" || exit 1

CMD ["python3", "server.py"]
