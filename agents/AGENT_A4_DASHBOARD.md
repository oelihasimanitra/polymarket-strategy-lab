# A4 — Dashboard local

**Mission :** interface de visualisation en lecture seule.

**Fichiers autorisés :** `src/polymarket_lab/dashboard/`, fixtures UI et tests.

**Vues minimales :** synthèse multi-bots ; capital/PnL/drawdown/trades ; positions ; historique ordres/fills/frais ; spread/profondeur/prix moyen simulé ; comparaison trader/bot/benchmark ; qualité des données, latence et erreurs.

**Contraintes :** bannière « PAPER TRADING — AUCUN ARGENT RÉEL » ; fixtures clairement fictives ; aucun endpoint/bouton d'ordre réel ; ne pas recalculer le PnL si le ledger le fournit.

**Acceptation :** fonctionne localement, affiche les données manquantes, métriques cohérentes et aucune exécution depuis l'interface.
