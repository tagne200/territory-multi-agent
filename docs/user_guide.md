# Guide d'utilisation

> **Prototype d'aide à l'analyse — résultats à vérifier par un spécialiste.**

## 1. Démonstration en une commande

```bash
territory-assistant demo
```

Le scénario fictif est le suivant :

- zone : `data/sample/study_area.geojson` (300 ha) ;
- couches :
  - cours d'eau (GeoJSON, EPSG:4326) ;
  - zones de vigilance inondation (GeoPackage, EPSG:2154) ;
  - occupation du sol (GeoJSON) ;
- documents : un guide fictif, une note fictive et un document piégé de test ;
- question : « Quels éléments territoriaux doivent être examinés avant une étude d'aménagement dans
  cette zone ? ».

Sortie attendue :

```
[1] Agent 1 — Cadrage de la demande : ok — 0 information(s) manquante(s), 0 blocage(s)
[2] Agent 2 — Analyse SIG : ok — 3 couche(s), 9 constat(s)
[3] Agent 3 — Recherche documentaire : warning — 3 document(s), 8 extrait(s)
[4] Agent 4 — Synthèse territoriale : ok — 24 affirmation(s), résumé par rules
[5] Agent 5 — Vérification critique : ok — statut : à vérifier
```

Le `warning` de l'agent 3 est normal : il signale le passage piégé du document de test.

## 2. Analyser vos propres données

```bash
territory-assistant analyze \
  --area mes_donnees/zone.geojson \
  --layers mes_donnees/couches/ \
  --docs mes_donnees/documents/ \
  --question "Quels éléments territoriaux doivent être examinés avant l'étude ?" \
  --project-type "aménagement d'un bassin de rétention" \
  --metric-crs EPSG:2154 --buffer 100
```

Avant de lancer :

1. Vérifier que chaque couche **déclare un CRS**. Un fichier sans CRS est refusé (sauf GeoJSON,
   supposé en WGS84 selon la RFC 7946, ce qui est signalé).
2. Placer à côté de chaque fichier un `<nom>.meta.json` (voir [data_formats.md](data_formats.md)) :
   thème, provenance, date, licence, échelle, statut. Sans lui, ces informations apparaissent comme
   « non renseignée » et des avertissements sont émis.
3. Pour la métropole, imposer `--metric-crs EPSG:2154`. Sinon, une zone UTM est choisie
   automatiquement et ce choix est signalé.
4. Les fichiers doivent se trouver sous le répertoire courant, ou sous un répertoire passé avec
   `--root` (répétable).

## 3. Référence du CLI

```
territory-assistant {demo,analyze,evaluate,schema} [options]
```

| Commande | Rôle |
|---|---|
| `demo` | scénario fictif de démonstration |
| `analyze` | analyse d'une zone fournie |
| `evaluate` | exécute les cas de `evaluation/cases/` (sans LLM réel) |
| `schema` | écrit le JSON Schema du rapport (défaut : `docs/report_schema.json`) |

Options communes à `demo` et `analyze` :

| Option | Défaut | Effet |
|---|---|---|
| `--out DIR` | `reports` | répertoire de sortie |
| `--no-llm` | — | force le mode déterministe |
| `--llm {none,anthropic}` | `.env` | choisit le fournisseur LLM |
| `--buffer M` | 200 | tampon de proximité en mètres |
| `--metric-crs CRS` | UTM automatique | CRS de calcul imposé |
| `--quiet` | — | masque la trace des agents |

Options propres à `analyze` :

| Option | Obligatoire | Effet |
|---|---|---|
| `--area FICHIER` | oui | zone d'étude (GeoJSON, GeoPackage) |
| `--layers F/DIR …` | non | fichiers ou répertoires de couches (`*.meta.json` exclus automatiquement) |
| `--docs F/DIR …` | non | fichiers ou répertoires de documents |
| `--question TEXTE` | oui | question (1 à 2 000 caractères) |
| `--project-type TEXTE` | non | type de projet ; son absence est signalée |
| `--root DIR` | non | répertoire autorisé, répétable (défaut : répertoire courant) |

Codes de sortie :

| Code | Signification |
|---|---|
| 0 | rapport produit |
| 2 | analyse **bloquée** (zone absente ou inutilisable) ; un rapport explicatif est quand même produit |
| 1 | erreur inattendue, ou au moins un cas d'évaluation en échec (`evaluate`) |

## 4. Fichiers produits

Chaque analyse crée `reports/<identifiant>/`, avec un identifiant de la forme
`TA-AAAAMMJJ-HHMMSS-xxxxxx` :

| Fichier | Contenu |
|---|---|
| `report.json` | rapport complet, conforme à [report_schema.json](report_schema.json) |
| `report.md` | rapport lisible (mêmes informations) |
| `map.png` | carte de synthèse dans le CRS de calcul (absente si l'analyse est bloquée) |
| `findings.geojson` | géométries des constats en WGS84 : partie dans la zone, ou entité entière si proximité, avec `finding_id` et `source_id` (ouvrable dans QGIS) |

## 5. Lire le rapport

| Section | Ce qu'il faut regarder |
|---|---|
| Statut | `contrôles automatiques passés`, `à vérifier` (avertissements à lire) ou `bloqué` |
| 1. Question | reformulation par règles ou par LLM (indiqué) |
| 2. Zone | surface, CRS d'origine et CRS de calcul |
| 3. Sources | provenance, date, licence, CRS et **traitements appliqués** à chaque fichier |
| 4. Constats | entité, relation (`intersecte`, `touche la limite`, `à proximité`), mesures avec unité, transformation de CRS |
| 5. Extraits | passages verbatim ; ⚠️ = passage suspect, exclu de la synthèse |
| 6. Données manquantes | à combler avant toute conclusion |
| 7. Limites et incertitudes | 🔴 critique, 🟠 avertissement, 🔵 information |
| 8. Synthèse | interprétations et points à vérifier, avec leurs appuis (`F-…`, `D-…`, `C-…`) |
| 9. Vérifications humaines | qui doit vérifier quoi |
| 10. Contrôles | résultat des 7 contrôles de l'agent 5 |
| 11. Trace | durée et statut de chaque agent |

**Retrouver la provenance d'un constat.** Prendre un constat, par exemple `F-L03-001`. Son
`source_id` (`layer:zones_vigilance_fictives`) mène à la ligne correspondante de la section 3
(fichier, empreinte SHA-256, CRS, traitements). Son `feature_id` (`V1`) désigne l'entité dans la
couche d'origine. Ses champs `operation` et `crs_transformation` décrivent le calcul effectué.

**Statut « à vérifier ».** C'est le cas le plus fréquent : il suffit d'un avertissement (couche
ancienne, statut provisoire, licence absente, géométrie réparée…). Il ne signale pas une erreur du
programme.

## 6. Interface Streamlit

```bash
streamlit run src/territory_assistant/ui/streamlit_app.py
```

1. **Zone** : zone d'exemple, zone fictive hors données ou fichier téléversé (avec son `.meta.json`
   si possible).
2. **Couches** et **documents** : sélection parmi les fichiers d'exemple, et téléversement possible.
3. **Question**, type de projet, tampon, puis activation facultative du LLM.
4. **Lancer l'analyse**.

L'affichage suit l'ordre de lecture recommandé :
- avertissements et données manquantes ;
- carte et constats ;
- extraits ;
- synthèse ;
- sources ;
- contrôles ;
- téléchargements (JSON, Markdown, GeoJSON, PNG).

Les fichiers téléversés sont enregistrés sous un nom assaini dans `reports/uploads/<session>/`
(non versionné).

## 7. Utilisation en Python

```python
from pathlib import Path
from territory_assistant.config import Settings
from territory_assistant.models import AnalysisRequest
from territory_assistant.pipeline import run_analysis
from territory_assistant.reporting import write_outputs

req = AnalysisRequest(
    question="Quels éléments territoriaux doivent être examinés ?",
    project_type="aménagement",
    study_area_path=Path("data/sample/study_area.geojson"),
    layer_paths=[Path("data/sample/layers/cours_eau_fictifs.geojson")],
    document_paths=[Path("data/sample/documents/guide_fictif_etudes_preliminaires.md")],
    allowed_roots=[Path.cwd()],
)
output = run_analysis(req, Settings(buffer_m=100))
print(output.report.status, len(output.report.spatial_findings))
write_outputs(output, Path("reports"))
```
