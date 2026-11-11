import os
import pytest
from apps.agent.app.deployment.dockerfile_generator import (
    detect_project_stack,
    generate_dockerfile,
    generate_dockerignore,
    ensure_dockerfile_and_ignore,
    get_available_templates,
    TEMPLATES,
)
from apps.agent.app.deployment.builder import DeploymentEngine


def test_templates_registry():
    templates = get_available_templates()
    assert "nextjs" in templates
    assert "vite_spa" in templates
    assert "node_backend" in templates
    assert "fastapi" in templates
    assert "django" in templates
    assert "laravel" in templates
    assert "golang" in templates
    assert "static_html" in templates


def test_generate_dockerfile_custom_port():
    df = generate_dockerfile("nextjs", port=3005)
    assert "EXPOSE 3005" in df
    assert "PORT=3005" in df
    assert "USER nextjs" in df


def test_detect_nextjs_project(tmp_path):
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text('{"name": "test-app", "dependencies": {"next": "^14.0.0", "react": "^18.0.0"}}')

    stack = detect_project_stack(str(tmp_path))
    assert stack["framework"] == "Next.js"
    assert stack["template_key"] == "nextjs"
    assert stack["recommended_port"] == 3000


def test_detect_vite_project(tmp_path):
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text('{"name": "vite-spa", "devDependencies": {"vite": "^5.0.0"}}')

    stack = detect_project_stack(str(tmp_path))
    assert stack["framework"] == "React / Vite / Vue"
    assert stack["template_key"] == "vite_spa"
    assert stack["recommended_port"] == 80


def test_detect_fastapi_project(tmp_path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("fastapi>=0.100.0\nuvicorn\npydantic\n")

    stack = detect_project_stack(str(tmp_path))
    assert stack["framework"] == "FastAPI"
    assert stack["template_key"] == "fastapi"
    assert stack["recommended_port"] == 8000


def test_detect_laravel_project(tmp_path):
    artisan = tmp_path / "artisan"
    artisan.write_text("#!/usr/bin/env php\n")

    stack = detect_project_stack(str(tmp_path))
    assert stack["framework"] == "Laravel"
    assert stack["template_key"] == "laravel"
    assert stack["recommended_port"] == 8080


def test_detect_golang_project(tmp_path):
    go_mod = tmp_path / "go.mod"
    go_mod.write_text("module example.com/myservice\n\ngo 1.22\n")

    stack = detect_project_stack(str(tmp_path))
    assert stack["framework"] == "Go"
    assert stack["template_key"] == "golang"


def test_ensure_dockerfile_and_ignore(tmp_path):
    # Empty directory with index.html
    html_file = tmp_path / "index.html"
    html_file.write_text("<h1>Hello Homelab</h1>")

    logs = []
    df_path, df_created, di_created = ensure_dockerfile_and_ignore(
        workspace_dir=str(tmp_path),
        dockerfile_path="Dockerfile",
        container_port=80,
        log_callback=lambda lvl, msg: logs.append((lvl, msg)),
    )

    assert df_created is True
    assert di_created is True
    assert (tmp_path / "Dockerfile").exists()
    assert (tmp_path / ".dockerignore").exists()

    df_content = (tmp_path / "Dockerfile").read_text()
    assert "nginx:alpine" in df_content

    di_content = (tmp_path / ".dockerignore").read_text()
    assert "node_modules" in di_content
    assert ".git" in di_content


def test_builder_integration_ensure_dockerfile(tmp_path):
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text('{"name": "my-express-app", "scripts": {"start": "node index.js"}}')

    logs = []
    resolved = DeploymentEngine.ensure_dockerfile_or_generate(
        workspace_dir=str(tmp_path),
        dockerfile_path="Dockerfile",
        compose_path="docker-compose.yml",
        container_port=3000,
        log_callback=lambda lvl, msg: logs.append((lvl, msg)),
    )

    assert resolved == "Dockerfile"
    assert (tmp_path / "Dockerfile").exists()
    assert (tmp_path / ".dockerignore").exists()
    content = (tmp_path / "Dockerfile").read_text()
    assert "FROM node:20-alpine" in content
    assert "USER node" in content

