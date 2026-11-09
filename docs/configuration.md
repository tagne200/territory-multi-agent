# Configuration

La configuration est lue dans les **variables d'environnement**. Un fichier `.env` situé dans le
répertoire courant est chargé s'il existe, sans écraser les variables déjà définies. Ce fichier est
ignoré par Git. Le modèle est [`.env.example`](../.env.example).

```bash
cp .env.example .env      # Windows : copy .env.example .env
```

**Aucune variable n'est nécessaire** pour le mode sans LLM ni pour les tests.

## 1. Variables

### LLM (facultatif)

| Variable | Défaut | Valeurs | Effet |
|---|---|---|---|
| `TA_LLM_PROVIDER` | `none` | `none`, `anthropic` | active le fournisseur LLM |
| `TA_LLM_MODEL` | `claude-opus-5-5` | identifiant de modèle | modèle appelé |
| `TA_LLM_EFFORT` | `medium` | `low`, `medium`, `high`, `xhigh`, `max` | profondeur de raisonnement (`output_config.effort`) |
| `TA_LLM_TIMEOUT_S` | `60` | 0 à 600 | délai maximal d'un appel, en secondes |
| `TA_LLM_MAX_RETRIES` | `2` | 0 à 5 | nouvelles tentatives automatiques du SDK (erreurs réseau, 429, 5xx) |
| `TA_LLM_SERVER_FALLBACK` | `true` | `true`, `false` | fallback serveur en cas de refus du modèle (beta Anthropic) |
| `ANTHROPIC_API_KEY` | — | clé | lue **directement par le SDK**, jamais par le prototype |

### Garde-fous

| Variable | Défaut | Effet |
|---|---|---|
| `TA_MAX_FILE_MB` | `50` | taille maximale d'une zone ou d'une couche (Mo) |
| `TA_MAX_FEATURES` | `50000` | nombre maximal d'entités par fichier, contrôlé avant la lecture |
| `TA_MAX_AREA_KM2` | `100` | surface maximale de la zone d'étude |

### Analyse

| Variable | Défaut | Effet |
|---|---|---|
| `TA_BUFFER_M` | `200` | tampon de proximité en mètres (0 = désactivé) |
| `TA_METRIC_CRS` | vide | CRS de calcul imposé (ex. `EPSG:2154`) ; vide = UTM estimé à partir de la zone |
| `TA_STALE_DATA_YEARS` | `5` | âge au-delà duquel une couche est signalée comme ancienne |

### Paramètres fixés dans le code

Ces paramètres ne sont pas exposés en variables d'environnement. On les modifie dans
`config.Settings` ou en construisant un `Settings(...)` en Python.

| Paramètre | Valeur | Effet |
|---|---|---|
| `max_doc_mb` | 10 | taille maximale d'un document |
| `doc_top_k` | 8 | nombre maximal d'extraits documentaires |
| `doc_min_score` | 1.0 | score BM25 minimal d'un extrait |

## 2. Priorité des réglages

1. Options du CLI (`--llm`, `--no-llm`, `--buffer`, `--metric-crs`). Si `--llm` et `--no-llm` sont
   fournis ensemble, c'est `--llm` qui s'applique.
2. Variables d'environnement déjà définies.
3. Fichier `.env`.
4. Valeurs par défaut.

## 3. Activer le mode LLM

```bash
pip install -e ".[llm]"
# dans .env (jamais versionné) :
TA_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
```

Ensuite : `territory-assistant demo` (ou `--llm anthropic` sans modifier `.env`).

Ce que le LLM fait et ne fait pas :

- il **reformule** la question (agent 1) et **rédige** le résumé, les interprétations et les points à
  vérifier (agent 4) ;
- il ne reçoit **aucun outil**, ne calcule rien, n'écrit ni les faits calculés ni les citations ;
- sa sortie est contrainte par JSON Schema, puis revalidée par Pydantic ; ses chiffres et ses
  références sont contrôlés par l'agent 5 ;
- en cas d'erreur (clé, quota, délai, indisponibilité, refus, sortie hors schéma), l'analyse continue
  en mode déterministe et le rapport l'indique.

Chaque analyse en mode LLM fait au plus trois appels : un pour le cadrage, un pour la synthèse et au
plus une régénération. Le repli final est déterministe et ne fait pas d'appel. Le coût dépend du
modèle et du volume des constats.

## 4. Bonnes pratiques pour la clé

- La clé ne doit jamais apparaître dans le code, dans `.env.example`, dans un ticket ou dans un
  commit. `.env` et `.env.*` sont dans `.gitignore`.
- En CI, la clé n'est pas nécessaire : les tests utilisent un client LLM simulé.
- En cas de fuite, révoquer la clé dans la console du fournisseur.
