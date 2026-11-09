# Sources de données

## 1. Données d'exemple : entièrement FICTIVES

Toutes les données de `data/sample/` sont **fictives** et produites par
`scripts/generate_sample_data.py` (reproductible, sans téléchargement). Licence : CC0-1.0,
sauf la couche d'occupation du sol dont la licence est **volontairement omise** pour démontrer
l'avertissement « non renseignée ».

**Localisation volontairement en mer** (golfe de Gascogne, environ 46,5° N, 5° O) : aucune limite
fictive ne peut être confondue avec un territoire réel. Aucun fond de carte n'est utilisé.

| Fichier | Format / CRS | Contenu | Particularités volontaires |
|---|---|---|---|
| `study_area.geojson` | GeoJSON, EPSG:4326 | Rectangle 2 000 m × 1 500 m (300 ha) | — |
| `alt_areas/zone_hors_donnees.geojson` | GeoJSON, EPSG:4326 | Zone à 10 km à l'est | aucune donnée à proximité |
| `layers/cours_eau_fictifs.geojson` | GeoJSON, EPSG:4326 | R1–R4 | R3 sans nom (attribut manquant) ; R4 éloigné |
| `layers/zones_vigilance_fictives.gpkg` | GeoPackage, **EPSG:2154** | V1 (fort), V2 (modéré), V3 (faible) | date 2019, statut « provisoire », 1/25 000 |
| `layers/occupation_sol_fictive.geojson` | GeoJSON, EPSG:4326 | L1–L6 | L5 auto-intersectée (invalide), L6 géométrie vide, licence absente |
| `documents/guide_fictif_etudes_preliminaires.md` | Markdown | Guide fictif en 5 sections | — |
| `documents/note_fictive_couche_vigilance.txt` | Texte | Note fictive sur la couche V | — |
| `documents/document_test_injection.md` | Markdown | **Test de sécurité** : texte imitant une instruction | doit être signalé et ignoré |

Chaque fichier est accompagné d'un `<nom>.meta.json` (nom, thème, provenance, date, licence,
échelle, statut, attributs attendus, limites connues, `is_fictitious`).

### Valeurs attendues (analytiques)

Les géométries sont conçues en mètres dans un repère UTM 30N centré sur le point de référence ;
les valeurs attendues ne dépendent donc pas du code testé :

| Entité | Relation attendue | Mesure attendue |
|---|---|---|
| R1 | intersecte | 2 000 m dans la zone |
| R2 | à proximité | 150 m de la zone (tampon 200 m) |
| R3 | intersecte | 950 m dans la zone ; nom absent |
| R4 | aucune | — (faux positif à éviter) |
| V1 | intersecte | 400 000 m² = 40 ha = 13,33 % de la zone |
| V2 | intersecte | 880 000 m² = 88 ha = 29,33 % |
| V3 | aucune | — (à 1 000 m, hors tampon) |
| L1–L4 | intersecte | 750 000 m² chacune (25 %) |
| L5 | aucune | invalide, réparée, hors zone |
| L6 | ignorée | géométrie vide |

Les petites différences possibles (< 0,5 %) viennent des reprojections EPSG:2154 ↔ EPSG:4326 ↔ UTM.

## 2. Utiliser des données ouvertes réelles (non incluses)

Le dépôt **ne contient aucune donnée réelle** et n'en télécharge pas. Pour une étude réelle, avant
d'ajouter une couche :

1. **Source** : récupérer la donnée depuis le producteur officiel (pas un miroir), noter l'URL exacte
   et l'identifiant de la fiche de métadonnées.
2. **Date / version** : relever la date de production et de mise à jour sur la fiche ; comparer avec
   l'actualité attendue (le prototype avertit au-delà de `TA_STALE_DATA_YEARS`, 5 ans par défaut).
3. **Licence** : lire la licence sur la fiche (de nombreuses données publiques françaises sont
   diffusées sous Licence Ouverte Etalab 2.0, mais **chaque jeu doit être vérifié**) ; la reporter
   dans `license` du `.meta.json`.
4. **CRS** : vérifier le CRS déclaré dans le fichier (`ogrinfo -so fichier` ou `pyogrio.read_info`)
   et sa cohérence avec les coordonnées ; pour la métropole, imposer `--metric-crs EPSG:2154`.
5. **Échelle, statut, définition** : relever l'échelle de saisie, le statut (projet, approuvé, abrogé)
   et la définition exacte de la couche ; une zone d'aléa n'est pas un zonage réglementaire.
6. Renseigner le `.meta.json` correspondant (provenance = URL + producteur).

Familles de données souvent utiles (à vérifier au cas par cas) : référentiels hydrographiques
nationaux, données de risques naturels publiées par l'État, référentiels d'occupation du sol
(nationaux ou européens), documents d'urbanisme publiés sur les portails officiels.

## 3. Distinguer les natures d'information dans les sorties

| Nature | Où la trouver | Marquage |
|---|---|---|
| Données d'exemple fictives | `sources[].is_fictitious = true` | avertissement « Sources déclarées FICTIVES » |
| Données ouvertes réelles | `sources[]` avec provenance/licence renseignées | — |
| Résultats de calcul | `spatial_findings`, `statements[category=computed_fact]` | `generated_by = "rules"` |
| Texte généré par le modèle | `statements[category=interpretation]`, `points_to_verify`, `summary` | `generated_by = "llm"` |
| Recommandations à valider | `points_to_verify`, `human_verifications` | `validation_status = "à valider par un spécialiste"` |
