# Support de présentation (entretien)

## 1. Pitch (1 minute)

> Avant une étude d'aménagement, une équipe d'ingénierie doit savoir ce qui, dans la zone, mérite une
> vérification : cours d'eau, zones inondables, occupation du sol, documents de référence. J'ai
> construit un prototype multi-agents qui produit cette analyse préliminaire de façon **traçable**.
> Les calculs géographiques sont déterministes : GeoPandas, avec reprojection systématique avant toute
> mesure. Un LLM peut aider à rédiger, mais il ne calcule rien et ne cite rien sans vérification. Un
> agent vérificateur contrôle chaque chiffre, chaque référence et chaque citation. Le système dit
> explicitement ce qu'il ne sait pas. Il n'est pas décisionnel : chaque résultat est à valider par un
> spécialiste.

## 2. Démonstration (5 minutes)

| Étape | Action | Point à montrer |
|---|---|---|
| 1 | `territory-assistant demo` | les 5 agents tracés ; statut « à vérifier » |
| 2 | ouvrir `map.png` | zone, tampon de 200 m, R2 détecté à proximité, R4 et V3 ignorés |
| 3 | `report.md` § 3 Sources | provenance, licence « non renseignée », CRS, traitements |
| 4 | `report.md` § 4 Constats | V1 : 40 ha, soit 13,33 % de la zone, après reprojection EPSG:2154 → EPSG:32630 |
| 5 | `report.md` § 5 Extraits | passage piégé signalé ⚠️, exclu de la synthèse |
| 6 | `report.md` § 6–7 | données manquantes et incertitudes **avant** les recommandations |
| 7 | `report.md` § 10 | les 7 contrôles de l'agent 5 |
| 8 | `territory-assistant evaluate` | 6/6, dont le cas 05 où un LLM simulé invente un chiffre et se fait rejeter |
| 9 | (facultatif) Streamlit | même analyse dans l'interface, téléchargements |

## 3. Décisions de conception à défendre

| Décision | Pourquoi | Compromis accepté |
|---|---|---|
| Orchestration séquentielle simple plutôt qu'agents autonomes | lisible, testable, comportement prévisible | moins flexible face à des demandes ouvertes |
| SIG 100 % déterministe | un calcul de surface doit être exact et reproductible | aucun |
| LLM limité à la rédaction | réduit les hallucinations au seul texte interprétatif, qui est contrôlé | rédaction plus sobre sans LLM |
| Sources des affirmations LLM **dérivées** des identifiants cités | le modèle ne peut pas fabriquer de source plausible | — |
| BM25 plutôt qu'embeddings | reproductible, explicable, sans dépendance lourde | pas de synonymie (limite mesurée) |
| Données fictives placées en mer | aucune confusion possible avec un territoire réel ; vérité terrain analytique | pas de démonstration sur des données réelles |
| Statut « à vérifier » par défaut dès qu'un avertissement existe | l'outil ne doit pas rassurer à tort | statut rarement « vert » |

## 4. Questions probables

**Comment garantissez-vous que le LLM n'invente pas de chiffre ?**
Les chiffres des faits sont écrits par des règles à partir des métriques SIG. Si le LLM écrit un
nombre, l'agent 5 le compare aux métriques des constats cités, aux faits produits par règles et aux
extraits cités. Un texte LLM ne peut pas servir de justification à un autre texte LLM : c'est un bug
de justification circulaire que j'ai trouvé et corrigé grâce au jeu d'évaluation (test de
non-régression `test_llm_summary_cannot_justify_its_own_numbers`). Une sortie rejetée est régénérée
une fois, puis remplacée par la version déterministe.

**Et l'injection de prompt dans un document ?**
Plusieurs barrières : les passages suspects sont détectés et exclus du LLM, le contenu est encadré
comme donnée, le modèle n'a aucun outil, sa sortie est contrainte par un schéma, et ses références
sont vérifiées. La détection seule ne suffirait pas, car elle repose sur des motifs. C'est la
combinaison qui protège.

**Pourquoi reprojeter ? Comment choisissez-vous le CRS ?**
Une surface calculée en degrés n'a pas de sens. Toutes les couches sont ramenées dans un CRS projeté
métrique unique : imposé (EPSG:2154 pour la métropole) ou UTM estimé, auquel cas c'est signalé. Le
CRS d'origine est conservé dans le registre, et chaque mesure porte son CRS de calcul.

**Une intersection avec une zone inondable signifie-t-elle un risque ?**
Non. Le rapport le dit explicitement. Il faut d'abord vérifier la définition de la couche, sa date,
son échelle et son statut : la couche de démonstration est « provisoire », date de 2019 et a été
saisie au 1/25 000, et ces trois points sont signalés.

**Quelle est la fiabilité du système ?**
Je ne donne pas de pourcentage. J'ai défini des mesures (traçabilité, précision et rappel SIG,
exactitude des mesures, rappel documentaire), que j'ai exécutées sur 6 cas fictifs : tous réussissent.
Cela valide les garde-fous, pas la performance sur données réelles. J'ai aussi mesuré une limite :
3 extraits documentaires sur 7 sont peu informatifs.

**Pourquoi pas LangChain, LangGraph ou CrewAI ?**
Cinq étapes dans un ordre fixe n'en ont pas besoin. Une orchestration explicite en Python est plus
facile à tester et à auditer. Un framework se justifierait avec des branchements dynamiques ou de
nombreux outils.

**Comment passer en production ?**
Il faudrait :
- des données réelles, avec leurs métadonnées officielles (ISO 19115) ;
- une API FastAPI et une authentification ;
- une recherche hybride évaluée sur un corpus réel ;
- une évaluation avec un vrai LLM et un suivi des coûts ;
- une revue métier des phrases d'interprétation par des ingénieurs.

## 5. Limites à annoncer soi-même

- Les données sont fictives, et le mode LLM n'a pas été testé contre l'API réelle.
- La recherche documentaire est lexicale et ne lit pas les PDF scannés.
- Les contrôles de langage et de chiffres reposent sur des règles, qui ont des angles morts
  documentés.

Voir [limitations.md](limitations.md) et [security.md](security.md).
