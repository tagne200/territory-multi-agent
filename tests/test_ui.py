"""Test fonctionnel de l'interface Streamlit (ignoré si Streamlit n'est pas installé)."""

from __future__ import annotations

import pytest

from .conftest import ROOT

st_testing = pytest.importorskip("streamlit.testing.v1")


def test_streamlit_app_runs_demo(monkeypatch):
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("TA_LLM_PROVIDER", "none")
    at = st_testing.AppTest.from_file(
        str(ROOT / "src" / "territory_assistant" / "ui" / "streamlit_app.py"), default_timeout=120
    )
    at.run()
    assert not at.exception
    assert any("résultats à vérifier par un spécialiste" in w.value for w in at.warning)
    at.button(key="run").click().run()
    assert not at.exception
    assert at.metric[0].value == "à vérifier"
    headers = [h.value for h in at.subheader]
    assert headers.index("⚠️ Données manquantes et avertissements") < headers.index(
        "Synthèse et points à vérifier"
    )
