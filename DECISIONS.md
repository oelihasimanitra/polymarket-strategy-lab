# Journal des décisions

Les décisions PROPOSÉES restent à valider par le propriétaire.

## D-001 — Périmètre initial — VALIDÉ
Trois traders, marchés crypto à court terme, Windows local, paper trading, capital virtuel de 100 à 10 000 USD/USDC. Aucun ordre réel en V1.

## D-002 — Types d'ordres — VALIDÉ
Taker uniquement en V1 ; maker reporté.

## D-003 — Stack — PROPOSÉ
Python modulaire, SQLite pour le prototype, Streamlit + Plotly pour le dashboard. A0 doit vérifier l'adéquation.

## D-004 — Devise comptable — À CONFIRMER
Ne jamais convertir silencieusement. Conserver la devise d'origine de chaque montant.

## D-005 — Carnet historique — À CONFIRMER
Ne pas revendiquer un backtest d'exécution fidèle si l'historique du carnet nécessaire n'est pas disponible.

## D-006 — Frais — À CONFIRMER
Aucun taux universel codé en dur. Barème vérifié, sourcé et versionné.

## D-007 — Périodes — PROPOSÉ
Séparer chronologiquement recherche, validation et test final ; ne pas optimiser sur le test final.

## D-008 — Accès réseau — VALIDÉ
Interfaces publiques documentées seulement en V1 ; aucune clé d'ordre privé requise.
