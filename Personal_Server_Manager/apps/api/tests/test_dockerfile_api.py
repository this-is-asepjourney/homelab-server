import os
import pytest

# Ensure fast SQLite database for unit test
os.environ["DATABASE_URL"] = "sqlite:///./test_fast.db"
os.environ["POSTGRES_HOST"] = "127.0.0.1"

from fastapi.testclient import TestClient
from apps.api.app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_dockerfile_templates_endpoint(client):
    res = client.get("/api/v1/projects/dockerfile/templates")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "templates" in data
    assert "nextjs" in data["templates"]
    assert "vite_spa" in data["templates"]
    assert "fastapi" in data["templates"]
    assert "laravel" in data["templates"]


def test_dockerfile_generate_preview_endpoint(client):
    res = client.post(
        "/api/v1/projects/dockerfile/generate",
        json={"framework": "Next.js", "port": 3000, "project_name": "pos-cashier"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["template_key"] == "nextjs"
    assert "FROM node:20-alpine AS deps" in data["dockerfile"]
    assert "USER nextjs" in data["dockerfile"]
    assert "node_modules" in data["dockerignore"]


def test_dockerfile_generate_preview_vite(client):
    res = client.post(
        "/api/v1/projects/dockerfile/generate",
        json={"framework": "React / Vite", "port": 80, "project_name": "frontend-spa"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["template_key"] == "vite_spa"
    assert "FROM nginx:alpine AS runner" in data["dockerfile"]
    assert "try_files" in data["dockerfile"]
    assert "index.html" in data["dockerfile"]


def test_dockerfile_generate_additional_frameworks_and_default_port(client):
    res_laravel = client.post(
        "/api/v1/projects/dockerfile/generate",
        json={"framework": "Laravel", "port": None, "project_name": "simrs-app"},
    )
    assert res_laravel.status_code == 200
    data_laravel = res_laravel.json()
    assert data_laravel["success"] is True
    assert data_laravel["template_key"] == "laravel"
    assert data_laravel["recommended_port"] == 8080
    assert "EXPOSE 8080" in data_laravel["dockerfile"]

    res_compose = client.post(
        "/api/v1/projects/dockerfile/generate",
        json={"framework": "Docker Compose", "project_name": "stack-app"},
    )
    assert res_compose.status_code == 200
    data_compose = res_compose.json()
    assert data_compose["success"] is True
    assert bool(data_compose["dockerfile"]) is True
