"""End-to-end verification for a running AI Adapter deployment.

This script is used by the Stage M demonstration. It never prints API keys or
prompt text; it validates observable behavior through the deployed HTTP
surface and exits nonzero on the first failed contract.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
import time
from typing import Any

import httpx


class DemoFailure(RuntimeError):
    """A required end-to-end check failed."""


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a running AI Adapter deployment.")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--dashboard-url", default="http://127.0.0.1:8501")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--wait-timeout", type=float, default=120.0)
    parser.add_argument("--min-requests", type=int, default=4)
    return parser.parse_args(argv)


def _required_key(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise DemoFailure(f"{name} is required")
    return value


def _json(response: httpx.Response, label: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        raise DemoFailure(f"{label} returned invalid JSON") from None
    if not isinstance(payload, dict):
        raise DemoFailure(f"{label} returned an unexpected JSON shape")
    return payload


def _request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    label: str,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    expected: int = 200,
) -> httpx.Response:
    response = client.request(method, url, headers=headers, json=body)
    if response.status_code != expected:
        raise DemoFailure(f"{label} returned HTTP {response.status_code}")
    return response


def _wait_for_api(client: httpx.Client, base_url: str, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = "not contacted"
    while time.monotonic() < deadline:
        try:
            response = client.get(f"{base_url}/health/ready")
        except httpx.HTTPError as error:
            last_error = type(error).__name__
        else:
            if response.status_code == 200:
                payload = _json(response, "readiness")
                if payload.get("status") == "ready":
                    return payload
            last_error = f"HTTP {response.status_code}"
        time.sleep(1.0)
    raise DemoFailure(f"API did not become ready ({last_error})")


def _wait_for_dashboard(client: httpx.Client, url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error = "not contacted"
    while time.monotonic() < deadline:
        try:
            root = client.get(url)
            health = client.get(f"{url}/_stcore/health")
        except httpx.HTTPError as error:
            last_error = type(error).__name__
        else:
            if (
                root.status_code == 200
                and health.status_code == 200
                and health.text.strip() == "ok"
            ):
                return
            last_error = f"HTTP {root.status_code}/{health.status_code}"
        time.sleep(1.0)
    raise DemoFailure(f"dashboard did not become ready ({last_error})")


def _wait_for_summary(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    minimum: int,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = "not contacted"
    while time.monotonic() < deadline:
        try:
            response = client.get(url, headers=headers, params={"window": "1h"})
        except httpx.HTTPError as error:
            last_error = type(error).__name__
        else:
            if response.status_code == 200:
                payload = _json(response, "monitoring summary")
                totals = payload.get("totals")
                if isinstance(totals, dict) and isinstance(totals.get("requests"), int):
                    if totals["requests"] >= minimum:
                        return payload
                    last_error = f"requests={totals['requests']}"
                else:
                    last_error = "missing totals"
            else:
                last_error = f"HTTP {response.status_code}"
        time.sleep(1.0)
    raise DemoFailure(
        f"monitoring summary did not reach {minimum} requests ({last_error})"
    )


def _bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _run_checks(args: argparse.Namespace) -> None:
    base_url = args.api_base_url.rstrip("/")
    dashboard_url = args.dashboard_url.rstrip("/")
    user_headers = _bearer(_required_key("E2E_USER_KEY"))
    admin_headers = _bearer(_required_key("E2E_ADMIN_KEY"))
    marker = f"stage-m-e2e-{secrets.token_hex(6)}"

    client = httpx.Client(
        timeout=args.timeout,
        trust_env=False,
        follow_redirects=False,
    )
    try:
        readiness = _wait_for_api(client, base_url, args.wait_timeout)
        checks = readiness.get("checks")
        if not isinstance(checks, dict) or checks.get("database") != "ok":
            raise DemoFailure("readiness did not report database ok")
        print(f"readiness: {readiness.get('status')} database=ok")

        _request(
            client,
            "GET",
            f"{base_url}/health/live",
            label="liveness",
        )

        first = _json(
            _request(
                client,
                "POST",
                f"{base_url}/api/v1/generate",
                label="generation 1",
                headers=user_headers,
                body={"messages": [{"role": "user", "content": f"{marker} first"}]},
            ),
            "generation 1",
        )
        if first.get("provider") != "fake" or not first.get("content"):
            raise DemoFailure("generation 1 did not return fake-provider content")

        second = _json(
            _request(
                client,
                "POST",
                f"{base_url}/api/v1/generate",
                label="generation 2",
                headers=user_headers,
                body={
                    "model": "fake-large",
                    "max_tokens": 32,
                    "messages": [{"role": "user", "content": f"{marker} second"}],
                },
            ),
            "generation 2",
        )
        if second.get("model") != "fake-large":
            raise DemoFailure("generation 2 did not honor the requested model")

        fault = _json(
            _request(
                client,
                "POST",
                f"{base_url}/api/v1/fault-reports/summarize",
                label="fault report",
                headers=user_headers,
                body={
                    "report": (
                        f"{marker}: Pump 7 bearing overheated to 95 C; "
                        "line stopped for 20 minutes."
                    )
                },
            ),
            "fault report",
        )
        extraction = fault.get("extraction")
        if extraction not in {"provider", "deterministic"}:
            raise DemoFailure("fault report returned an unknown extraction mode")
        if not isinstance(fault.get("summary"), dict):
            raise DemoFailure("fault report did not return a summary")

        unknown = _request(
            client,
            "POST",
            f"{base_url}/api/v1/generate",
            label="unknown provider",
            headers=user_headers,
            body={
                "provider": "ghost",
                "messages": [{"role": "user", "content": f"{marker} unknown"}],
            },
            expected=404,
        )
        unknown_error = _json(unknown, "unknown provider").get("error")
        if not isinstance(unknown_error, dict):
            raise DemoFailure("unknown provider did not return an error envelope")
        if unknown_error.get("code") != "provider_not_found":
            raise DemoFailure("unknown provider returned the wrong error code")

        unauthorized = _request(
            client,
            "GET",
            f"{base_url}/api/v1/requests",
            label="unauthorized history",
            expected=401,
        )
        unauthorized_error = _json(unauthorized, "unauthorized history").get("error")
        if not isinstance(unauthorized_error, dict):
            raise DemoFailure("unauthorized history did not return an error envelope")
        if unauthorized_error.get("code") != "authentication_required":
            raise DemoFailure("unauthorized history returned the wrong error code")

        summary = _wait_for_summary(
            client,
            f"{base_url}/api/v1/monitoring/summary",
            admin_headers,
            args.min_requests,
            args.wait_timeout,
        )
        totals = summary.get("totals")
        if not isinstance(totals, dict):
            raise DemoFailure("monitoring summary has no totals")
        if not isinstance(totals.get("accepted"), int) or totals["accepted"] < 3:
            raise DemoFailure("monitoring summary has too few accepted results")
        if not isinstance(totals.get("errors"), int) or totals["errors"] < 1:
            raise DemoFailure("monitoring summary did not record the error")
        if not isinstance(totals.get("total_tokens"), int) or totals["total_tokens"] < 1:
            raise DemoFailure("monitoring summary has no token usage")
        kinds = summary.get("by_kind")
        if not isinstance(kinds, list):
            raise DemoFailure("monitoring summary has no kind breakdown")
        kind_names = {
            item.get("kind") for item in kinds if isinstance(item, dict)
        }
        if not {"generation", "fault_report"} <= kind_names:
            raise DemoFailure("monitoring summary is missing a request kind")
        print(
            "summary: "
            f"requests={totals['requests']} accepted={totals['accepted']} "
            f"errors={totals['errors']} total_tokens={totals['total_tokens']}"
        )

        metrics = _request(
            client,
            "GET",
            f"{base_url}/api/v1/monitoring/metrics",
            label="prometheus metrics",
            headers=admin_headers,
        )
        if "ai_adapter_requests_total" not in metrics.text:
            raise DemoFailure("prometheus metrics are missing request counters")
        if marker in metrics.text:
            raise DemoFailure("prometheus metrics leaked request content")
        if not metrics.headers.get("content-type", "").startswith("text/plain"):
            raise DemoFailure("prometheus metrics returned the wrong content type")
        print(f"metrics: {len(metrics.text)} bytes content-type=text/plain")

        history_response = _request(
            client,
            "GET",
            f"{base_url}/api/v1/requests",
            label="request history",
            headers=admin_headers,
        )
        if marker in history_response.text:
            raise DemoFailure("request history leaked request content")
        history = _json(history_response, "request history")
        total = history.get("total")
        if not isinstance(total, int) or total < args.min_requests:
            raise DemoFailure("request history is missing expected records")
        print(f"history: total={total}")

        models = _json(
            _request(
                client,
                "GET",
                f"{base_url}/api/v1/model-versions",
                label="model versions",
                headers=admin_headers,
            ),
            "model versions",
        )
        entries = models.get("models")
        if not isinstance(entries, list) or not entries:
            raise DemoFailure("model version inventory is empty")
        active = sum(
            1
            for item in entries
            if isinstance(item, dict) and item.get("status") == "active"
        )
        if active < 1:
            raise DemoFailure("model version inventory has no active entries")
        print(f"model_versions: entries={len(entries)} active={active}")

        _wait_for_dashboard(client, dashboard_url, args.wait_timeout)
        print("dashboard: 200 health=ok")
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        _run_checks(args)
    except DemoFailure as error:
        print(f"stage-m e2e: FAIL ({error})", file=sys.stderr)
        return 1
    except httpx.HTTPError as error:
        print(f"stage-m e2e: FAIL ({type(error).__name__})", file=sys.stderr)
        return 1
    print("stage-m e2e: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
