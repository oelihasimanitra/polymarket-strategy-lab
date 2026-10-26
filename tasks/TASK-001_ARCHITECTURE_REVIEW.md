# TASK-001 — Revue des contrats et de l'architecture

**Agent :** A0 — **Priorité :** bloquante — **Statut :** prête à lancer.

## Objectif
Auditer les contrats, le schéma SQL et la structure de démarrage avant le développement parallèle.

## Fichiers autorisés
`contracts/`, `schemas/`, `DECISIONS.md`, `ARCHITECTURE.md`.

## Travail
1. Vérifier types, unités, identifiants, timestamps et champs optionnels.
2. Vérifier cohérence événements ↔ stockage ↔ simulation ↔ ledger ↔ dashboard.
3. Définir les interfaces minimales entre modules et fournir un exemple de payload.
4. Lister les champs externes à valider dans la documentation officielle Polymarket.
5. Documenter les décisions ouvertes sans choisir arbitrairement.

## Acceptation
Contrats cohérents ; source et réception séparées ; quantités/unités documentées ; SQL compatible ; interfaces avec exemples ; questions bloquantes et non bloquantes listées ; rapport final selon `COORDINATION.md`.

## Hors périmètre
Pas de collecteur réseau, simulateur complet, dashboard ou ordre réel.
