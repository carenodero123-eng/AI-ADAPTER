"""Stage M deployment contract checks for Docker and the end-to-end demo."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
COMPOSE = (ROOT / "compose.yaml").read_text(encoding="utf-8")
ENTRYPOINT = (ROOT / "scripts" / "docker-entrypoint.sh").read_text(encoding="utf-8")
DOCKERIGNORE = (ROOT / ".dockerignore").read_text(encoding="utf-8")
ENV_EXAMPLE = (ROOT / ".env.docker.example").read_text(encoding="utf-8")
GITIGNORE = (ROOT / ".gitignore").read_text(encoding="utf-8")
DEMO = (ROOT / "scripts" / "demo.ps1").read_text(encoding="utf-8")
VERIFIER = (ROOT / "scripts" / "e2e_demo.py").read_text(encoding="utf-8")


def _service(name: str) -> str:
    marker = f"  {name}:\n"
    start = COMPOSE.index(marker)
    tail = COMPOSE[start + len(marker) :]
    match = re.search(r"(?m)^  [a-z][a-z0-9_-]*:\n|^volumes:\n|^networks:\n", tail)
    return tail[: match.start()] if match else tail


def test_dockerfile_defines_builder_runtime_and_both_targets() -> None:
    assert DOCKERFILE.startswith("# syntax=docker/dockerfile:1.7")
    assert "FROM python:3.14-slim AS builder" in DOCKERFILE
    assert "FROM python:3.14-slim AS runtime" in DOCKERFILE
    assert "FROM runtime AS api" in DOCKERFILE
    assert "FROM runtime AS dashboard" in DOCKERFILE
    assert "target: api" in COMPOSE
    assert "target: dashboard" in COMPOSE


def test_images_run_as_non_root_and_do_not_write_bytecode() -> None:
    user_lines = [
        line.strip() for line in DOCKERFILE.splitlines() if line.strip().startswith("USER ")
    ]
    assert user_lines
    assert user_lines[-1] == "USER 10001:10001"
    assert "PYTHONDONTWRITEBYTECODE=1" in DOCKERFILE
    assert "useradd --system" in DOCKERFILE
    assert "--uid 10001" in DOCKERFILE


def test_images_declare_api_and_dashboard_healthchecks() -> None:
    assert DOCKERFILE.count("HEALTHCHECK") == 2
    assert "http://127.0.0.1:8000/health/ready" in DOCKERFILE
    assert "http://127.0.0.1:8501/_stcore/health" in DOCKERFILE


def test_dockerfile_copies_runtime_assets_without_env_files() -> None:
    for path in (
        "alembic.ini",
        "./alembic",
        "./app",
        "./dashboard",
        "./config",
        "./.streamlit",
    ):
        assert path in DOCKERFILE
    assert "COPY .env" not in DOCKERFILE
    assert "OPENAI_API_KEY" not in DOCKERFILE
    assert "SECURITY_API_KEYS" not in DOCKERFILE


def test_entrypoint_runs_migrations_then_execs_the_container_command() -> None:
    assert ENTRYPOINT.startswith("#!/bin/sh\n")
    assert "set -eu" in ENTRYPOINT
    assert 'RUN_MIGRATIONS:-true' in ENTRYPOINT
    assert "alembic upgrade head" in ENTRYPOINT
    assert "sleep 2" in ENTRYPOINT
    assert 'exec "$@"' in ENTRYPOINT
    assert "\r\n" not in ENTRYPOINT
    assert "chmod 0555 /usr/local/bin/docker-entrypoint.sh" in DOCKERFILE


def test_compose_defines_the_three_services_and_dependencies() -> None:
    for name in ("db", "api", "dashboard"):
        assert f"  {name}:\n" in COMPOSE
    api = _service("api")
    dashboard = _service("dashboard")
    assert "condition: service_healthy" in api
    assert "condition: service_healthy" in dashboard
    for name in ("db", "api", "dashboard"):
        assert "healthcheck:" in _service(name)


def test_compose_publishes_only_loopback_ports() -> None:
    assert '"127.0.0.1:8000:8000"' in _service("api")
    assert '"127.0.0.1:8501:8501"' in _service("dashboard")
    assert "ports:" not in _service("db")
    assert "0.0.0.0" not in COMPOSE


def test_compose_uses_production_database_and_security_guards() -> None:
    api = _service("api")
    assert "ENVIRONMENT: production" in api
    assert "postgresql+asyncpg://" in api
    assert 'DATABASE_ENABLED: "true"' in api
    assert 'DATABASE_AUTO_CREATE: "false"' in api
    assert 'DATABASE_ECHO: "false"' in api
    assert 'SECURITY_REQUIRE_AUTH: "true"' in api
    assert "MODEL_VERSION_MANIFEST: config/model_versions.json" in api


def test_compose_requires_secrets_and_maps_the_admin_key() -> None:
    assert "${POSTGRES_PASSWORD:?" in COMPOSE
    assert "${SECURITY_API_KEYS:?" in COMPOSE
    assert "${SECURITY_ADMIN_API_KEYS:?" in COMPOSE
    dashboard = _service("dashboard")
    assert "DASHBOARD_ADMIN_API_KEY:" in dashboard
    assert "${SECURITY_ADMIN_API_KEYS:?" in dashboard
    assert "DASHBOARD_API_BASE_URL: http://api:8000" in dashboard
    for literal in ("sk-", "admin-key-0123", "user-key-0123"):
        assert literal not in COMPOSE


def test_compose_hardens_application_containers_and_internalizes_the_database() -> None:
    assert _service("api").count("read_only: true") == 1
    assert _service("dashboard").count("read_only: true") == 1
    assert COMPOSE.count("cap_drop:") == 2
    assert COMPOSE.count("no-new-privileges:true") == 3
    assert "internal: true" in COMPOSE
    assert "privileged: true" not in COMPOSE
    assert "init: true" in _service("api")
    assert "init: true" in _service("dashboard")


def test_compose_persists_postgres_in_a_named_volume_without_exposing_it() -> None:
    assert "db_data:" in COMPOSE
    assert "db_data:/var/lib/postgresql/data" in _service("db")
    assert "ports:" not in _service("db")


def test_dockerignore_excludes_secrets_state_and_development_trees() -> None:
    ignored = DOCKERIGNORE.splitlines()
    for entry in (
        ".env",
        ".env.*",
        ".venv",
        "data",
        "docs",
        "tests",
        "scripts/*",
        "!scripts/docker-entrypoint.sh",
        ".git",
    ):
        assert entry in ignored
    for kept in ("app", "dashboard", "config", "alembic"):
        assert kept not in ignored


def test_env_docker_example_documents_required_values_without_secrets() -> None:
    for name in (
        "POSTGRES_PASSWORD",
        "SECURITY_API_KEYS",
        "SECURITY_ADMIN_API_KEYS",
    ):
        assert f"{name}=" in ENV_EXAMPLE
    assert "replace-with" in ENV_EXAMPLE
    assert not re.search(r"(?m)=[0-9a-f]{32,}$", ENV_EXAMPLE)
    assert ".env.docker" in GITIGNORE
    assert "!.env.docker.example" in GITIGNORE


def test_demo_script_generates_random_secrets_and_tears_down() -> None:
    assert "RandomNumberGenerator" in DEMO
    assert "New-RandomHex" in DEMO
    assert ".env.docker" in DEMO
    assert "-Encoding ascii" in DEMO
    assert "docker compose version" in DEMO
    assert '"up", "-d"' in DEMO
    assert "--build" in DEMO
    assert "e2e_demo.py" in DEMO
    assert '"down"' in DEMO
    assert '"-v"' in DEMO
    assert "KeepRunning" in DEMO
    assert "E2E_USER_KEY" in DEMO
    assert "E2E_ADMIN_KEY" in DEMO
    assert "must differ" in DEMO
    assert "without whitespace or commas" in DEMO
    assert "URL-safe" in DEMO
    assert "Write-Host $userKey" not in DEMO
    assert "Write-Host $adminKey" not in DEMO
    assert "Write-Host $dbPassword" not in DEMO


def test_verifier_covers_the_deployed_surface_without_printing_secrets() -> None:
    for path in (
        "/health/live",
        "/health/ready",
        "/api/v1/generate",
        "/api/v1/fault-reports/summarize",
        "/api/v1/monitoring/summary",
        "/api/v1/monitoring/metrics",
        "/api/v1/requests",
        "/api/v1/model-versions",
        "/_stcore/health",
    ):
        assert path in VERIFIER
    assert 'os.environ.get(name, "")' in VERIFIER
    assert "E2E_USER_KEY" in VERIFIER
    assert "E2E_ADMIN_KEY" in VERIFIER
    assert "trust_env=False" in VERIFIER
    assert "follow_redirects=False" in VERIFIER
    assert "leaked request content" in VERIFIER
    assert "stage-m e2e: PASS" in VERIFIER
    assert "stage-m e2e: FAIL" in VERIFIER
    assert "print(user_key" not in VERIFIER
    assert "print(admin_key" not in VERIFIER
    assert "print(args" not in VERIFIER


def test_compose_file_is_valid_when_the_docker_cli_is_installed() -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI is not installed on this host")

    version = subprocess.run(
        [docker, "compose", "version"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if version.returncode != 0:
        pytest.skip("Docker Compose v2 is not available on this host")

    result = subprocess.run(
        [
            docker,
            "compose",
            "--project-directory",
            str(ROOT),
            "--env-file",
            ".env.docker.example",
            "config",
            "--quiet",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
