# A2 — Simulation taker et ledger

**Mission :** moteur déterministe d'exécution simulée et portefeuille virtuel.

**Fichiers autorisés :** `src/polymarket_lab/simulation/`, `ledger/`, `tests/unit/simulation/`, `tests/unit/ledger/`, tests associés. D-027.

**Priorités :** fonction pure d'exécution depuis un carnet ; achat consomme asks croissants, vente bids décroissants ; prix moyen pondéré et fills partiels ; latence et vieillissement/haircut explicites ; frais configurables uniquement si barème vérifié ; grand livre réconciliable.

**Contraintes :** aucun réseau dans le calcul pur ; pas de PnL calculé par LLM ; pas de short implicite ; pas d'ordres réels ; éviter double comptage spread/slippage/profondeur.

**Acceptation :** tests multi-niveaux, liquidité insuffisante, frais, arrondis, cash/positions/PnL, limites et données périmées.
