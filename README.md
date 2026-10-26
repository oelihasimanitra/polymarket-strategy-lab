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

## Contrats et décisions
- `contracts/` — contrats JSON `1.0.0` (proposition, non gelés).
- `contracts/CONTRACT_FREEZE_PROPOSAL.md` — critères d'acceptation A1–A5 et proposition de gel.
- `schemas/initial_db_schema.sql` — schéma SQLite `0.2`.
- `DECISIONS.md` — décisions validées, approuvées en principe et questions ouvertes.

## État
Documents de cadrage v0.2 (revue A0 du 2026-10-26). Les contrats sont proposés, pas encore gelés. Aucun logiciel de trading n'est implémenté.

## Démarrage recommandé
1. Lire le cahier des charges PDF.
2. Valider les documents Markdown et la proposition de gel.
3. Vérifier les interfaces, les sources et les règles de frais dans la documentation officielle.
4. Laisser A5 commiter les tests de contrat et de schéma.
5. Développer les fixtures et le stockage avant la collecte réseau.

## Mise en place du dépôt (mémo)
```bash
git remote add origin https://github.com/oelihasimanitra/polymarket-strategy-lab.git
git branch -M main
git push -u origin main
```
