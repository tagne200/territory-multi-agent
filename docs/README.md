# Documentation

> **Prototype d'aide à l'analyse — résultats à vérifier par un spécialiste.**

Documentation du prototype *territory-multi-agent*, classée par besoin.

## Utiliser le prototype

| Document | Contenu |
|---|---|
| [installation.md](installation.md) | Prérequis, installation, vérification, dépannage |
| [user_guide.md](user_guide.md) | Démonstration, analyse de vos données, CLI, interface Streamlit, lecture du rapport |
| [configuration.md](configuration.md) | Variables d'environnement, fichier `.env`, mode LLM |
| [data_formats.md](data_formats.md) | Formats d'entrée, fichiers `.meta.json`, structure du rapport, identifiants |

## Comprendre le système

| Document | Contenu |
|---|---|
| [architecture.md](architecture.md) | Architecture, flux, choix techniques, fiche détaillée de chaque agent (prompt, schéma, erreurs, tests) |
| [data_sources.md](data_sources.md) | Données d'exemple fictives, valeurs attendues, vérification de données ouvertes réelles |
| [evaluation.md](evaluation.md) | Mesures définies, cas d'évaluation, résultats obtenus |
| [security.md](security.md) | Menaces considérées et protections mises en place |
| [limitations.md](limitations.md) | Limites connues et hypothèses |
| [report_schema.json](report_schema.json) | JSON Schema du rapport (généré) |

## Contribuer et présenter

| Document | Contenu |
|---|---|
| [developer_guide.md](developer_guide.md) | Organisation du code, conventions, tests, extensions (fournisseur LLM, thème, cas d'évaluation) |
| [kanban.md](kanban.md) | Organisation proposée, tâches et critères d'acceptation |
| [presentation.md](presentation.md) | Support de présentation en entretien : pitch, démonstration, questions fréquentes |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Règles de contribution |
| [../CHANGELOG.md](../CHANGELOG.md) | Historique des versions |

## Lexique

| Terme | Sens dans ce projet |
|---|---|
| **Constat** (`F-…`) | Relation géométrique calculée entre une entité d'une couche et la zone d'étude |
| **Extrait** (`D-…`) | Passage court et verbatim d'un document local |
| **Fait calculé** (`C-…`) | Phrase produite **par règles** à partir des constats |
| **Interprétation** (`I-…`) | Point à investiguer, produit par règles ou par le LLM, toujours appuyé sur des identifiants |
| **Source** (`layer:…`, `doc:…`, `area:…`, `input:…`) | Entrée du registre de provenance |
| **CRS de calcul** | CRS projeté métrique unique dans lequel toutes les mesures sont faites |
| **Tampon** | Distance (200 m par défaut) jusqu'à laquelle une entité proche est signalée sans intersecter la zone |
