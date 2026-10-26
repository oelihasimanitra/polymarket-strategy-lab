# Coordination des agents

| ID | Agent | Responsabilité | Périmètre principal |
|---|---|---|---|
| A0 | Architecte / intégrateur | Contrats, décisions, structure et interfaces | `contracts/`, `schemas/`, `DECISIONS.md`, `ARCHITECTURE.md` |
| A1 | Collecte & stockage | Données publiques, normalisation, qualité, stockage | `src/polymarket_lab/collectors/`, `normalization/`, `storage/` |
| A2 | Simulation & ledger | Exécution taker, profondeur, latence, frais, portefeuille | `src/polymarket_lab/simulation/`, `ledger/` |
| A3 | Recherche & stratégies | Analyse des traders, hypothèses testables, stratégies versionnées | `src/polymarket_lab/analytics/`, `strategies/` |
| A4 | Dashboard | Visualisation locale en lecture seule | `src/polymarket_lab/dashboard/` |
| A5 | Validation & benchmark | Tests indépendants, métriques, benchmarks et audit de biais | `tests/`, `src/polymarket_lab/validation/`, `benchmarks/` |

## Ordre de lancement
1. Lancer A0 seul et valider contrats / interfaces.
2. Après validation, A1 et A2 travaillent en parallèle sur les contrats gelés.
3. A3 définit le format d'hypothèse et des règles testables.
4. A5 construit tests de contrat et audit indépendant.
5. A4 commence avec fixtures synthétiques, puis branche les services validés.

## Règles
- Une tâche explicite et un ensemble de fichiers autorisés par agent.
- Une branche Git ou un worktree par agent si possible.
- Pas de refactor global sans accord d'A0.
- Ne pas modifier en parallèle les mêmes fichiers.
- Les changements de contrat nécessitent revue, tests et note de migration.
- Le propriétaire du projet décide des traders, hypothèses, seuils de risque et changements de périmètre.

## Rapport de fin de session
Résumé ; fichiers modifiés ; commandes et résultats exacts des tests ; hypothèses ; risques/blocages ; dépendances ; prochaine étape.
