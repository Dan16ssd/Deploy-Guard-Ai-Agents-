FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app

# Default command = the webhook web server (binds 0.0.0.0:$PORT, default 8000). This image
# is shared by all 6 services; the 5 agent workers override this via their Railway "Custom
# Start Command" (e.g. `python -m agents.scan_agent`), which takes precedence over CMD. The
# webhook needs no override, so it boots correctly even if no start command is set.
CMD ["python", "-m", "webhook.main"]
