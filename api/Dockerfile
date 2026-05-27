FROM python:3.12-slim

WORKDIR /app

# Install build deps for passlib/cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/
COPY alembic.ini alembic.ini
COPY alembic/ alembic/

# Install the package normally (not editable) to prevent auto-reload
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "glow_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
