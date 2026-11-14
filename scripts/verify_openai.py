"""Make one live OpenAI request through the adapter and print safe results.

This script reads the same environment/.env configuration as the service. It
never prints the API key or upstream payloads. Run it only when a real key is
configured and a billable request is acceptable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.core.config import Settings
from app.providers.errors import ProviderError
from app.providers.openai import OpenAIProvider
from app.providers.schemas import ChatMessage, GenerationRequest, ProviderHealth


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1 or value > 8192:
        raise argparse.ArgumentTypeError("must be between 1 and 8192")
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the configured OpenAI provider with one live request."
    )
    parser.add_argument("--model", default=None, help="Configured model to use")
    parser.add_argument(
        "--prompt",
        default="Reply with exactly: adapter verification ok",
        help="User prompt for the verification request",
    )
    parser.add_argument("--max-tokens", type=_positive_int, default=64)
    return parser.parse_args()


def _print_health(health: ProviderHealth) -> None:
    print(
        json.dumps(
            {
                "health": {
                    "provider": health.provider,
                    "status": health.status,
                    "latency_ms": health.latency_ms,
                    "detail": health.detail,
                }
            },
            indent=2,
        )
    )


async def _run(args: argparse.Namespace) -> int:
    settings = Settings()
    if not settings.openai_enabled or settings.openai_api_key is None:
        print(
            "OPENAI_API_KEY is not configured. Set it in the environment or .env.",
            file=sys.stderr,
        )
        return 2

    model = args.model or settings.openai_default_model
    provider = OpenAIProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
        models=settings.openai_model_list,
        default_model=settings.openai_default_model,
        timeout_seconds=settings.openai_timeout_seconds,
    )

    try:
        _print_health(await provider.healthcheck())
        result = await provider.generate(
            GenerationRequest(
                model=model,
                messages=[ChatMessage(role="user", content=args.prompt)],
                max_tokens=args.max_tokens,
            )
        )
        print(json.dumps({"result": result.model_dump()}, indent=2))
        return 0
    except ProviderError as error:
        print(
            json.dumps(
                {
                    "error": {
                        "code": error.code,
                        "message": error.message,
                        "provider": error.provider,
                        "retryable": error.retryable,
                    }
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        await provider.aclose()


def main() -> int:
    return asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
