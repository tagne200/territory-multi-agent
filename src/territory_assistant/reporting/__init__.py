"""Exports : rapport JSON, rapport Markdown, carte PNG et constats GeoJSON."""

from __future__ import annotations

from pathlib import Path

from territory_assistant.pipeline import PipelineOutput
from territory_assistant.reporting.json_report import write_json
from territory_assistant.reporting.map_export import export_findings_geojson, export_map
from territory_assistant.reporting.markdown_report import render_markdown


def write_outputs(output: PipelineOutput, out_dir: Path) -> dict[str, Path]:
    """Écrit tous les livrables dans `out_dir/<analysis_id>/` et retourne leurs chemins."""
    folder = Path(out_dir) / output.report.analysis_id
    folder.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    if output.report.study_area is not None and "area_geom" in output.ctx.artifacts:
        paths["map"] = export_map(output, folder / "map.png")
        paths["findings"] = export_findings_geojson(output, folder / "findings.geojson")
    paths["json"] = write_json(output.report, folder / "report.json")
    md = render_markdown(output.report, map_filename="map.png" if "map" in paths else None)
    paths["markdown"] = folder / "report.md"
    paths["markdown"].write_text(md, encoding="utf-8")
    return paths


__all__ = [
    "write_outputs",
    "write_json",
    "render_markdown",
    "export_map",
    "export_findings_geojson",
]
