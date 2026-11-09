"""Interface Streamlit de démonstration.

Lancement (depuis la racine du dépôt) :
    streamlit run src/territory_assistant/ui/streamlit_app.py

Ordre d'affichage volontaire : avertissements et données manquantes AVANT la synthèse
et les recommandations générées.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

from territory_assistant import DISCLAIMER
from territory_assistant.cli import DEMO_QUESTION
from territory_assistant.config import DOCUMENT_EXTENSIONS, LAYER_EXTENSIONS, Settings
from territory_assistant.models import AnalysisRequest
from territory_assistant.pipeline import run_analysis
from territory_assistant.reporting import write_outputs
from territory_assistant.safety import sanitize_filename

BANNER = "Prototype d'aide à l'analyse — résultats à vérifier par un spécialiste."
ROOT = (
    Path.cwd() if (Path.cwd() / "data" / "sample").is_dir() else Path(__file__).resolve().parents[3]
)
SAMPLE = ROOT / "data" / "sample"
UPLOADS = ROOT / "reports" / "uploads"
SEV_ICON = {"critical": "🔴", "warning": "🟠", "info": "🔵"}


def _list(folder: Path, exts: set[str]) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(
        p
        for p in folder.iterdir()
        if p.suffix.lower() in exts and not p.name.endswith(".meta.json")
    )


def _save_uploads(files, session_dir: Path) -> list[Path]:
    """Enregistre les fichiers téléversés sous un nom assaini (les .meta.json sont conservés
    à côté pour fournir provenance, date et licence)."""
    saved = []
    session_dir.mkdir(parents=True, exist_ok=True)
    for f in files or []:
        target = session_dir / sanitize_filename(f.name)
        target.write_bytes(f.getbuffer())
        if not target.name.endswith(".meta.json"):
            saved.append(target)
    return saved


st.set_page_config(page_title="Contraintes territoriales — prototype", layout="wide")
st.title("Assistant multi-agents — analyse préliminaire des contraintes territoriales")
st.warning(f"**{BANNER}**")

if "session_dir" not in st.session_state:
    st.session_state.session_dir = UPLOADS / uuid.uuid4().hex[:12]
session_dir: Path = st.session_state.session_dir

with st.sidebar:
    st.header("1. Zone d'étude")
    zone_choice = st.radio(
        "Source de la zone",
        ["Zone d'exemple (fictive)", "Zone fictive hors données", "Téléverser"],
        key="zone_choice",
    )
    area_path: Path | None = None
    if zone_choice == "Zone d'exemple (fictive)":
        area_path = SAMPLE / "study_area.geojson"
    elif zone_choice == "Zone fictive hors données":
        area_path = SAMPLE / "alt_areas" / "zone_hors_donnees.geojson"
    else:
        up = st.file_uploader(
            "Zone (GeoJSON / GeoPackage, + .meta.json facultatif)",
            type=["geojson", "json", "gpkg"],
            accept_multiple_files=True,
            key="area_upload",
        )
        saved = _save_uploads(up, session_dir / "zone")
        area_path = saved[0] if saved else None

    st.header("2. Couches")
    sample_layers = _list(SAMPLE / "layers", LAYER_EXTENSIONS)
    chosen_layers = st.multiselect(
        "Couches locales",
        sample_layers,
        default=sample_layers,
        format_func=lambda p: p.name,
        key="layers",
    )
    extra_layers = _save_uploads(
        st.file_uploader(
            "Couches supplémentaires (+ .meta.json)",
            type=["geojson", "json", "gpkg"],
            accept_multiple_files=True,
            key="layer_upload",
        ),
        session_dir / "layers",
    )

    st.header("3. Documents")
    sample_docs = _list(SAMPLE / "documents", DOCUMENT_EXTENSIONS)
    chosen_docs = st.multiselect(
        "Documents locaux",
        sample_docs,
        default=sample_docs,
        format_func=lambda p: p.name,
        key="docs",
    )
    extra_docs = _save_uploads(
        st.file_uploader(
            "Documents supplémentaires (.md, .txt, .pdf)",
            type=["md", "txt", "pdf", "json"],
            accept_multiple_files=True,
            key="doc_upload",
        ),
        session_dir / "docs",
    )

    st.header("4. Question")
    question = st.text_area("Question", value=DEMO_QUESTION, key="question")
    project_type = st.text_input("Type de projet", value="aménagement (étude préliminaire)")
    buffer_m = st.number_input("Tampon de proximité (m)", 0.0, 5000.0, 200.0, 50.0)
    base_settings = Settings.from_env()
    use_llm = st.toggle(
        "Activer le LLM (Anthropic, clé locale requise)",
        value=False,
        help="Sans clé, l'analyse reste entièrement déterministe. Les chiffres ne passent jamais par le LLM.",
    )
    run = st.button("Lancer l'analyse", type="primary", key="run")

if run:
    if not question.strip():
        st.error("La question est vide.")
    else:
        settings = base_settings.model_copy(
            update={"buffer_m": buffer_m, "llm_provider": "anthropic" if use_llm else "none"}
        )
        req = AnalysisRequest(
            question=question,
            project_type=project_type or None,
            study_area_path=area_path,
            layer_paths=list(chosen_layers) + extra_layers,
            document_paths=list(chosen_docs) + extra_docs,
            allowed_roots=[ROOT],
        )
        with st.spinner("Analyse en cours…"):
            output = run_analysis(req, settings)
            paths = write_outputs(output, ROOT / "reports")
        st.session_state.result = (output.report, paths)

if "result" not in st.session_state:
    st.info("Choisissez une zone, des couches et des documents, puis lancez l'analyse.")
    st.stop()

report, paths = st.session_state.result
c1, c2, c3, c4 = st.columns(4)
c1.metric("Statut", report.status)
c2.metric("Constats SIG", len(report.spatial_findings))
c3.metric("Extraits documentaires", len(report.document_evidence))
c4.metric("Données manquantes", len(report.missing_information))
st.caption(f"Analyse `{report.analysis_id}` — mode : {report.mode}")

# ---------------------------------------------------------------- 1. avertissements d'abord
st.subheader("⚠️ Données manquantes et avertissements")
for m in report.missing_information:
    st.markdown(f"- **{m.statement_id}** — {m.text}")
order = {"critical": 0, "warning": 1, "info": 2}
for u in sorted(report.uncertainties, key=lambda u: order[u.severity]):
    st.markdown(f"- {SEV_ICON[u.severity]} `[{u.category}]` {u.description}")

# ---------------------------------------------------------------- 2. carte et constats
st.subheader("Carte et constats calculés")
if "map" in paths:
    st.image(str(paths["map"]))
if report.spatial_findings:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "constat": f.finding_id,
                    "couche": f.layer_name,
                    "entité": f.feature_id,
                    "libellé": f.feature_label,
                    "relation": f.relation,
                    "mesures": "; ".join(f"{m.name}={m.value:g} {m.unit}" for m in f.metrics),
                    "CRS": f.crs_transformation,
                    "source": f.source_id,
                }
                for f in report.spatial_findings
            ]
        ),
        hide_index=True,
        width="stretch",
    )

# ---------------------------------------------------------------- 3. documents
st.subheader("Extraits documentaires")
if not report.document_evidence:
    st.write(report.document_search_note or "Aucun extrait.")
for e in report.document_evidence:
    loc = e.section or (f"page {e.page}" if e.page else "passage")
    if e.suspicious_instructions:
        st.error(
            f"{e.evidence_id} — {e.title} ({loc}) : passage ressemblant à une instruction, "
            "traité comme donnée et exclu de la synthèse."
        )
    st.markdown(f"**{e.evidence_id}** — {e.title}, {loc} (`{e.source_id}`)\n\n> {e.excerpt}")

# ---------------------------------------------------------------- 4. synthèse (après les limites)
st.subheader("Synthèse et points à vérifier")
st.markdown(f"**Résumé** ({report.summary_generated_by}) : {report.summary}")
for s in report.statements:
    if s.category == "interpretation":
        st.markdown(
            f"- **{s.statement_id}** ({s.generated_by}) {s.text} — _appuis : {', '.join(s.based_on)}_"
        )
st.markdown("**Points à vérifier (à valider par un spécialiste)**")
for p in report.points_to_verify:
    st.markdown(f"- **{p.recommendation_id}** {p.text}")
st.markdown("**Vérifications humaines recommandées**")
for h in report.human_verifications:
    st.markdown(f"- **{h.recommendation_id}** {h.text}")

# ---------------------------------------------------------------- 5. sources, contrôles, trace
with st.expander("Sources et provenance", expanded=False):
    st.dataframe(
        pd.DataFrame([s.model_dump(exclude={"loaded_at"}) for s in report.sources]),
        hide_index=True,
        width="stretch",
    )
with st.expander("Contrôles de vérification et trace des agents", expanded=False):
    if report.verification:
        st.dataframe(
            pd.DataFrame([c.model_dump() for c in report.verification.checks]), hide_index=True
        )
    st.dataframe(
        pd.DataFrame([t.model_dump(exclude={"started_at"}) for t in report.agent_trace]),
        hide_index=True,
    )

# ---------------------------------------------------------------- 6. téléchargements
st.subheader("Téléchargements")
d1, d2, d3, d4 = st.columns(4)
d1.download_button("Rapport JSON", paths["json"].read_bytes(), "report.json", "application/json")
d2.download_button("Rapport Markdown", paths["markdown"].read_bytes(), "report.md", "text/markdown")
if "findings" in paths:
    d3.download_button(
        "Constats GeoJSON",
        paths["findings"].read_bytes(),
        "findings.geojson",
        "application/geo+json",
    )
if "map" in paths:
    d4.download_button("Carte PNG", paths["map"].read_bytes(), "map.png", "image/png")

st.caption(DISCLAIMER)
