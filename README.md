# Polymarket Strategy Research Lab

Laboratoire local de recherche sur la reproductibilité de stratégies observées chez trois traders Polymarket actifs sur les marchés crypto à court terme.

## Documents de cadrage
- `PROJECT_SPEC.md` — objectifs, périmètre et critères de réussite.
- `ARCHITECTURE.md` — modules, interfaces et stack.
- `SIMULATION_RULES.md` — règles de paper trading taker.
- `VALIDATION_PLAN.md` — validations technique, historique, en direct et benchmarks.
- `CAHIER_DES_CHARGES.pdf` — version lisible du cahier des charges général.

## Périmètre initial
- Windows local.
- 3 traders.
- Marchés crypto.
- Capital virtuel : 100 à 10 000 USD/USDC.
- Paper trading uniquement.
- Taker uniquement en V1.
- Benchmark indépendant.
- Dashboard local.

## État
Documents de cadrage v0.1. Aucun logiciel de trading n'est encore implémenté par ces documents.

## Démarrage recommandé
1. Lire le cahier des charges PDF.
2. Valider les documents Markdown.
3. Vérifier les interfaces et règles de frais dans la documentation officielle au moment du développement.
4. Créer le dépôt Git et les contrats de données.
5. Développer et tester le collecteur avant le moteur de simulation.
