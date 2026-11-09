# Organisation du travail (Kanban proposé)

> Ce tableau est une **proposition** pour GitHub Projects, Jira ou Trello. Aucun outil de gestion de
> projet n'a été utilisé pour réaliser ce prototype : seuls Git et GitHub (dépôt) l'ont été.

Colonnes : **Backlog → À faire → En cours → En revue → Terminé**.

État à la livraison de la v0.1.0 : les tâches 1 à 10 sont dans **Terminé** ; les tâches B1 à B5
restent dans le **Backlog**.

| # | Tâche | Critère d'acceptation vérifiable | Vérification |
|---|---|---|---|
| 1 | Cadrage du scénario | Question type, zone fictive et 3 thèmes définis ; caractère fictif documenté | `docs/data_sources.md` §1 |
| 2 | Données d'exemple | Script reproductible ; 3 couches (2 CRS différents), 3 documents, `.meta.json` ; valeurs attendues analytiques | `python scripts/generate_sample_data.py` |
| 3 | Moteur SIG | Refus d'un CRS absent ; mesures uniquement en CRS projeté ; R1 = 2 000 m ± 0,5 % ; V1 = 40 ha ± 0,5 % | `pytest tests/test_spatial.py` (20 tests) |
| 4 | Recherche documentaire | Extraits verbatim avec section/page ; message explicite si aucun résultat ; injection signalée | `pytest tests/test_documents.py` (18 tests) |
| 5 | Orchestration des agents | 5 agents dans un ordre fixe ; trace (durée, statut) dans le rapport ; régénération bornée à 1 | section 11 de `examples/demo_valbrume/report.md` |
| 6 | Validation des schémas | Modèles Pydantic `extra="forbid"` ; JSON Schema publié ; sortie LLM hors schéma rejetée | `territory-assistant schema` ; `test_invalid_llm_output_falls_back_to_rules` |
| 7 | Tests | Suite pytest verte sans clé API ; lint Ruff propre ; CI GitHub Actions | `pytest` ; `ruff check` ; onglet *Actions* |
| 8 | Interface / CLI | `territory-assistant demo` produit JSON, Markdown, PNG, GeoJSON ; Streamlit affiche le bandeau et les avertissements avant les recommandations | `tests/test_ui.py`, `test_cli_demo_without_api_key` |
| 9 | Documentation | README + 5 documents ; distinction fictif / réel / calcul / LLM / recommandation | relecture |
| 10 | Démonstration finale | Exemple généré par le système versionné ; évaluation 6/6 | `examples/` |
| B1 | API FastAPI | `POST /analyses` renvoie un `AnalysisReport` valide | à faire |
| B2 | Données ouvertes réelles | Une zone réelle documentée (source, date, licence, CRS) | à faire |
| B3 | Recherche hybride | Rappel documentaire ≥ BM25 sur un jeu élargi, mesuré | à faire |
| B4 | Test avec un vrai LLM | Cas 06 rejoué avec l'API ; coût et résultats consignés | à faire |
| B5 | Métadonnées ISO 19115 | Lecture d'une fiche XML à la place du `.meta.json` | à faire |

## Création facultative des tickets avec `gh`

```bash
gh issue create --title "B1 — API FastAPI" --body "Critère : POST /analyses renvoie un AnalysisReport valide."
gh project create --owner @me --title "territory-multi-agent"   # nécessite le scope 'project'
```
