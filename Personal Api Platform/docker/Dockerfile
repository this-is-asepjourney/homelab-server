FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    mariadb-client \
    tar \
    gzip \
    && rm -rf /var/lib/apt/lists/*

COPY ["Personal Api Platform/requirements.txt", "./"]
RUN pip install --no-cache-dir -r requirements.txt

# Single Source of Truth: Copy PAP Core & PSM Control Plane
COPY ["Personal Api Platform/app", "./app"]
COPY ["Personal_Server_Manager/apps/api", "./apps/api"]
COPY ["Personal Api Platform/migrations", "./migrations"]
COPY ["Personal Api Platform/alembic.ini", "./alembic.ini"]

# Ensure directories for backups and storage exist
RUN mkdir -p /app/backups /opt/psm/uploads /opt/psm/releases

RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app /opt/psm

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
