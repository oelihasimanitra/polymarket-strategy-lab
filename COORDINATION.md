# Coordination des agents

| ID | Agent | Responsabilité | Périmètre principal |
|---|---|---|---|
| A0 | Architecte / intégrateur | Contrats, décisions, structure et interfaces | `contracts/`, `schemas/`, `DECISIONS.md`, `ARCHITECTURE.md` |
| A1 | Collecte & stockage | Données publiques, normalisation, qualité, stockage, `core/` | `src/polymarket_lab/core/`, `collectors/`, `normalization/`, `storage/`, `tests/unit/core/`, `tests/fixtures/raw/` |
| A2 | Simulation & ledger | Exécution taker, profondeur, latence, frais, portefeuille | `src/polymarket_lab/simulation/`, `ledger/`, `tests/unit/simulation/`, `tests/unit/ledger/` |
| A3 | Recherche & stratégies | Analyse des traders, hypothèses testables, stratégies versionnées | `src/polymarket_lab/analytics/`, `strategies/` |
| A4 | Dashboard | Visualisation locale en lecture seule | `src/polymarket_lab/dashboard/` |
| A5 | Validation & benchmark | Tests indépendants, métriques, benchmarks et audit de biais | `tests/labtest/`, `tests/integration/`, `tests/accounting/`, `tests/fixtures/canonical/`, `src/polymarket_lab/validation/`, `benchmarks/` |

## Ordre de lancement
1. Lancer A0 seul et valider contrats / interfaces.
2. Après validation, A1 et A2 travaillent en parallèle sur les contrats gelés.
3. A3 définit le format d'hypothèse et des règles testables.
4. A5 construit tests de contrat et audit indépendant.
5. A4 commence avec fixtures synthétiques, puis branche les services validés.

## Propriété des tests et fixtures (D-027)
- Chaque propriétaire de module écrit ses tests unitaires dans le sous-répertoire
  correspondant (`tests/unit/core/` A1, `tests/unit/simulation|ledger/` A2).
- A5 possède les tests indépendants (`labtest/`, `integration/`, `accounting/`)
  et les fixtures canoniques.
- A1 possède les fixtures brutes par source sous `tests/fixtures/raw/` ; toute
  modification d'une fixture partagée exige A5 + propriétaire.
- Aucun import de `tests/` depuis `src/`.

## Règles
- Une tâche explicite et un ensemble de fichiers autorisés par agent.
- Une branche Git ou un worktree par agent si possible.
- Pas de refactor global sans accord d'A0.
- Ne pas modifier en parallèle les mêmes fichiers.
- Les changements de contrat nécessitent revue, tests et note de migration.
- Le propriétaire du projet décide des traders, hypothèses, seuils de risque et changements de périmètre.

## Rapport de fin de session
Résumé ; fichiers modifiés ; commandes et résultats exacts des tests ; hypothèses ; risques/blocages ; dépendances ; prochaine étape.
