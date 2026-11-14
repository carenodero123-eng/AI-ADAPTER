"""Provider-independent prompt construction for fault summarization."""

from __future__ import annotations

from app.providers.schemas import ChatMessage

SYSTEM_PROMPT = """You extract industrial maintenance fault data.
Return exactly one JSON object and nothing else.
The object must contain exactly these keys:
- machine: equipment name or identifier, or null
- fault_description: concise description of the fault, or null
- temperature: a JSON number, or null
- temperature_unit: "C", "F", or null
- downtime: a short duration string such as "2 hours", or null
- action_taken: the maintenance action performed, or null
- severity: one of "low", "medium", "high", "critical", or null

Rules:
- Use only information explicitly present in the report.
- Never guess, infer, or fabricate a value that is not stated.
- Use null for every unknown value.
- Do not include markdown, comments, or explanatory text.
"""


def build_fault_messages(report: str) -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=f"Fault report:\n{report}"),
    ]
