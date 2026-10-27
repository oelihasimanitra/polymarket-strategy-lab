# A1 — Collecte, normalisation et stockage

**Mission :** données publiques et stockage local fiable.

**Fichiers autorisés :** `src/polymarket_lab/core/`, `collectors/`, `normalization/`, `storage/`, `tests/unit/core/`, `tests/fixtures/raw/`, tests associés. D-017/D-027.

**Priorités :** commencer par fixtures et stockage ; vérifier les interfaces officielles avant réseau ; garder timestamps source/réception ; détecter doublons, trous, événements tardifs et déconnexions ; conserver une référence aux payloads bruts utiles.

**Contraintes :** interfaces publiques documentées seulement ; pas de clés privées ni ordres réels ; ne pas inventer les champs des API.

**Acceptation :** stockage idempotent, normalisation conforme aux contrats, état qualité explicite, tests de reprise/doublons/timestamps.
