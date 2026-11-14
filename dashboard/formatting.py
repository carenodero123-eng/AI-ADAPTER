"""Presentation-only formatting helpers."""

from __future__ import annotations

from datetime import UTC, datetime

_UTC = UTC


def format_percent(value: float) -> str:
    return f"{max(value, 0.0) * 100:.1f}%"


def format_usd(value: float) -> str:
    value = max(value, 0.0)
    if value >= 0.01:
        return f"${value:,.2f}"
    return f"${value:.6f}"


def format_ms(value: float | None) -> str:
    if value is None or value < 0:
        return "n/a"
    if value >= 1000.0:
        return f"{value / 1000.0:,.2f} s"
    return f"{value:,.2f} ms"


def format_count(value: int) -> str:
    return f"{max(value, 0):,}"


def format_utc(value: datetime | None) -> str:
    if value is None:
        return "n/a"
    if value.tzinfo is None:
        value = value.replace(tzinfo=_UTC)
    return value.astimezone(_UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
