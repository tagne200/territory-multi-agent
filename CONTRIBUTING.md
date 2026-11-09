# Contribuer

Merci de votre intérêt. Ce dépôt est un **prototype de portfolio**. Les contributions sont bienvenues
si elles respectent ses principes : calculs déterministes, traçabilité, usage non décisionnel.

## Mise en place

```bash
git clone https://github.com/tagne200/territory-multi-agent.git
cd territory-multi-agent
python -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -e ".[dev,llm,ui]"
```

## Avant d'ouvrir une pull request

```bash
ruff format src tests scripts
ruff check src tests scripts
pytest
territory-assistant evaluate
```

Les quatre commandes doivent réussir : la CI exécute les mêmes contrôles sous Python 3.11 et 3.13.

## Règles

- **Pas de calcul SIG dans le LLM.** Toute opération géographique est une fonction Python testée.
- **Pas de nouvelle sortie LLM sans contrôle.** Un nouveau champ produit par le modèle doit être couvert
  par l'agent de vérification : références, chiffres, langage.
- **Pas de donnée réelle sans provenance.** Une couche ou un document ajouté doit avoir un `.meta.json`
  qui renseigne la source, la date, la licence et le CRS. Pas de données volumineuses ni soumises à une
  licence restrictive.
- **Aucune clé ni aucun secret** dans le code, les tests, les tickets ou les commits.
- Chaque correction de bug s'accompagne d'un test de non-régression.
- Messages et documentation en français ; identifiants de code en anglais.
- Mettre à jour [CHANGELOG.md](CHANGELOG.md) et la documentation concernée.

Le guide détaillé (architecture du code, extensions, régénération des artefacts) se trouve dans
[docs/developer_guide.md](docs/developer_guide.md).
