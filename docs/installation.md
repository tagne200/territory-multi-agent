# Installation

## 1. Prérequis

| Élément | Version | Remarque |
|---|---|---|
| Python | ≥ 3.11 | testé localement en 3.14 (Windows 11), en CI en 3.11 et 3.13 (Ubuntu) |
| Git | toute version récente | pour cloner le dépôt |
| GDAL | **non requis séparément** | fourni par les roues binaires de `pyogrio` |
| Clé API | **non requise** | seulement pour le mode LLM facultatif |

## 2. Installation

```bash
git clone https://github.com/tagne200/territory-multi-agent.git
cd territory-multi-agent
python -m venv .venv
```

Activation de l'environnement :

| Système | Commande |
|---|---|
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
| Windows (cmd) | `.venv\Scripts\activate.bat` |
| Linux / macOS | `source .venv/bin/activate` |

Installation du paquet (mode éditable) avec les options voulues :

```bash
pip install -e "."                 # cœur seul : CLI, moteur SIG, rapports
pip install -e ".[dev]"            # + pytest et ruff
pip install -e ".[dev,llm,ui]"     # + SDK anthropic (mode LLM) + Streamlit (interface)
```

| Option | Paquets | Utilité |
|---|---|---|
| (cœur) | geopandas, shapely, pyproj, pyogrio, pydantic, matplotlib, pypdf, python-dotenv | analyse complète sans LLM |
| `dev` | pytest, ruff | tests et qualité du code |
| `llm` | anthropic (2.x) | mode LLM facultatif |
| `ui` | streamlit (≥ 1.50) | interface web de démonstration |

## 3. Vérifier l'installation

```bash
territory-assistant --help
territory-assistant demo
pytest
```

Résultats attendus :

- `demo` affiche les 5 agents, puis `statut : à vérifier` et les chemins de quatre fichiers
  (`map.png`, `findings.geojson`, `report.json`, `report.md`) dans `reports/TA-…/` ;
- `pytest` affiche `69 passed` (le test Streamlit est ignoré si l'option `ui` n'est pas installée).

## 4. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `territory-assistant` introuvable | environnement non activé | activer `.venv`, ou utiliser `python -m territory_assistant.cli` |
| Erreur d'installation de `pyogrio` ou `pyproj` | aucune roue binaire pour la plate-forme ou la version de Python | utiliser une version de Python disposant de roues (3.11 à 3.13 sont les plus sûres), mettre `pip` à jour |
| Accents illisibles dans la console Windows | encodage de la console | le CLI force l'UTF-8 ; sinon `chcp 65001` ou `set PYTHONIOENCODING=utf-8` |
| `Chemin … refusé (hors des répertoires autorisés)` | fichier situé hors du répertoire courant | lancer depuis le dossier parent des données, ou ajouter `--root <dossier>` |
| `SDK anthropic non installé` | option `llm` absente | `pip install -e ".[llm]"` |
| `Mode LLM demandé mais indisponible (authentification)` | clé absente ou invalide | voir [configuration.md](configuration.md) ; l'analyse continue sans LLM |
| `streamlit: command not found` | option `ui` absente | `pip install -e ".[ui]"` |

## 5. Désinstallation

Supprimer le dossier `.venv` et, si besoin, `reports/` (fichiers générés, non versionnés).
