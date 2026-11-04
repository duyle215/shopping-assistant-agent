FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 5000

# One worker: chat sessions live in memory. Threads handle concurrent requests.
CMD ["gunicorn", "--workers", "1", "--threads", "8", "--timeout", "180", \
     "--bind", "0.0.0.0:5000", "--access-logfile", "-", "run:app"]
