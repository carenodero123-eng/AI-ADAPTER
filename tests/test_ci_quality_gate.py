"""Stage J CI quality-gate contract tests."""

from __future__ import annotations

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
QUALITY_SCRIPT = PROJECT_ROOT / "scripts" / "quality.ps1"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_runs_for_pull_requests_and_manual_dispatch() -> None:
    text = _workflow_text()
    assert "pull_request:" in text
    assert "workflow_dispatch:" in text
    assert "actions/checkout@v4" in text
    assert "actions/setup-python@v5" in text
    assert 'PYTHON_VERSION: "3.14"' in text


def test_workflow_uses_read_only_permissions_and_a_bounded_job() -> None:
    text = _workflow_text()
    assert "permissions:\n  contents: read" in text
    assert "timeout-minutes: 15" in text


def test_workflow_runs_every_required_quality_gate() -> None:
    text = _workflow_text()
    required_commands = (
        'python -m pip install -e ".[dev]"',
        "python -m compileall -q app dashboard tests alembic",
        "python -m ruff check .",
        "python -m pytest -q --strict-config --strict-markers",
        "python -m pytest -q -m fault_matrix tests/test_fault_matrix.py",
        "python -m pytest -q -m regression tests/test_model_versions.py tests/test_regression.py",
        "git diff --exit-code -- tests/regression/baselines",
    )
    for command in required_commands:
        assert command in text


def test_workflow_cannot_update_baselines_or_reference_secrets() -> None:
    text = _workflow_text()
    assert 'UPDATE_REGRESSION_BASELINES: "0"' in text
    assert 'UPDATE_REGRESSION_BASELINES: "1"' not in text
    assert "secrets." not in text


def test_workflow_does_not_export_application_settings_globally() -> None:
    text = _workflow_text()
    test_sensitive_settings = (
        "ENVIRONMENT:",
        "MODEL_VERSION_MANIFEST:",
        "DATABASE_ENABLED:",
        "BUDGET_ENFORCEMENT_ENABLED:",
        "SECURITY_REQUIRE_AUTH:",
        "SECURITY_RATE_LIMIT_REQUESTS:",
    )
    for setting in test_sensitive_settings:
        assert setting not in text


def test_local_quality_runner_mirrors_ci_checks() -> None:
    script = QUALITY_SCRIPT.read_text(encoding="utf-8")
    required_commands = (
        "-m compileall -q app dashboard tests alembic",
        "-m ruff check .",
        "-m pytest -q --strict-config --strict-markers",
        "-m pytest -q -m fault_matrix tests/test_fault_matrix.py",
        "-m pytest -q -m regression tests/test_model_versions.py tests/test_regression.py",
    )
    for command in required_commands:
        assert command in script
    assert "$env:UPDATE_REGRESSION_BASELINES = \"0\"" in script
    for setting in (
        "ENVIRONMENT",
        "MODEL_VERSION_MANIFEST",
        "DATABASE_ENABLED",
        "BUDGET_ENFORCEMENT_ENABLED",
        "SECURITY_REQUIRE_AUTH",
        "SECURITY_RATE_LIMIT_REQUESTS",
    ):
        assert f"$env:{setting}" not in script
    assert "exit $LASTEXITCODE" in script


def test_ruff_is_declared_and_configured_for_the_project() -> None:
    configuration = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    dev_dependencies = configuration["project"]["optional-dependencies"]["dev"]
    assert any(requirement.startswith("ruff") for requirement in dev_dependencies)

    ruff = configuration["tool"]["ruff"]
    assert ruff["target-version"] == "py314"
    assert {"E4", "F", "I", "B", "UP", "ASYNC"}.issubset(
        set(ruff["lint"]["select"])
    )
