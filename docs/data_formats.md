# Formats de données

## 1. Entrées

### Zone d'étude

| Règle | Détail |
|---|---|
| Formats | `.geojson`, `.json`, `.gpkg` |
| Géométrie | Polygon ou MultiPolygon uniquement ; plusieurs entités sont fusionnées (et c'est signalé) |
| CRS | obligatoire ; coordonnées cohérentes avec le CRS déclaré |
| Taille | ≤ `TA_MAX_FILE_MB` ; surface ≤ `TA_MAX_AREA_KM2` |

### Couches SIG

| Règle | Détail |
|---|---|
| Formats | GeoJSON, GeoPackage. Si un GeoPackage contient plusieurs couches, le nom de couche est obligatoire (`gpkg_layer`) |
| Géométries | points, lignes ou polygones ; les géométries vides sont ignorées et les invalides réparées (`make_valid`), dans les deux cas avec un signalement |
| Attributs | libres ; l'identifiant et le libellé sont désignés dans le `.meta.json`. Les valeurs sont tronquées à 200 caractères dans le rapport |
| Limite | ≤ `TA_MAX_FEATURES` entités |

### Documents

| Format | Découpage | Localisation retournée |
|---|---|---|
| `.md` (UTF-8) | par titre, puis par paragraphe | `section` = titre Markdown |
| `.txt` (UTF-8) | par paragraphe | — |
| `.pdf` (texte extractible) | par page, puis par paragraphe | `page` |

Les paragraphes de plus de 1 200 caractères sont redécoupés aux fins de phrase. Les extraits retournés
font au plus 420 caractères et sont toujours une **sous-chaîne exacte** du passage. Sont refusés :
fichier binaire, encodage autre qu'UTF-8, PDF chiffré ou malformé.

## 2. Fichier de métadonnées `<nom>.meta.json`

Il est placé dans le même dossier que le fichier décrit, et `couche.geojson` va avec
`couche.meta.json`. Il est facultatif, mais fortement recommandé : sans lui, la provenance, la date et
la licence sont marquées « non renseignée ». Un champ inconnu rend le fichier invalide : il est alors
ignoré et signalé.

| Champ | Type | Usage |
|---|---|---|
| `name` | texte | nom affiché de la couche ou du document |
| `theme` | `hydrography`, `flood_hazard`, `land_use`, `other` | règles d'interprétation et mots-clés documentaires |
| `description` | texte | description de la couche |
| `provenance` | texte | producteur, URL, mode d'obtention |
| `date` | texte (`AAAA`, `AAAA-MM`, `AAAA-MM-JJ`) | date ou version ; sert au contrôle d'ancienneté |
| `license` | texte | licence de réutilisation |
| `scale_denominator` | entier > 0 | échelle de saisie (25 000 pour 1/25 000) ; avertissement à partir de 25 000 |
| `status` | texte | statut de la donnée ; « provisoire » déclenche un avertissement |
| `id_attribute` | texte | attribut identifiant (sinon : index de ligne, signalé) |
| `label_attribute` | texte | attribut de libellé affiché |
| `expected_attributes` | liste | attributs dont l'absence ou les valeurs vides sont comptées |
| `gpkg_layer` | texte | couche à lire dans un GeoPackage |
| `known_limitations` | liste | limites recopiées dans le registre des sources |
| `is_fictitious` | booléen | marque les données de démonstration |

Exemple :

```json
{
  "name": "Zones de vigilance inondation (fictives)",
  "theme": "flood_hazard",
  "provenance": "Données FICTIVES générées par scripts/generate_sample_data.py",
  "date": "2019-06",
  "license": "CC0-1.0",
  "scale_denominator": 25000,
  "status": "provisoire",
  "id_attribute": "id",
  "label_attribute": "alea",
  "expected_attributes": ["alea", "statut", "date_ref"],
  "gpkg_layer": "zones_vigilance",
  "is_fictitious": true
}
```

## 3. Rapport `report.json`

Le schéma complet est dans [report_schema.json](report_schema.json). Les champs de premier niveau
sont, dans l'ordre :

| Champ | Contenu |
|---|---|
| `analysis_id`, `created_at`, `tool_version` | identification de l'analyse |
| `mode`, `llm_model` | `sans LLM (déterministe)` ou fournisseur et modèle utilisés |
| `status` | `contrôles automatiques passés`, `à vérifier` ou `bloqué` |
| `question`, `project_type`, `parameters` | demande et paramètres effectifs (tampon, CRS de calcul, régénérations LLM…) |
| `scoping` | sortie de l'agent 1 |
| `study_area` | surface (m², ha), CRS d'origine et de calcul, emprise, géométrie WGS84 |
| `sources` | registre de provenance (voir § 4) |
| `layers` | métadonnées et état de chargement de chaque couche |
| `spatial_findings` | constats calculés |
| `document_evidence`, `document_search_note` | extraits, ou message explicite d'absence de résultat |
| `summary`, `summary_generated_by` | résumé et son auteur (`rules` ou `llm`) |
| `statements` | faits calculés, contenus documentaires, interprétations |
| `missing_information` | données manquantes |
| `uncertainties` | limites et incertitudes (`info`, `warning`, `critical`) |
| `points_to_verify`, `human_verifications` | recommandations, toutes « à valider par un spécialiste » |
| `verification` | résultat des contrôles de l'agent 5 |
| `agent_trace` | trace d'exécution |
| `disclaimer` | avertissement d'usage non décisionnel |

### Constat (`spatial_findings[]`)

| Champ | Exemple |
|---|---|
| `finding_id` | `F-L03-001` |
| `source_id`, `layer_id`, `layer_name`, `theme` | `layer:zones_vigilance_fictives`, `L03`, … |
| `feature_id`, `feature_label`, `attributes` | `V1`, `fort`, attributs bruts |
| `relation` | `intersects`, `touches_boundary`, `within_buffer` |
| `metrics[]` | `{name, value, unit, crs}` |
| `distance_m` | pour `within_buffer` |
| `operation`, `parameters`, `crs_transformation` | description du calcul |

Métriques possibles :

| Nom | Unité | Géométrie |
|---|---|---|
| `longueur_dans_zone` | m | ligne |
| `surface_dans_zone`, `surface_dans_zone_ha` | m², ha | polygone |
| `part_de_la_zone` | % de la surface de la zone | polygone |
| `part_de_l_entite_dans_zone` | % de la longueur ou de la surface de l'entité | ligne, polygone |
| `nombre_de_points_dans_zone` | entité(s) | point |
| `distance_a_la_zone` | m | toute géométrie (proximité) |

### Affirmation (`statements[]`, `missing_information[]`)

`{statement_id, category, text, source_ids, based_on, generated_by}`. La catégorie vaut
`computed_fact`, `document_content`, `interpretation` ou `missing_information`.

## 4. Registre des sources (`sources[]`)

| Champ | Contenu |
|---|---|
| `source_id` | identifiant stable (voir § 5) |
| `kind` | `study_area`, `gis_layer`, `document`, `user_input` |
| `filename` | chemin relatif au répertoire autorisé (aucun chemin absolu exposé) |
| `title`, `provenance`, `date_or_version`, `license` | « non renseignée » si inconnu, avec un avertissement |
| `crs` | CRS d'origine (couches et zone) |
| `loaded_at`, `sha256` | date de chargement et empreinte du fichier |
| `processing` | traitements appliqués, dans l'ordre |
| `known_limitations`, `is_fictitious`, `warnings` | limites et avertissements |

## 5. Conventions d'identifiants

| Préfixe | Objet | Produit par |
|---|---|---|
| `area:`, `layer:`, `doc:`, `input:` | sources (dérivées du nom de fichier) | registre |
| `L01`, `L02`… | couches, dans l'ordre fourni | agent 2 |
| `F-L01-001` | constat n° 1 de la couche L01 | agent 2 |
| `D-001` | extrait documentaire | agent 3 |
| `C-001` | fait calculé | agent 4 (règles) |
| `DC-001` | contenu documentaire | agent 4 (règles) |
| `I-001` | interprétation | agent 4 (règles ou LLM) |
| `M-001` | donnée manquante | agent 4 (règles) |
| `P-001`, `H-001` | point à vérifier, vérification humaine | agent 4 |
| `U-001` | incertitude de méthode, de sécurité ou liée au LLM | agent 4 |
| `UV-001` | avertissement sur les données | agent 5 |
| `UL-001`, `UP-001` | synthèse LLM rejetée, LLM indisponible au démarrage | orchestrateur |

## 6. `findings.geojson`

FeatureCollection en EPSG:4326 dont les propriétés sont `finding_id`, `source_id`, `layer`,
`feature_id` et `relation`. Pour une intersection, la géométrie est la **partie située dans la
zone**. Pour un contact en limite ou une proximité, c'est l'entité entière.
