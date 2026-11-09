# Limites, hypothèses et sécurité

## Usage

- **Outil non décisionnel.** Il ne dit jamais qu'un projet est autorisé, interdit ou conforme, et ne
  remplace ni un ingénieur, ni un géomaticien, ni l'autorité compétente.
- Une intersection géométrique **n'est pas** une preuve de risque ou de contrainte. Il faut d'abord
  vérifier la définition, la date, la précision et le statut de la couche.
- Les données d'exemple sont fictives. Les résultats de la démonstration n'ont aucune valeur réelle.

## SIG

- Les mesures sont faites dans un seul CRS projeté : UTM estimé automatiquement ou CRS imposé avec
  `--metric-crs`. L'UTM convient aux petites zones. Pour la métropole, EPSG:2154 est préférable.
- La précision des résultats ne peut pas dépasser celle des couches d'entrée. L'échelle est signalée
  à partir de 1/25 000, mais aucune incertitude positionnelle n'est propagée dans les calculs.
- `make_valid` peut modifier une géométrie invalide. Chaque réparation est signalée et doit être contrôlée.
- La somme des parts de zone par couche est une somme brute : les recouvrements entre entités d'une
  même couche ne sont pas déduits (c'est indiqué dans le texte).
- Les zones sont limitées à `TA_MAX_AREA_KM2` (100 km² par défaut). Il n'y a pas de traitement par
  tuiles pour les grandes couches (limite `TA_MAX_FEATURES`).
- Un GeoJSON sans membre `crs` est supposé en WGS84, comme le prévoit la RFC 7946. Ce cas est signalé.
  Un autre format sans CRS est refusé.

## Documents

- La recherche est lexicale (BM25) : pas de synonymes, et des passages peu informatifs peuvent
  remonter (mesuré dans [evaluation.md](evaluation.md)).
- Les PDF scannés ne sont pas lus (pas d'OCR). Les pages vides sont signalées.
- La détection d'instructions repose sur une liste de motifs FR/EN : elle **n'est pas exhaustive**.
  La protection principale reste structurelle : les passages suspects sont exclus du LLM, le LLM n'a
  aucun outil, ses sorties sont contraintes par un schéma puis vérifiées.

## LLM

- Le mode LLM (Anthropic, modèle par défaut `claude-opus-5-5`) **n'a pas été exécuté contre l'API
  réelle** pendant le développement : seuls la conversion des erreurs du SDK et le comportement du
  pipeline avec un client simulé sont testés.
- Le LLM peut seulement reformuler la question et rédiger le résumé, les interprétations et les points
  à vérifier. Une sortie rejetée deux fois est remplacée par la synthèse par règles, et le rapport le signale.
- Contrôle des chiffres : les entiers de 0 à 10 sont acceptés (dénombrements), ce qui laisse passer de
  petits nombres inventés. Les tolérances d'arrondi sont de 0,5 % ou de 0,011.
- Le contrôle du langage décisionnel repose sur des motifs : une paraphrase peut lui échapper.
- Le fallback serveur en cas de refus (`TA_LLM_SERVER_FALLBACK=true`, fonctionnalité beta Anthropic)
  peut faire répondre un autre modèle. Il est désactivable.

## Sécurité et robustesse

| Risque | Protection |
|---|---|
| Fichier trop volumineux / vide | `TA_MAX_FILE_MB`, 10 Mo pour les documents ; refus des fichiers vides |
| Trop d'entités | comptage avant lecture (`pyogrio.read_info`) |
| Chemin inattendu, `..`, lien | résolution puis comparaison aux répertoires autorisés |
| Extension inattendue | liste blanche |
| Fichier corrompu / mal encodé / binaire | `DataReadError`, couche ou document isolé, signalé dans le rapport |
| Géométrie vide ou invalide | suppression ou `make_valid`, signalées |
| CRS absent / incohérent | refus explicite (`CRSError`) |
| Sortie LLM hors schéma | JSON Schema côté API + Pydantic `extra="forbid"` côté prototype |
| Injection dans un document | détection, exclusion, balises `<donnees>`, aucun outil pour le LLM |
| Fuite de clé | clé lue par le SDK depuis l'environnement ; `.env` ignoré par Git ; `.env.example` sans secret |
| Fichiers téléversés (Streamlit) | noms assainis, dossier de session dédié sous `reports/uploads/` (non versionné) |
