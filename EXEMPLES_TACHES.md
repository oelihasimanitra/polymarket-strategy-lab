# Tâches initiales

## TASK-001 — Revue des contrats (A0)
Auditer les schémas et interfaces avant tout développement parallèle. Vérifier types, unités, timestamps, champs optionnels, cohérence événements ↔ stockage ↔ fills ↔ dashboard. Documenter les décisions ouvertes. Pas de collecteur, simulateur ou UI à construire dans cette tâche.

## TASK-002 — Fixtures synthétiques (A1)
Créer des données explicitement fictives : un marché, deux snapshots, événements avec timestamps source/réception distincts, carnet périmé et profondeur faible. Aucun vrai trader ou identifiant présenté comme réel.

## TASK-003 — Moteur de carnet (A2)
Fonction pure d'exécution taker : achat consomme asks croissants, vente consomme bids décroissants, prix moyen pondéré correct, fills partiels, quantité restante, coûts et hypothèses enregistrés. Aucun réseau ni ordre réel.

## TASK-004 — Format d'hypothèse (A3)
Structurer observations, hypothèses, confiance, inconnues, biais, règles d'entrée/sortie/risque et test de réfutation.

## TASK-005 — Dashboard sur fixtures (A4)
Vue lecture seule, données fictives étiquetées, capital, PnL, drawdown, trades, coûts et qualité des données. Aucun bouton d'ordre.

## TASK-006 — Tests indépendants (A5)
Tests de contrat, anti-look-ahead, comptabilité, idempotence, benchmarks et rapport des biais.
