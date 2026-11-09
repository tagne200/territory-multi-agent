# Historique des versions

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Versionnage sémantique.

## [Non publié]

### Ajouté
- Documentation complète :
  - index `docs/README.md` ;
  - guides d'installation, d'utilisation, de configuration et développeur ;
  - référence des formats ;
  - document de sécurité ;
  - support de présentation ;
  - `CONTRIBUTING.md` et ce fichier.
- Textes d'aide pour toutes les options du CLI.

## [0.1.0] — 2026-11-09

### Ajouté
- Orchestration de 5 agents : cadrage, analyse SIG, recherche documentaire, synthèse, vérification,
  avec trace d'exécution et une régénération LLM au plus.
- Moteur SIG déterministe (GeoPandas, Shapely, PyProj, pyogrio) :
  - contrôle et reprojection des CRS ;
  - réparation des géométries ;
  - intersections, proximité ;
  - longueurs, surfaces et parts.
- Recherche documentaire BM25 locale avec extraits verbatim et détection d'injection.
- Registre des sources : provenance, licence, CRS, empreinte, traitements.
- Mode sans LLM par défaut ; fournisseur Anthropic facultatif (sortie JSON contrainte et revalidée).
- Rapports JSON et Markdown, carte PNG, constats GeoJSON ; CLI et interface Streamlit.
- Données d'exemple fictives générées par script ; 6 cas d'évaluation ; 69 tests ; CI GitHub Actions.

### Corrigé (pendant le développement)
- Le contrôle des chiffres acceptait un chiffre inventé par le LLM dans le résumé s'il apparaissait
  aussi dans une autre de ses phrases (justification circulaire). Seuls les calculs SIG, les faits
  produits par règles et les extraits peuvent désormais justifier un chiffre.
