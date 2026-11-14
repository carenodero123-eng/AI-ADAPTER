"""Provider-independent fault-report summarization."""

from app.faults.extraction import extract_fault_summary
from app.faults.factory import build_fault_report_service
from app.faults.models import (
    SUMMARY_FIELDS,
    FaultSeverity,
    FaultSummary,
    TemperatureUnit,
    is_empty_summary,
    summarize_fields,
)
from app.faults.parsing import FaultSummaryParseError, parse_fault_summary
from app.faults.service import FaultReportService, FaultSummaryResult

__all__ = [
    "FaultReportService",
    "FaultSeverity",
    "FaultSummary",
    "FaultSummaryParseError",
    "FaultSummaryResult",
    "SUMMARY_FIELDS",
    "TemperatureUnit",
    "build_fault_report_service",
    "extract_fault_summary",
    "is_empty_summary",
    "parse_fault_summary",
    "summarize_fields",
]
