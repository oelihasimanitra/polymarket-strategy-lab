# Journal des décisions

Mise à jour : 2026-10-26 (revue A0 — TASK-001).

Statuts :
- **VALIDÉ** : décision du propriétaire, applicable.
- **APPROUVÉ EN PRINCIPE** : accord du propriétaire du 2026-10-26 ; le gel
  formel des contrats reste à prononcer.
- **PROPOSÉ** : proposition A0, non applicable avant validation.
- **À CONFIRMER** : question ouverte, aucune valeur par défaut n'est supposée.
- **À FAIRE** : vérification documentaire ou action de mise en place.

Les décisions APPROUVÉES EN PRINCIPE ne sont pas encore un gel : elles
autorisent la préparation, pas la modification unilatérale des interfaces.
A0 n'a exécuté aucun test réseau ; les vérifications documentaires rapportées
par le propriétaire sont identifiées comme telles.

## Décisions existantes

### D-001 — Périmètre initial — VALIDÉ
Trois traders, marchés crypto à court terme, Windows local, paper trading,
capital virtuel de 100 à 10 000 USD/USDC. Aucun ordre réel en V1.

### D-002 — Types d'ordres — VALIDÉ
Taker uniquement en V1 ; maker reporté.

### D-003 — Stack — PROPOSÉ
Python modulaire, SQLite pour le prototype, Streamlit + Plotly pour le dashboard.

**Avis A0 (2026-10-26)** : SQLite est adapté à la V1 si le mode WAL est activé,
avec un seul écrivain et des lecteurs concurrents. PostgreSQL/TimescaleDB n'est
pas justifié à ce stade. Voir D-014. Le statut reste PROPOSÉ.

### D-004 — Devise comptable — À CONFIRMER
Ne jamais convertir silencieusement. Conserver la devise d'origine de chaque
montant.

**Note A0 (mise à jour 2026-10-26)** : le schéma 0.2 distingue désormais
l'actif de collatéral, l'unité comptable, l'actif de règlement et la devise de
présentation (voir D-022). Aucune devise par défaut. Une expérience impliquant
deux unités est invalide sans règle de conversion explicite, datée et testée.
Selon la vérification documentaire du propriétaire, pUSD est présenté comme
collatéral et le protocole règle en USDC natif ; chaque marché doit confirmer
ces deux points.

### D-005 — Carnet historique — À CONFIRMER
Ne pas revendiquer un backtest d'exécution fidèle si l'historique du carnet
nécessaire n'est pas disponible.

**Note A0** : tant que ce point n'est pas résolu, A2 ne doit produire que des
estimations d'exécution étiquetées comme telles, avec une référence de snapshot
et une incertitude. Aucun rapport ne doit parler de « backtest fidèle ».
Voir D-023 : un historique de prix ne permet pas de reconstituer la profondeur.

### D-006 — Frais — À CONFIRMER
Aucun taux universel codé en dur. Barème vérifié, sourcé et versionné.

**Note A0** : couvert structurellement par D-013. Les contrats ne contiennent
aucun taux ; l'exemple `fee_fixture_001` est explicitement fictif et marqué
`unverified`. Un taux de catégorie ou global n'est pas une preuve qu'il
s'applique à un marché : un barème `verified` non spécifique doit citer un
`scope_evidence_ref`.

### D-007 — Périodes — PROPOSÉ
Séparer chronologiquement recherche, validation et test final ; ne pas optimiser
sur le test final.

**Note A0** : renforcé par D-012. Une expérience `final_test` sans manifeste de
données est refusée par le schéma.

### D-008 — Accès réseau — VALIDÉ
Interfaces publiques documentées seulement en V1 ; aucune clé d'ordre privé
requise.

## Propositions issues de la revue A0

### D-009 — Montants en entiers micro-unités — APPROUVÉ EN PRINCIPE (2026-10-26)
Tous les montants, prix, tailles et taux sont des entiers d'échelle 1e-6
(`*_micros`). Aucun `REAL` dans le grand livre, les fills, les ordres ou les
snapshots de portefeuille.

**Pourquoi** : les actifs à 6 décimales (USDC, et pUSD selon la documentation
actuelle) se représentent exactement en micro-unités ; les entiers rendent
l'addition, la réconciliation et l'idempotence exactes. Les flottants binaires
introduisent des écarts d'arrondi qui rendent les tests comptables fragiles.

**Conséquence** : contrats `1.0.0` et schéma SQL `0.2`. A1 et A2 ne peuvent pas
démarrer sur les interfaces concernées avant validation.

### D-010 — Contrat d'événement strict et typé — APPROUVÉ EN PRINCIPE (2026-10-26)
Enveloppe commune + un seul payload typé par `event_type`, `side` non ambigu
(`taker_side`, `book_side`, `side` d'activité), champs obligatoires par type,
timestamps UTC canoniques, `additionalProperties: false`.

**Pourquoi** : le contrat précédent acceptait un `book_snapshot` sans carnet, un
`trade` sans prix et une `trader_activity` sans trader ; les modules auraient
divergé.

**Conséquence** : A1 normalise selon `contracts/market_event.schema.json`.
Toute valeur externe inconnue devient `UNKNOWN` + flag, sans suppression.

### D-011 — Journal comptable en partie double — APPROUVÉ EN PRINCIPE (2026-10-26)
Le grand livre est un journal de transactions équilibrées (somme nulle), avec
postings `CASH`, `POSITION`, `FEES`, `REALIZED_PNL`, `CAPITAL`. Les fills et le
ledger sont immuables ; toute correction est un reversal.

**Pourquoi** : la réconciliation et l'absence de double comptage sont des
critères d'acceptation du projet. Un simple agrégat de cash + positions ne
permet pas de les tester sérieusement.

**Conséquence** : A2 implémente le ledger ; A5 teste la somme nulle, les
soldes et les reversals. Si le propriétaire refuse la partie double, il faut
définir un modèle de remplacement aussi testable avant A2.

### D-012 — Manifeste de données et cutoff de réception — APPROUVÉ EN PRINCIPE (2026-10-26)
Chaque expérience historique référence un manifeste : cutoff de
`received_timestamp`, filtres, nombre d'événements, SHA-256. Aucun événement
reçu après le cutoff n'est lisible.

**Pourquoi** : la reproductibilité et l'anti-look-ahead ne peuvent pas reposer
sur la seule discipline du code.

**Conséquence** : A1 fournit le manifeste ; A2 l'applique ; A5 teste qu'un
événement futur est invisible.

### D-013 — Barèmes de frais versionnés — APPROUVÉ EN PRINCIPE (2026-10-26)
Les frais sont des données, pas du code : table `fee_schedules`, source URL,
date de consultation, période d'effet, périmètre, formule, unité de prélèvement,
arrondi, statut `verified` / `provisional` / `unverified`.

**Pourquoi** : D-006 l'exige. Un fill sans barème référencé est rejeté ; un
barème non vérifié interdit de présenter un PnL net définitif. La formule peut
être documentée au niveau d'une catégorie, mais les **paramètres applicables**
doivent être vérifiés, datés et versionnés par marché.

**Conséquence** : A1 vérifie la documentation officielle et crée les barèmes
datés ; un barème `verified` de portée `global` ou `category` doit porter
`scope_evidence_ref` ; A2 refuse un fill sans barème ; A4 affiche le statut.

### D-014 — SQLite WAL en V1 — APPROUVÉ EN PRINCIPE (2026-10-26)
SQLite en mode WAL, `busy_timeout` raisonnable, un seul écrivain, lectures
concurrentes pour le dashboard. PostgreSQL reporté.

**Pourquoi** : le volume V1, les fixtures et le dashboard local ne justifient
pas une infrastructure serveur. Le mode WAL suffit si les écritures sont
sérialisées.

**Conséquence** : A1 configure WAL et les migrations ; A4 ouvre en lecture
seule. Un passage à PostgreSQL ne doit pas changer les contrats.

### D-015 — Déterminisme des scénarios d'exécution — APPROUVÉ EN PRINCIPE (2026-10-26)
Latence, jitter, haircut, profondeur et seed sont figés par expérience dans
`execution_assumptions`. Le générateur et son implémentation exacte sont
enregistrés. Aucun scénario « central » n'est présenté comme la vérité.

**Pourquoi** : deux runs avec le même code mais des tirages différents ne sont
pas comparables. Un seuil global dans un fichier de configuration ne suffit pas
à figer une expérience.

**Conséquence** : A2 utilise le seed de l'expérience ; A5 rejoue et compare.

### D-016 — Ordre limite obligatoire — APPROUVÉ EN PRINCIPE (2026-10-26)
Même un ordre dit « market » porte un `limit_price_micros` explicite. Aucun
ordre sans borne de prix n'est simulé.

**Pourquoi** : sans borne, un carnet fin ou un haircut peut produire un
slippage arbitraire et un résultat non interprétable.

**Conséquence** : contrat `order_intent` et table `simulated_orders` imposent la
limite. Une stratégie qui veut un prix non borné doit écrire 0 ou 1 000 000.

### D-017 — Module partagé `core` — APPROUVÉ EN PRINCIPE (2026-10-26)
Créer `src/polymarket_lab/core/` pour les unités, les timestamps et les
identifiants déterministes. **Propriétaire désigné : A1.** A2 relit
obligatoirement `core/units.py` ; A5 teste les cas limites.

**Pourquoi** : A1 et A2 ont besoin des mêmes conversions Decimal → micros et de
la même formule d'`event_id`. Dupliquer ces fonctions crée des divergences.
A1 produit le premier les événements normalisés et les identifiants ; lui
confier le module évite un aller-retour de propriété.

**Conséquence** : A1 crée `core/units.py`, `core/time.py` et `core/ids.py`.
A2 ne réimplémente pas les conversions dans le ledger. Le prompt d'A1 et
`COORDINATION.md` doivent être mis à jour par le propriétaire pour inclure
`core/` dans le périmètre d'A1 ; A0 ne les modifie pas. Aucun agent ne crée ce
module en parallèle.

### D-018 — Packaging et dépendances verrouillées — APPROUVÉ EN PRINCIPE (2026-10-26)
Créer `pyproject.toml`, épingler les versions, ajouter `jsonschema` aux
dépendances de test, choisir un client HTTP compatible asyncio (`httpx` ou
`aiohttp`) ou documenter l'exécution de `requests` en thread.

**Pourquoi** : `requirements.txt` n'est pas épinglé et le projet n'est pas
installable comme package ; `requests` synchrone bloque une boucle asyncio.

**Conséquence** : action propriétaire ou tâche dédiée. Bloquant pour des tests
reproductibles en environnement propre, non bloquant pour les fixtures locales.

### D-019 — Vérifications Polymarket — PARTIELLEMENT VÉRIFIÉ (documentaire, 2026-10-26)
Avant toute collecte réseau et tout calcul de frais réel : vérifier et dater les
endpoints, champs, unités, sémantique de `side`, formats de carnet, barèmes de
frais, collatéral et règles de résolution. Checklist détaillée dans
`ARCHITECTURE.md`, section 16.

**Pourquoi** : aucun endpoint ni barème n'est affirmé sans source. Une fixture
ne prouve rien sur la production.

**Vérification documentaire du propriétaire (2026-10-26)** : les responsabilités
Gamma / CLOB / Data API / temps réel sont distinctes ; pUSD est présenté comme
collatéral et le protocole règle en USDC natif ; la formule de frais est
documentée, mais un taux de catégorie ne prouve pas son application à un
marché ; un historique de prix ne donne pas la profondeur du carnet. A0 n'a pas
rejoué cette vérification et n'a exécuté aucun test réseau.

**Conséquence** : la collecte réseau reste désactivée jusqu'à ce qu'A1 documente
les endpoints, champs, unités et paramètres par marché. Les fixtures, le
stockage et la simulation sur données fictives peuvent avancer.

### D-020 — Métadonnées de marché historisées — APPROUVÉ EN PRINCIPE (2026-10-26)
Les métadonnées (tick size, taille minimale, statut, negRisk, devise) sont
historisées dans `market_metadata_events`. `markets` n'est qu'une projection du
dernier état. Une simulation utilise la métadonnée reçue avant l'instant de
décision, jamais la projection actuelle.

**Pourquoi** : un changement de tick size ou de statut ne doit pas réécrire le
passé ni produire un look-ahead.

**Conséquence** : A1 écrit l'historique ; A2 résout la métadonnée « as of » ;
A5 teste le cas d'un changement en cours d'expérience.

### D-021 — Responsabilités des sources de données — APPROUVÉ EN PRINCIPE (2026-10-26)
Quatre familles distinctes : `gamma_api` (métadonnées de marchés), `clob_api`
(carnet, prix, ordres/trades), `data_api` (activité publique des traders) et
`clob_ws` (flux temps réel). Champs **non interchangeables**.

**Pourquoi** : une même notion (prix, taille, statut) peut avoir des noms,
unités et sémantiques différents selon la source. Un mapping générique crée des
erreurs silencieuses.

**Conséquence** : un adaptateur et un normaliseur par source ; `source` est
obligatoire et énuméré dans le contrat ; `source_schema_version` est conservé ;
les payloads bruts sont gardés. Toute nouvelle source exige une nouvelle
version de contrat.

### D-022 — Actif de collatéral, unité comptable, actif de règlement — APPROUVÉ EN PRINCIPE (2026-10-26)
Trois notions distinctes, plus la devise de présentation :
- actif de collatéral du marché (`collateral_asset`, pUSD selon la doc actuelle) ;
- unité comptable du ledger (`accounting_unit`, une par expérience) ;
- actif de règlement (`settlement_asset`, USDC natif selon la doc actuelle) ;
- devise de présentation (`presentation_currency`, affichage seulement).

**Pourquoi** : la documentation actuelle présente pUSD comme collatéral et le
règlement du protocole en USDC natif. Supposer une conversion 1:1 serait une
erreur comptable.

**Conséquence** : le ledger ne mélange jamais deux unités ; une résolution qui
change d'actif porte une `conversion_rule` sourcée, datée et versionnée ; la
présentation ne réécrit jamais le ledger. Aucune fonction de transaction réelle
n'est développée.

### D-023 — Historique des prix ≠ historique des carnets — APPROUVÉ EN PRINCIPE (2026-10-26)
Un historique de prix ne contient pas la profondeur. Interdiction de
reconstituer une profondeur à partir des seuls prix.

**Pourquoi** : la simulation d'exécution exige des tailles par niveau ; les
déduire d'une série de prix serait une invention.

**Conséquence** : paper live enregistre localement snapshots, deltas, trades et
payloads bruts ; sans carnet historique, l'exécution reste une estimation
étiquetée. D-005 reste ouvert.

### D-024 — Résolution comme événement distinct — APPROUVÉ EN PRINCIPE (2026-10-26)
La résolution est un `market_resolution` avec statut, token gagnant, date,
source, actif de règlement, payout par part et règle de conversion éventuelle.

**Pourquoi** : le règlement n'est pas un trade et ne doit pas être déduit d'un
prix de carnet. Le ledger a besoin d'une écriture de settlement explicite.

**Conséquence** : A1 collecte et normalise la résolution ; A2 l'applique au
ledger ; A4 affiche séparément le PnL pré-résolution et le résultat de
règlement.

### D-025 — Proposition de gel des contrats — EN ATTENTE DE VALIDATION
Les contrats `1.0.0` et le schéma SQL `0.2` sont proposés au gel après
validation des critères d'acceptation de
`contracts/CONTRACT_FREEZE_PROPOSAL.md`.

**Conséquence** : aucun agent ne modifie une interface gelée sans nouvelle
version, test et note de migration.

## Questions ouvertes (non tranchées)

### Q-001 — Source de vérité des tokens et outcomes
Quelle interface fait foi pour la correspondance `market → tokens → outcome`
(Gamma, CLOB, Data API) ? Que faire en cas de divergence ? Aucune réponse
supposée.

**Note 2026-10-26** : les responsabilités des sources sont désormais distinguées
(D-021), mais la source canonique de la correspondance token/outcome reste à
documenter par A1 avec des exemples réels.

### Q-002 — Doublons inter-sources
Politique de déduplication entre REST, WebSocket et données historiques : sur
`tx_hash`, sur un identifiant de trade, ou signalement sans fusion ? Le schéma
signale mais ne tranche pas.

### Q-003 — Unité de prélèvement des frais
Les frais sont-ils prélevés en USDC, en parts, ou les deux selon le marché ?
Le schéma supporte `collateral` et `outcome_token`, mais la règle réelle doit
être vérifiée. L'arrondi exact reste à documenter. Si un prélèvement en parts
peut rendre une position négative (vente totale), la règle officielle de
conversion ou de rejet doit être documentée avant d'activer ce mode.

### Q-004 — Positions ouvertes en fin d'expérience
Une expérience historique doit-elle liquider les positions au dernier prix
exécutable, les laisser ouvertes, ou exiger une résolution ? Le schéma stocke
les deux états, mais la convention de rapport doit être choisie avant les
métriques finales.

### Q-005 — Manifeste en paper live
Un run `paper_live` démarre sans manifeste final. Quand et comment le manifeste
est-il figé (à l'arrêt, quotidiennement, à la première revue) ? Le schéma
autorise `NULL` uniquement pour `paper_live`.

### Q-006 — Rétention des payloads bruts
Combien de temps conserver les payloads bruts et les événements ? Le stockage
local et le `.gitignore` empêchent le commit, mais aucune politique de purge
n'est définie.

### Q-007 — Version Python supportée
Python 3.15.0 est installé localement. Quelle plage de versions le projet
supporte-t-il réellement, compte tenu des dépendances scientifiques ? À figer
dans `pyproject.toml`.

### Q-008 — Critères de sélection des trois traders
Les critères (performance, période, volume, visibilité maker/taker) sont une
décision du propriétaire et ne sont pas déduits des données.

### Q-009 — Conversion pUSD → USDC à la résolution
Quel taux, quelle source et quel moment de conversion s'appliquent lorsqu'un
marché collatéralisé en pUSD règle en USDC natif ? Le schéma exige une
`conversion_rule` si les actifs diffèrent, mais aucune valeur n'est supposée.
A1/A2 doivent documenter la règle officielle et la dater avant tout PnL net
définitif.
