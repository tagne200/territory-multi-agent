"""Export JSON du rapport et du schéma JSON correspondant."""

from __future__ import annotations

import json
from pathlib import Path

from territory_assistant.models import AnalysisReport


def write_json(report: AnalysisReport, path: Path) -> Path:
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_report(path: Path) -> AnalysisReport:
    """Relit et revalide un rapport (utile aux tests de conformité au schéma)."""
    return AnalysisReport.model_validate_json(Path(path).read_text(encoding="utf-8"))


def write_json_schema(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(AnalysisReport.model_json_schema(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
