FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Run as a non-root user; /data holds the conversation log
RUN useradd --create-home --uid 1000 anna \
    && mkdir -p /data \
    && chown -R anna:anna /app /data
USER anna

# Inside the container the app must listen on all interfaces;
# docker-compose publishes the port on 127.0.0.1 only.
ENV ANNA_HOST=0.0.0.0 \
    ANNA_PORT=8010 \
    ANNA_DB_PATH=/data/anna_history.sqlite3 \
    ANNA_KEY_FILE=/data/gemini_key.txt

EXPOSE 8010
VOLUME ["/data"]

CMD ["python", "anna.py"]
