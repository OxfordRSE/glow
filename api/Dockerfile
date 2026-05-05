FROM python:3.12-slim

WORKDIR /app

# Install build deps for passlib/cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/

# Install the package and its dependencies
RUN pip install --no-cache-dir -e .

COPY alembic.ini alembic.ini
COPY alembic/ alembic/

EXPOSE 8000

CMD ["uvicorn", "ib_ox_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
