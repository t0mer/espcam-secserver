FROM python:3.12-slim

LABEL maintainer="tomer.klein@gmail.com"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    PORT=8000

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY app /app

# Run as a non-root user on an unprivileged port.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["python3", "/app/app.py"]
