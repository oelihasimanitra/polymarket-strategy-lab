# Journal des décisions

Mise à jour : 2026-10-27 (consolidation A0, clôture B-04 et préparation P0).

Statuts :
- **VALIDÉ** : décision du propriétaire, applicable.
- **APPROUVÉ EN PRINCIPE** : accord du propriétaire du 2026-10-26 ; le gel
  formel des contrats reste à prononcer.
- **PROPOSÉ** : proposition A0, non applicable avant validation.
- **À CONFIRMER** : question ouverte, aucune valeur par défaut n'est supposée.
- **À FAIRE** : vérification documentaire ou action de mise en place.
- **PRÉPARÉ** : spécification/fichiers candidats écrits, non approuvés et non
  exécutés. Un statut PRÉPARÉ ne vaut ni validation ni autorisation d'exécuter
  une migration sur la base de travail.

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
Les contrats `1.1.0` et le schéma SQL `0.4` sont proposés au gel après
validation des critères d'acceptation de
`contracts/CONTRACT_FREEZE_PROPOSAL.md`.

**Mise à jour 2026-10-27** : le schéma passe de `0.2` à `0.3` après les
corrections de l'audit A5 (voir D-026). Le gel n'est pas prononcé.

**Conséquence** : aucun agent ne modifie une interface gelée sans nouvelle
version, test et note de migration.

### D-026 — Corrections SQL après audit A5 — PROPOSÉ, À APPROUVER
Le schéma `0.3` corrige les anomalies SQL bloquantes de l'audit A5 :

- append-only effectif sur `market_events` et ses sept tables de détail ;
- intégrité composite `(market_id, token_id)` sur les événements et les ordres ;
- `book_snapshot_event_id` vérifié comme snapshot du même marché et token ;
- `intent_id` persisté, unique par ordre, et cité par les estimations via une
  FK composite `(order_id, intent_id)` ;
- `schema_version` ajouté aux tables qui persistent un document versionné ;
- refus des fills sur un ordre non exécutable ;
- formats `accounting_unit`, `tx_hash`, SHA-256 et références de payload ;
- hashes de delta de carnet stockés et cohérents par événement ;
- conversion exigée quand l'actif de règlement diffère du collatéral ;
- `random_seed` cohérent avec le JSON d'hypothèses d'exécution.

**Décisions de conception à approuver :**

1. **Cardinalité V1** : une intention produit au plus un ordre ; l'ordre porte
   l'intention, y compris rejetée. Une intention ne peut pas être réutilisée.
   Cette règle interdit le fractionnement d'une intention en plusieurs ordres.
2. **Hashes de delta** : stockés sur chaque ligne de `book_delta_changes` et
   contraints identiques, plutôt que dans une table d'en-tête. C'est moins
   normalisé mais évite une table supplémentaire sans besoin applicatif
   démontré ; une migration vers une table d'en-tête reste possible.
3. **`schema_version` avec valeur par défaut `1.0.0`** : évite une migration
   immédiate des barèmes et expériences existants ; la colonne reste NOT NULL.
4. **A5-06 reste hors SQL/JSON Schema standard** : la comparaison de deux
   champs n'est pas exprimable en JSON Schema standard. A1/A2 doivent valider
   la chronologie avant insertion ; les deux tests restent `xfail` documentés,
   pas masqués. **Mise à jour A5-06 (D-050) :** une extension normative
   `x-polymarket-chronological-order` est déclarée dans les deux schémas et les
   deux tests sont devenus verts ; les validateurs standards ignorent
   l'extension, donc A1/A2 doivent toujours l'appliquer.
5. **A5-16 reste une barrière applicative** : le SQL ne peut pas imposer la
   somme nulle et les soldes non négatifs par contrainte déclarative simple
   sans modifier l'ordre des écritures. A2 doit consulter les vues d'audit.

**Conséquence** : ces corrections ne prononcent pas le gel. Elles doivent être
approuvées, puis A5 doit relancer la suite et A1/A2 accepter les règles
sémantiques §5.1 de `ARCHITECTURE.md`.

### D-027 — Propriété de core, des tests et des fixtures — APPROUVÉ EN PRINCIPE POUR PRÉPARATION (2026-10-27)
A1 possède `src/polymarket_lab/core/` et `tests/unit/core/` ; A2 possède
`tests/unit/simulation/` et `tests/unit/ledger/` ; A5 possède `tests/labtest/`,
`tests/integration/`, `tests/accounting/` et les fixtures canoniques. A1 possède
les fixtures brutes par source sous `tests/fixtures/raw/`. Aucun import de
`tests/` depuis `src/`. Les fixtures partagées exigent A5 + propriétaire.

**Conséquence** : `COORDINATION.md` et les fiches A1/A2/A5 doivent être mis à
jour avant tout code. Aucun fichier de production A1/A2 n'est modifié par A0.

### D-028 — Définitions canoniques de core — APPROUVÉ SOUS RÉSERVE (2026-10-27)
Définitions normatives de `to_micros`, `base_units_to_micros`,
`canonical_timestamp`, `deterministic_event_id`, `manifest_hash` et
`config_hash`. `to_micros` rejette les flottants et les précisions non
représentables ; `canonical_timestamp` exige un datetime UTC aware ;
`deterministic_event_id` utilise `evt_` + 32 hex SHA-256 et vérifie les
collisions ; `manifest_hash` retourne 64 hex ; `config_hash` retourne
`sha256:<64 hex>`.

**Réserve** : A1 doit valider les vecteurs, A2 relire `units.py`, A5 recalculer
indépendamment. Le détail est dans `ARCHITECTURE.md` §2.

### D-029 — Provenance de accounting_unit — APPROUVÉ EN PRINCIPE POUR PRÉPARATION (2026-10-27)
Sur un événement de marché, `accounting_unit` est l'unité du notionnel dérivé,
égale au collatéral du marché à la réception. Sur ordre, estimation, fill et
posting, elle doit être exactement celle de l'expérience. Aucune conversion
implicite ; le SQL 0.4 ajoute les triggers d'égalité.

### D-030 — Trades publics et traders inconnus — APPROUVÉ EN PRINCIPE POUR PRÉPARATION (2026-10-27)
`trade_events` stocke tous les prints publics des marchés observés, pas
seulement les trois traders. `trader_visibility` vaut `identified` ou
`unknown` ; `trader_id` est nul si inconnu. `trader_activity_events` exige un
trader enregistré. Aucun sentinel, aucune inférence.

### D-031 — Reconstruction du carnet — APPROUVÉ SOUS RÉSERVE (2026-10-27)
Vue décision en ordre de réception ; vue d'audit en ordre source. Snapshot
obligatoire avant delta ; séquence contiguë ou `GAP` ; hash source comparé
seulement si l'algorithme est connu ; hash interne séparé ; delta tardif non
rétroactif ; cutoff de réception. Un carnet dont l'ordre n'est pas établi est
`DEGRADED`, jamais présenté comme fiable. Q-010 reste ouverte.

### D-032 — Estimation et résultat rejeté missing_book — APPROUVÉ EN PRINCIPE POUR PRÉPARATION (2026-10-27)
`execution_estimate.order_id` est obligatoire. `execution_result.estimate` peut
être nul uniquement pour `rejected` + `missing_book`. Ajout des motifs
`incomplete_book` et `ambiguous_fee_schedule`. `accepted` reste un état d'ordre
intermédiaire, pas un résultat terminal. Aucun snapshot fictif.

### D-033 — Modèle de frais V1 — APPROUVÉ SOUS RÉSERVE (2026-10-27)
Formules autorisées : `none`, `linear_min_price_1mp`, `notional`. `per_share`
et `custom` sont suspendus. Frais prélevés uniquement en collatéral ;
`outcome_token` est suspendu. Arrondi une fois par fill, incrément explicite.
Sélection par spécificité, période d'effet et date de consultation antérieure à
la décision. `not_required` est retiré. Q-011 reste ouverte.

### D-034 — Comptabilité, coût moyen, valorisation et VOID — APPROUVÉ EN PRINCIPE POUR PRÉPARATION (2026-10-27)
Une transaction par fill, frais inclus. Aucune transaction `kind='fee'` séparée
avec `ref_type='fill'` n'est admise en V1. Coût moyen pondéré, frais en charge
séparée, PnL réalisé hors frais. Valorisation inconnue représentée par des
champs nuls avec `valuation_method='none'` et une table `position_valuations`.
Aucun règlement VOID sans règle officielle sourcée ; Q-012 reste ouverte.

### D-035 — Séparation fixtures / données réelles — APPROUVÉ EN PRINCIPE POUR PRÉPARATION (2026-10-27)
Base de test séparée ; `data_manifests.source_class` (`fixture`, `recorded`,
`live`) ; `final_test` interdit les fixtures. Fixtures versionnées sous
`tests/fixtures/`, payloads réels sous `data/raw/` non commités.

### D-036 — Version du normaliseur et remplacements — APPROUVÉ EN PRINCIPE POUR PRÉPARATION (2026-10-27)
`normalizer_version` obligatoire dans l'enveloppe 1.1.0. Table append-only
`event_replacements` ; le nouvel événement ne modifie jamais l'ancien. Vue
`v_current_market_events`.

### D-037 — Packaging et stratégie SQLite — APPROUVÉ SOUS RÉSERVE (2026-10-27)
`pyproject.toml`, versions épinglées, lock avec hashes, extras test/dashboard/
research. Python non élargi avant matrice de tests. SQLite : un seul service
écrivain, `BEGIN IMMEDIATE`, WAL, `foreign_keys=ON`,
`recursive_triggers=ON`, dashboard en lecture seule. `httpx` n'est pas retenu
tant qu'il n'est pas installé et validé ; `requests` reste le client V1.

### D-038 — Cohérence contrats/SQL/docs/tests — APPROUVÉ EN PRINCIPE POUR PRÉPARATION (2026-10-27)
Contrats `1.1.0`, migration SQL `0.4`, exemples/docs/tests alignés. Aucun gel.
Les écarts de version et les CHECK de format sont corrigés.

### D-039 — Hypothèses d'exécution V1 — APPROUVÉ SOUS RÉSERVE (2026-10-27)
Latence `fixed` ou `uniform` uniquement ; `normal` retiré. RNG déterministe par
sous-seed SHA-256 dépendant de `(master_seed, intent_id, purpose)`, indépendant
de Python. Haircut par niveau avec arrondi floor ; `max_depth_levels=null`
illimité ; âge vérifié à l'arrivée ; limite BUY = maximum, SELL = minimum.

### D-040 — Versionnement pré-gel et compatibilité 1.1.0 — APPROUVÉ (2026-10-27)
Pendant la phase pré-gel, les contrats ne sont pas des interfaces stables et
aucun consommateur externe ne les utilise. Une extension compatible reste une
version mineure. Une version mineure peut aussi contenir des changements
incompatibles, à condition qu'ils soient documentés, testés et accompagnés
d'une déclaration explicite de compatibilité. Après gel, la règle SemVer stricte
s'applique : ajout de champ optionnel = mineure ; changement de type, d'unité,
de sémantique, retrait d'énumération ou ajout de champ obligatoire = majeure.

Les contrats `1.1.0` ne sont **pas rétrocompatibles** avec `1.0.0` au sens de la
validation : les documents `1.0.0` restent des archives lisibles, mais ne
valident pas le schéma `1.1.0` et aucun producteur `1.0.0` n'est compatible
sans migration. Cette incompatibilité est assumée avant gel, sans consommateur
externe stable à la date du 2026-10-27. `strategy_hypothesis` reste `1.0.0`
parce que son contrat n'est pas modifié.

### D-041 — Clôture B-04 et fabrique de connexion — VALIDÉ (2026-10-27)
B-04 est clos : fabrique unique `open_connection`, vérification des pragmas
effectifs, WAL obligatoire pour toute écriture sur fichier, `transaction()` en
`BEGIN IMMEDIATE`, tests append-only et garde AST. À la clôture : 535 tests
réussis, 2 xfail A5-06. Aucun contrat JSON ni schéma SQL n'a été modifié pour
B-04. B-04 n'est rouvert qu'en cas de régression ou d'échec démontré.

### D-042 — Identité d'événement v2 — PRÉPARÉ (2026-10-27)
Formule `event-id/v2` : source, ancrage (`source_event_id` prioritaire, sinon
`raw_payload_sha256`), type, marché, token, `source_timestamp` et
`normalizer_version`. `event_identity_version='v2'` est obligatoire en 1.2.0.
Unicité par `(source, source_event_id, event_type, normalizer_version)` et
trois index de repli raw. Les lignes legacy v1/NULL ne sont ni recalculées ni
réécrites. Un reparse exige un bump de `normalizer_version`.

### D-043 — Canonical JSON, manifeste et config hash v2 — PRÉPARÉ (2026-10-27)
`canonical-json/v1` strict (UTF-8, clés triées/ASCII, entiers, refus
float/NaN/Infinity et clés dupliquées). `manifest/v2` couvre l'en-tête, les
`event_ids` triés et les `replacements` triés
`[old_event_id, new_event_id, visible_from]`. Le manifeste est scellé par
`manifest_seals` ; aucun manifeste n'est lisible sans seal valide.
`config/v2` stocke une projection immuable `experiment_config_json` incluant
`code_version` et `config_hash_version`, excluant
`config_hash/status/created_at/completed_at`. Les manifestes legacy portent
`legacy/v1` et ne sont jamais scellés rétroactivement.

### D-044 — RNG v2 et `intent_id` — PRÉPARÉ (2026-10-27)
`polymarket-lab/rng/v2` : sous-seed
`SHA-256(canonical_json([DOMAIN, master_seed, intent_id, purpose]))`, compteur
`u64`, rejet modulo, bornes inclusives, `span` dans `1..2^64`, purposes
`latency`/`control`, un tirage logique par couple. `fixed` ne tire pas et impose
un jitter nul. `intent_id` est dérivé de `(experiment_id, idempotency_key)`.
`rng/v1` reste archivé et testé.

### D-045 — Découpage des migrations P0 — PRÉPARÉ (2026-10-27)
`0005_p0_foundations.sql` (0.4 → 0.5) porte B-01/B-02/B-05 ;
`0006_p0_ledger.sql` (0.5 → 0.6) porte B-06. Le runner accepte un registre
`3→0004`, `4→0005`, `5→0006`, vérifie source, journal et cible, exige une
sauvegarde et restaure la base en cas d'échec. Les noms de sauvegarde sont
rendus uniques par suffixe si deux migrations tombent dans la même seconde.
La provenance d'une conversion exige une transaction de la même expérience,
`ref_type='market_resolution'`, `ref_id=resolution_event_id` et
`kind='settlement'` ; un ajustement seul est refusé. Aucune migration candidate
n'est exécutée sur la base de travail.

### D-046 — Monotonie des remplacements (C-01) — PRÉPARÉ (2026-10-27)
Pour `O→N`, `visible_from >= current_from(O)` et
`visible_from < min(visible_from des sortants de N)`. Les cycles sont refusés.
Les règles sont portées par des triggers SQL, pas seulement par l'API. Une
collision `INSERT OR REPLACE` est refusée par un trigger `BEFORE INSERT`, même
si `recursive_triggers` est désactivé. Le cas A→B à 3 s puis B→C à 2 s est
refusé ; A→B à 2 s puis B→C à 3 s est accepté.

### D-047 — Horloge de confiance (C-02) — PRÉPARÉ (2026-10-27)
`created_at` et `visible_from` sont générés par la couche de stockage via une
horloge UTC injectée (`storage.clock`). L'API d'écriture n'accepte pas
`visible_from`. SQL impose l'égalité
`visible_from = max(old.received, new.received, created_at)` et
`created_at >= max(old.received, new.received)`. Les dates legacy ne sont pas
fabriquées.

### D-048 — Scellement obligatoire (C-03) — PRÉPARÉ (2026-10-27)
Aucune lecture as-of d'un manifeste sans `manifest_seals` valide. Le seal exige
`manifest_hash = data_manifests.sha256`, des comptages égaux aux listes et
l'ensemble complet des remplacements. Les listes sont immuables après seal ; le
seal est append-only. Les collisions `INSERT OR REPLACE` sur les manifestes et
leurs listes sont refusées même avec `recursive_triggers` désactivé. Un
manifeste legacy n'est pas scellable rétroactivement.

### D-049 — Versionnement des candidats P0 — PRÉPARÉ (2026-10-27)
**Décision initiale, avant A5-06 :** les contrats `market_event`, `execution`
et `experiment` passent à `1.2.0` ; `fee_schedule` devait rester `1.1.0` et
`strategy_hypothesis` restait `1.0.0`. Le schéma SQL candidat était `0.5`,
puis `0.6`. Les versions `1.1.0`/`0.4` restent les références auditées et ne
sont pas modifiées en place. Le statut de ces candidats est PRÉPARÉ, pas gelé.

> **Mise à jour A5-06 (D-050) :** `fee_schedule` passe à `1.2.0` pour porter
> l'extension chronologique. La référence auditée `1.1.0` reste l'historique
> Git ; aucun document `1.1.0` n'est réécrit sous le même numéro.

### D-050 — Chronologie JSON/SQL (A5-06) — PRÉPARÉ (2026-10-27)
La règle existante du SQL est rendue explicite côté contrat :
`effective_to > effective_from` pour `fee_schedule` et
`period.end_time > period.start_time` pour `experiment`. Les bornes égales sont
refusées ; une fin nulle est admise ; une fin absente n'est admise que si le
champ n'est pas requis (`fee_schedule.effective_to`), tandis que
`experiment.period.end_time` reste requis mais peut être nul.

JSON Schema 2020-12 ne permet pas de comparer deux champs. Les schémas
déclarent l'extension `x-polymarket-chronological-order` et le validateur
consommateur **doit** l'appliquer ; un validateur standard l'ignore. Le point
d'entrée applicatif est
`src/polymarket_lab/validation/contracts.py::validate_contract` (schéma puis
extension) ; les tests sont dans `tests/unit/test_contract_validation.py` et
`tests/REPORT_A0_A5_06_FIX.md`.

`fee_schedule` passe de `1.1.0` à `1.2.0` pour ne pas modifier en place une
version auditée. `experiment` reste `1.2.0` (candidat non gelé). Cette décision
complète D-026 point 4 et D-049 ; elle ne prononce aucun gel.

### D-051 — Validation applicative et migration 0007 — PRÉPARÉ (2026-10-27)
`validate_contract(document, schema, schema_validator)` est le point d'entrée
commun : il applique le validateur JSON Schema fourni, puis
`chronology_errors`. Aucun consommateur ne doit utiliser un validateur standard
seul sur un schéma qui déclare l'extension.

La migration candidate `0007_contract_sql_alignment.sql` (0.6 → 0.7) aligne
SQLite sur le contrat : `research`, `validation` et `final_test` exigent
`end_time IS NOT NULL` ; `paper_live` peut rester ouverte ; une fin existante
reste strictement postérieure au début. Elle fixe aussi les défauts
`schema_version` à `1.2.0` sans réécrire les versions historiques. Le préflight
compte les lignes incompatibles et refuse la migration avant toute
reconstruction. Les migrations `0005`/`0006` ne sont pas modifiées.

Le validateur est un module applicatif, mais aucun writer d'expériences ou de
barèmes n'existe encore dans `src/` : le branchement à un point d'écriture réel
reste une obligation d'A1/A2 avant tout usage en production. Aucun gel.

### D-052 — Parcours commun d'écriture A1/A2 — PRÉPARÉ (2026-10-27)
`storage.contract_writer` expose `ContractSpec`, `write_experiment` et
`write_fee_schedule`. Le parcours impose, dans l'ordre : schéma JSON,
chronologie, version épinglée du contrat, contrôles métier documentés,
transaction SQLite, relecture et comparaison de la ligne persistée. Les erreurs
sont catégorisées (`schema`, `chronology`, `version`, `business`, `sql`,
`persistence`) et aucune ligne n'est écrite avant validation complète.

Le writer persiste explicitement `schema_version` et n'utilise pas les défauts
SQL. Il exige `period.end_time` pour `paper_live`, même nul, avant insertion.
Il ne met pas à jour les lignes historiques et ne remplace aucune version.
Le branchement à un writer A1/A2 réel reste à faire ; les `INSERT` SQL directs
peuvent encore contourner ce parcours. Voir `WRITER_INTEGRATION.md`.

Cette décision ne prononce aucun gel.

### D-053 — Durcissement du writer commun — PRÉPARÉ (2026-10-27) — partiellement remplacé par D-054
> **Note 2026-10-27 (post-audit A5).** Les mécanismes
> `ContractSpec.for_tests` et `allow_test_specs=True` décrits ci-dessous sont
> remplacés par le parcours séparé de D-054. Le reste (connexion, registre,
> erreurs, transactions) est conservé et renforcé.

Le writer exige une connexion issue d'`open_connection` : `foreign_keys=ON`,
`recursive_triggers=ON`, `isolation_level=None` et aucune transaction
appelante active. Ces propriétés sont vérifiées avant toute validation et ne
sont jamais modifiées implicitement.

Les schémas de production proviennent du registre
`validation/registry.py` (nom, version, SHA-256). `ContractSpec.from_approved`
charge le schéma approuvé ; `ContractSpec.for_tests` est explicite et refusé
par les writers sauf `allow_test_specs=True` réservé aux tests. Un schéma
falsifié, un `ContractSpec` mal formé et une exception du validateur sont
rejetés par des erreurs catégorisées, avec conservation de la cause.

La validation schéma/chronologie/version est centralisée dans
`validation/contracts.py::contract_issues`. Les erreurs sont distinguées :
`spec`, `approval`, `connection`, `schema`, `chronology`, `version`,
`business`, `validator`, `sql`, `persistence`.

Une baseline `schemas/migrations/SHA256SUMS` et un test vérifient l'identité
des migrations présentes. Elle ne remplace pas Git : tant que les migrations et
la baseline ne sont pas suivies par Git, la non-modification historique n'est
pas prouvée formellement.

Aucun gel n'est prononcé.

### D-054 — Approbation intrinsèque et contrôles SQLite — PRÉPARÉ (2026-10-27)
Le writer normal n'accepte plus ni schéma, ni validateur, ni
`allow_test_specs` de l'appelant. Il recharge le registre à chaque écriture,
vérifie le SHA-256 et la version, gèle profondément le schéma et construit un
`SystemSchemaValidator` interne. Le registre public est une vue en lecture
seule ; le writer consulte une donnée privée pour qu'une réassignation de la
vue publique ne change pas l'approbation. Le parcours de test est un module
distinct (`contract_writer_testing`) qui ne constitue pas une frontière de
sécurité contre du code Python arbitraire.

La connexion doit être exactement `sqlite3.Connection`, avec un `row_factory`
`None` ou `sqlite3.Row`, `foreign_keys=ON`, `recursive_triggers=ON`,
`ignore_check_constraints=OFF`, `isolation_level=None` et aucune transaction
active. Le writer ne modifie aucun pragma.

L'ordre de validation est schéma → chronologie → version. Une erreur
`schema_version` n'est classée `version` que si elle concerne le champ racine.
Un document sans `period` et sans `schema_version` produit d'abord une erreur
de schéma pour `period`.

`SystemSchemaValidator` est un sous-ensemble JSON Schema fail-closed. C'est un
candidat Option B, pas une décision de production : l'ajout de `jsonschema`
(Option A) ou l'adoption de ce validateur interne (Option B) reste une décision
du propriétaire. L'intégration A1/A2 en production reste bloquée tant que ce
choix n'est pas fait. Aucune dépendance de production n'a été modifiée.

La baseline `SHA256SUMS` identifie explicitement les migrations couvertes,
épingle l'empreinte du manifeste dans le test et distingue intégrité relative
et historique Git. Un acteur qui modifie migration, manifeste, test et
constante peut produire un état cohérent ; la preuve d'historique exige un
commit Git de référence conservé par le propriétaire.

Aucun gel n'est prononcé.

### D-055 — Levée des conditions A5-C2 du candidat — PRÉPARÉ (2026-10-27)
`SystemSchemaValidator` refuse explicitement `multipleOf` à la construction.
La sémantique décimale divergeait de `jsonschema` sur `0.3` et
`0.30000000000000004` avec `multipleOf: 0.1` ; aucun schéma approuvé n'utilise
ce mot-clé. Un futur contrat qui l'utilise est refusé comme inutilisable, pas
interprété partiellement.

Les `$ref` sont limitées aux pointeurs locaux `#/...`. À la construction, la
cible doit être un schéma objet valide ; les cibles non-schéma et les cycles de
références sont refusés. Le contrôle de profondeur à l'exécution reste une
défense secondaire. Ce choix est fail-closed et documenté comme un
sous-ensemble, pas comme JSON Schema complet.

La vérification finale d'approbation reste **dans** la transaction, après
`BEGIN IMMEDIATE` et juste avant l'INSERT. Ce comportement est correct : il
réduit la fenêtre entre la dernière relecture du fichier et l'insertion, et un
échec annule la transaction sans ligne. Il ne verrouille ni le fichier ni le
registre et ne constitue pas une garantie de concurrence. La documentation
décrit désormais exactement cet ordre.

Les tests couvrent `ContractSchemaUnreadableError`, `ContractSchemaMismatchError`,
les références valides/invalides/cycliques, `multipleOf` et la position de la
vérification finale. Aucune dépendance de production n'est modifiée et aucun
gel n'est prononcé.

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
Le schéma 0.4 ne supporte que `collateral` en V1 ; `outcome_token` est suspendu
avec Q-011. La règle réelle doit être vérifiée. L'arrondi exact reste à
documenter. Si un prélèvement en parts peut rendre une position négative (vente
totale), la règle officielle de conversion ou de rejet doit être documentée
avant d'activer ce mode.

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

### Q-010 — Sémantique des séquences et hashes de carnet
Quelle est la signification exacte de `sequence_number`, des hashes source et
de leur portée (par flux, par token, par côté) chez chaque source ? Tant que
ce n'est pas documenté, le reconstructeur marque l'état `DEGRADED` lorsqu'il ne
peut pas établir l'ordre ou vérifier le hash. Aucun carnet n'est présenté comme
fiable dans ce cas.

### Q-011 — Base des frais `per_share` et frais en parts
`rate_micros` est un taux (`1 000 000 = 100 %`) ; il ne peut pas servir à la
fois de taux et de montant par part. `per_share` et `outcome_token` sont
suspendus en V1. Toute réintroduction exige soit un champ
`fee_per_share_micros` ou `rate_basis`, soit une règle de conversion
collatéral → parts sourcée, datée et testée.

### Q-012 — Règlement VOID
Quelle règle officielle définit le payout d'un marché `VOID` (0, remboursement,
autre) et à quel moment ? Aucun règlement VOID n'est produit sans
`void_rule_ref` sourcé. Un événement VOID sans payout peut être stocké, mais
A2 ne doit pas écrire de transaction de settlement.
