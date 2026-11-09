# Évaluation

L'évaluation est **reproductible** et s'exécute sans clé API :

```bash
territory-assistant evaluate            # écrit reports/evaluation_results.json
```

Les cas sont décrits dans `evaluation/cases/*.json`. Les valeurs attendues sont **analytiques**
(géométries conçues en mètres, voir [data_sources.md](data_sources.md)), donc indépendantes du code évalué.
Les cas « LLM » utilisent un client simulé (`ScriptedLLMClient`) : ils testent les garde-fous, **pas la
qualité d'un vrai modèle**.

## 1. Mesures définies

| Mesure | Définition |
|---|---|
| `conformite_schema` | 1 si le rapport JSON écrit se relit et se revalide avec `AnalysisReport`, sinon 0 |
| `tracabilite` | part des affirmations, recommandations et constats dont toutes les références existent (registre, constats, extraits, affirmations) et qui ont au moins une référence lorsqu'elle est exigée |
| `precision_sig` / `rappel_sig` | sur les couples (source, entité, relation) attendus vs obtenus |
| `faux_positifs` | entités listées « ne doivent pas apparaître » mais présentes |
| `exactitude_mesures` | part des mesures attendues retrouvées à la tolérance près (0,5 %) |
| `rappel_documentaire` | part des sections documentaires attendues présentes parmi les extraits **non suspects** |
| contrôles booléens | injection signalée et non réutilisée ; contenu LLM rejeté ou conservé selon le cas ; informations manquantes attendues présentes ; contrôles de l'agent 5 tous passés |

## 2. Cas

| Cas | Objet | Faux positifs à éviter |
|---|---|---|
| 01_demo_valbrume | Scénario nominal (3 couches, 3 documents dont un piégé) | R4, V3, L5, L6 ; réutilisation du passage piégé |
| 02_zone_hors_donnees | Zone à 10 km : aucune entité attendue | toute entité |
| 03_couche_manquante | Couche inexistante, pas de couche inondation, pas de document | arrêt du traitement |
| 04_zone_inconnue | Zone introuvable : blocage propre | rapport invalide ou exception |
| 05_llm_chiffre_invente | LLM simulé : chiffre inventé + « sans risque », puis identifiants inexistants | conservation de tout texte LLM |
| 06_llm_conforme | LLM simulé conforme (le cadrage LLM échoue volontairement : sortie hors schéma) | rejet abusif d'un texte LLM correct |

## 3. Résultats obtenus (exécution du 2026-11-09, Python 3.14, Windows)

Sortie réelle de `territory-assistant evaluate` (fichier complet : `examples/evaluation_results.json`) :

```
cas                          statut                         schéma  traçab.  préc. rappel mesures  docs  résultat
01_demo_valbrume             à vérifier                       1.00     1.00   1.00   1.00    1.00  1.00  OK
02_zone_hors_donnees         à vérifier                       1.00     1.00   1.00   1.00       —     —  OK
03_couche_manquante          à vérifier                       1.00     1.00   1.00   1.00       —     —  OK
04_zone_inconnue             bloqué                           1.00     1.00   1.00   1.00       —     —  OK
05_llm_chiffre_invente       à vérifier                       1.00     1.00   1.00   1.00       —     —  OK
06_llm_conforme              à vérifier                       1.00     1.00   1.00   1.00       —     —  OK

6/6 cas réussis
```

Détail du cas 01 : traçabilité 41/41 éléments ; 8/8 mesures dans la tolérance ; 9 constats
attendus, 9 obtenus, aucun faux positif.

### Limite mesurée : précision documentaire

Dans le cas 01, sur 7 extraits non suspects retenus, 3 proviennent de passages **peu informatifs**
(l'avertissement « document fictif » en tête du guide et de la note, et l'objet du guide). Ils ne
sont pas faux, mais ils diluent la synthèse. Cela vient de la recherche lexicale : les mots de la
question (« étude », « aménagement ») figurent dans ces passages. Le champ
`extraits_hors_attendus` du fichier de résultats les liste.

## 4. Ce que ces résultats ne disent pas

- Ils ne mesurent **pas** la fiabilité sur des données réelles : 6 cas, construits pour ce prototype,
  sur des données fictives. **Aucun taux de fiabilité général n'est revendiqué.**
- Ils ne mesurent pas la qualité rédactionnelle d'un vrai LLM (aucun appel réel n'a été effectué
  pendant le développement ; le fournisseur Anthropic est testé uniquement pour la conversion des
  erreurs).
- Le contrôle des chiffres accepte les petits entiers de 0 à 10 (dénombrements) : un « 5 % » inventé
  passerait ce contrôle. Limite documentée dans [limitations.md](limitations.md).

## 5. Étendre le jeu d'évaluation

Ajouter un fichier `evaluation/cases/NN_nom.json` (même structure) : `request`, éventuellement
`llm_script` et `settings`, puis `expected` (`intersects`, `within_buffer`, `must_not_appear`,
`metrics`, `expected_doc_sections`, `suspicious_sources`, `missing_contains`, `status_in`,
`no_llm_content_kept`, `llm_content_kept`).
