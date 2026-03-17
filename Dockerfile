# Control panel + Discord bridge — one container for Unraid or any host
FROM python:3.12-slim

ENV CLAUDESPACE_ROOT=/app
WORKDIR /app

# Minimal copy: scripts + dashboard + discord-bridge
COPY scripts/ /app/scripts/
COPY projects/bot-dashboard/ /app/projects/bot-dashboard/
COPY projects/discord-bridge/ /app/projects/discord-bridge/

# Placeholders so dashboard can write state/logs
RUN mkdir -p /app/.state /app/logs

# Install deps for both
RUN pip install --no-cache-dir -q -r /app/projects/bot-dashboard/requirements.txt \
    && pip install --no-cache-dir -q -r /app/projects/discord-bridge/requirements.txt

RUN chmod +x /app/scripts/docker-entrypoint.sh

EXPOSE 5050

# Bind to 0.0.0.0 in container so port is reachable from host
ENV FLASK_HOST=0.0.0.0
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
