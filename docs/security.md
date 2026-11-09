# Sécurité et robustesse

## 1. Principes

1. **Les fichiers sont des données, jamais des instructions.** Aucun contenu lu ne peut modifier
   les règles du prototype.
2. **Le LLM n'agit pas.** Il ne reçoit aucun outil, n'exécute pas de code, ne lit ni n'écrit de
   fichier. Il ne produit que du JSON, qui est ensuite validé.
3. **Les calculs sont déterministes.** Toute opération SIG est réalisée par du code Python.
4. **Défense en profondeur.** Chaque risque est couvert par plusieurs barrières. Aucune ne repose
   uniquement sur la bonne volonté du modèle.

## 2. Menaces et protections

| Menace | Protection | Où | Test |
|---|---|---|---|
| Chemin hors périmètre (`..`, lien, chemin absolu) | résolution du chemin puis comparaison aux répertoires autorisés | `safety.resolve_safe_path` | `test_path_outside_allowed_roots_is_refused`, `test_path_outside_roots_is_refused_in_pipeline` |
| Extension inattendue (`.exe`…) | liste blanche par type d'entrée | `config.*_EXTENSIONS` | `test_unexpected_extension_size_and_missing` |
| Fichier trop volumineux ou vide | limites `TA_MAX_FILE_MB` (couches) et 10 Mo (documents) ; refus des fichiers vides | `safety` | idem |
| Trop d'entités | comptage avant lecture complète | `spatial/loader.py` | `test_feature_limit` |
| Fichier corrompu | `DataReadError` ; la couche est isolée et l'analyse continue | loaders | `test_corrupted_file_raises_read_error`, `test_read_error_layer_is_isolated` |
| Document binaire, mal encodé, PDF malformé ou chiffré | refus explicite | `documents/loader.py` | `test_malformed_documents` |
| Métadonnées malformées | fichier ignoré et signalé, sans arrêt | `source_registry.load_sidecar` | — |
| Géométrie vide ou invalide | suppression ou `make_valid`, signalée avec la raison GEOS | `spatial/validation.py` | `test_invalid_geometry_is_repaired_with_warning` |
| CRS absent ou incohérent | refus ; contrôle de plausibilité des coordonnées | `spatial/validation.py` | `test_missing_crs_is_refused`, `test_implausible_coordinates_for_geographic_crs` |
| Mesure en degrés | CRS de calcul obligatoirement projeté et en mètres | `choose_metric_crs`, `prepare_layer` | `test_geographic_crs_refused_for_measurements` |
| **Injection dans un document** | détection de motifs, passage marqué, exclu de la synthèse et du LLM ; balises `<donnees>` ; consigne explicite dans les prompts ; aucun outil | `safety`, agents 3 et 4 | `test_injected_passage_is_not_used_nor_sent_to_llm` |
| Sortie LLM hors schéma | JSON Schema côté API, puis Pydantic `extra="forbid"` | `llm/base.call_structured` | `test_invalid_llm_output_falls_back_to_rules` |
| Chiffre ou citation inventés par le LLM | contrôle des nombres et des extraits verbatim ; sources dérivées, jamais reprises du modèle | agent 5 | `test_llm_summary_cannot_justify_its_own_numbers`, `test_altered_excerpt_is_flagged` |
| Formulation décisionnelle | motifs interdits | agent 5 | `test_forbidden_language_detection` |
| Boucle LLM infinie | 1 régénération au plus, puis repli déterministe | `pipeline.MAX_REGENERATIONS` | cas d'évaluation 05 |
| Fuite de clé API | clé lue par le SDK seulement ; `.env` ignoré par Git ; aucune clé en CI | `.gitignore` | — |
| Exposition de chemins locaux | chemins relatifs aux répertoires autorisés dans les rapports | `source_registry` | — |
| Fichiers téléversés (Streamlit) | noms assainis, dossier de session dédié, mêmes contrôles que le CLI | `ui/streamlit_app.py` | `test_sanitize_filename` |

## 3. Limites connues

- La détection d'injection repose sur une liste de motifs français et anglais : une formulation
  nouvelle peut lui échapper. La protection principale est structurelle : pas d'outil, sortie sous
  schéma, contrôle des références et des chiffres.
- Le contrôle du langage décisionnel peut être contourné par paraphrase.
- Le contrôle des chiffres accepte les entiers de 0 à 10.
- Aucune analyse antivirus des fichiers n'est faite : n'utilisez que des fichiers de confiance.
- L'interface Streamlit est prévue pour un usage **local**. Elle n'a ni authentification ni quota et
  ne doit pas être exposée sur Internet sans protection supplémentaire.

## 4. Signaler un problème

Ouvrir un ticket GitHub **sans y joindre de donnée sensible ni de clé**.
