# Guide développeur

## 1. Organisation du code

| Module | Responsabilité | Dépend du LLM ? |
|---|---|---|
| `config.py` | `Settings` (env + `.env`), extensions acceptées, thèmes et mots-clés | non |
| `errors.py` | exceptions métier (`InputFileError`, `DataReadError`, `CRSError`, `GeometryError`) | non |
| `safety.py` | chemins sûrs, assainissement des noms, détection de texte ressemblant à des instructions | non |
| `models.py` | tous les modèles Pydantic (entrées, sorties d'agents, rapport) | non |
| `source_registry.py` | registre de provenance, lecture des `.meta.json` | non |
| `spatial/loader.py` | lecture GeoJSON/GPKG avec garde-fous | non |
| `spatial/validation.py` | CRS, plausibilité des coordonnées, choix du CRS métrique, réparation des géométries | non |
| `spatial/analysis.py` | préparation de la zone et des couches, intersections, mesures | non |
| `documents/loader.py` | découpage des documents en passages | non |
| `documents/search.py` | index BM25, extraits verbatim | non |
| `llm/base.py` | interface `LLMClient`, erreurs typées, `ScriptedLLMClient`, `call_structured` | — |
| `llm/anthropic_client.py` | fournisseur Anthropic (SDK officiel) | — |
| `agents/*.py` | les 5 agents, plus `base.py` (contexte, formatage et extraction des nombres) | agents 1 et 4 seulement |
| `pipeline.py` | inventaire des entrées, orchestration, boucle de régénération, assemblage du rapport | non |
| `reporting/*` | JSON, Markdown, carte PNG, GeoJSON | non |
| `evaluation.py` | jeu d'évaluation et mesures | non |
| `cli.py`, `ui/streamlit_app.py` | interfaces | non |

Règle d'architecture : **aucun module SIG ou documentaire n'importe `llm`**. Seuls les agents 1 et 4
reçoivent un `LLMClient`, et toujours de façon facultative (`None` = mode déterministe).

## 2. Cycle de développement

```bash
pip install -e ".[dev,llm,ui]"
pytest                                   # 69 tests, environ 10 s
pytest tests/test_spatial.py -k crs      # sous-ensemble
ruff check src tests scripts             # lint
ruff format src tests scripts            # formatage (ligne de 100 caractères)
territory-assistant evaluate             # 6 cas
```

La CI (`.github/workflows/ci.yml`) exécute, sous Python 3.11 et 3.13 : installation, lint, tests,
évaluation et démonstration. Une contribution doit laisser les quatre au vert.

## 3. Stratégie de test

| Niveau | Fichier | Principe |
|---|---|---|
| Unitaire SIG | `test_spatial.py` | géométries construites en Lambert-93 avec des valeurs exactes (carré de 1 000 m, etc.) |
| Unitaire documents et sécurité | `test_documents.py` | documents d'exemple et fichiers malformés créés dans `tmp_path` |
| Agents | `test_agents.py` | agents 1 à 3 exécutés sur l'exemple, puis synthèses altérées volontairement pour déclencher chaque contrôle de l'agent 5 ; LLM simulé par `ScriptedLLMClient` |
| Bout en bout | `test_pipeline.py` | `run_analysis` et `write_outputs`, CLI, évaluation |
| Interface | `test_ui.py` | `streamlit.testing.v1.AppTest` (ignoré sans Streamlit) |

Aucun test n'appelle de réseau ni ne demande de clé. Pour tester un comportement LLM, on scripte les
réponses :

```python
from territory_assistant.llm import ScriptedLLMClient, LLMTimeoutError
llm = ScriptedLLMClient([
    {"reformulated_question": "…", "ambiguities": []},   # agent 1
    LLMTimeoutError("délai"),                             # agent 4 : erreur simulée
])
```

## 4. Régénérer les artefacts versionnés

| Artefact | Commande |
|---|---|
| Données d'exemple | `python scripts/generate_sample_data.py` |
| JSON Schema | `territory-assistant schema docs/report_schema.json` |
| Exemple de rapport | `territory-assistant demo --no-llm --out tmp`, puis copier le dossier produit dans `examples/demo_valbrume/` |
| Résultats d'évaluation | `territory-assistant evaluate --out examples/evaluation_results.json` |

Après avoir modifié un modèle Pydantic, régénérer le schéma et l'exemple pour qu'ils restent cohérents.

## 5. Étendre le prototype

### Ajouter un fournisseur LLM

1. Créer `llm/mon_fournisseur.py` avec une classe qui hérite de `LLMClient` et implémente
   `complete_json(system, user, schema, max_tokens) -> dict`.
2. Convertir toutes les erreurs du SDK en sous-classes de `LLMError` (`LLMAuthError`,
   `LLMRateLimitError`, `LLMTimeoutError`, `LLMUnavailableError`, `LLMRefusalError`,
   `LLMOutputError`). Les agents n'interceptent que `LLMError`.
3. Ne transmettre **aucun outil** au modèle.
4. Ajouter la valeur dans `Settings.llm_provider` et dans `build_llm_client`.
5. Tester la conversion des erreurs comme dans `test_anthropic_error_mapping`.

### Ajouter un thème de couche

1. `config.py` : ajouter le thème à `KNOWN_THEMES`, `THEME_LABELS` et `THEME_KEYWORDS`, et, s'il est
   attendu dans toute analyse, à `EXPECTED_THEMES`.
2. `models.py` : ajouter la valeur au `Literal` de `SidecarMetadata.theme`.
3. `agents/synthesis_agent.py` : ajouter les phrases d'interprétation et d'action dans `THEME_RULES`.
   Ces phrases ne doivent **pas contenir de chiffre** et doivent formuler des points à vérifier, jamais
   des conclusions.
4. Ajouter un test et, si possible, un cas d'évaluation.

### Ajouter un contrôle de vérification

Ajouter un bloc dans `VerificationAgent.run`, qui produit un `Check(name, passed, details)` et
alimente `feedback`. Un contrôle en échec rend la synthèse « non conforme », ce qui déclenche une
régénération si le contenu fautif vient du LLM. Ajouter un test qui provoque volontairement l'échec.

### Ajouter un cas d'évaluation

Créer `evaluation/cases/NN_nom.json` (format décrit dans [evaluation.md](evaluation.md) § 5). Les
valeurs attendues doivent être établies **indépendamment du code** : calcul analytique ou valeur de
référence documentée.

## 6. Conventions

- Messages, rapports et documentation en français ; identifiants de code en anglais.
- Tout nouveau modèle hérite de `StrictModel` (`extra="forbid"`).
- Une erreur de donnée ne doit jamais interrompre l'analyse sans produire de rapport. Il faut soit
  isoler l'élément (couche en `load_status="error"`), soit produire un rapport `bloqué`.
- Toute mesure doit porter son unité et son CRS de calcul.
- Ne jamais écrire de texte décisionnel (« autorisé », « conforme », « sans risque ») dans les
  phrases produites par règles : l'agent 5 le refuserait.
