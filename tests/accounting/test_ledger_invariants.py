"""Invariants comptables au niveau du schéma SQL.

Le SQL initial ne peut pas imposer « somme nulle par transaction » avec un
simple CHECK multi-lignes. Les tests vérifient donc deux choses :

1. les écritures valides produisent les agrégats attendus dans les vues ;
2. les écritures invalides restent détectables par les vues d'audit, et les
   triggers empêchent leur correction par UPDATE/DELETE.

Un test qui accepte une écriture invalide est une caractérisation explicite,
pas une validation du comportement.
"""

from __future__ import annotations

import sqlite3

import pytest

from labtest import sqlfixtures as fx


def _cash(db, experiment_id):
    row = db.execute(
        "SELECT cash_micros FROM v_experiment_cash WHERE experiment_id = ?",
        (experiment_id,),
    ).fetchone()
    return None if row is None else row[0]


def _position(db, experiment_id, token_id):
    return db.execute(
        "SELECT quantity_micros, remaining_cost_basis_micros "
        "FROM v_experiment_positions WHERE experiment_id = ? AND token_id = ?",
        (experiment_id, token_id),
    ).fetchone()


def _anomalies(db, transaction_id):
    return db.execute(
        "SELECT * FROM v_ledger_anomalies WHERE transaction_id = ?",
        (transaction_id,),
    ).fetchone()


def _sum_amounts(db, transaction_id):
    return db.execute(
        "SELECT COALESCE(SUM(amount_micros), 0) FROM ledger_postings "
        "WHERE transaction_id = ?",
        (transaction_id,),
    ).fetchone()[0]


def test_deposit_is_balanced_and_visible(db, seeded):
    fx.insert_ledger_transaction(
        db, "tx_deposit", fx.deposit_postings(), kind="deposit",
        ref_type="experiment", ref_id=seeded["experiment_id"],
    )
    assert _sum_amounts(db, "tx_deposit") == 0
    assert _cash(db, seeded["experiment_id"]) == 1_000_000_000
    assert _anomalies(db, "tx_deposit") is None


def test_buy_fill_updates_cash_position_and_fees(db, seeded):
    fx.insert_ledger_transaction(
        db, "tx_deposit", fx.deposit_postings(), kind="deposit",
        ref_type="experiment", ref_id=seeded["experiment_id"],
    )
    fx.insert_ledger_transaction(
        db, "tx_buy", fx.buy_postings(seeded["token_yes"]), kind="fill",
        ref_type="fill", ref_id="fill_fixture_001",
    )
    assert _sum_amounts(db, "tx_buy") == 0
    assert _cash(db, seeded["experiment_id"]) == 1_000_000_000 - 53_600_000 - 464_000
    position = _position(db, seeded["experiment_id"], seeded["token_yes"])
    assert position["quantity_micros"] == 100_000_000
    assert position["remaining_cost_basis_micros"] == 53_600_000
    assert _anomalies(db, "tx_buy") is None
    assert db.execute("SELECT COUNT(*) FROM v_negative_cash").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM v_position_anomalies").fetchone()[0] == 0


def test_sell_realizes_pnl_and_closes_position(db, seeded):
    fx.insert_ledger_transaction(
        db, "tx_deposit", fx.deposit_postings(), kind="deposit",
        ref_type="experiment", ref_id=seeded["experiment_id"],
    )
    fx.insert_ledger_transaction(
        db, "tx_buy", fx.buy_postings(seeded["token_yes"]), kind="fill",
        ref_type="fill", ref_id="fill_fixture_001",
    )
    fx.insert_ledger_transaction(
        db, "tx_sell", fx.sell_postings(seeded["token_yes"]), kind="fill",
        ref_type="fill", ref_id="fill_fixture_002",
    )
    assert _sum_amounts(db, "tx_sell") == 0
    assert _cash(db, seeded["experiment_id"]) == (
        1_000_000_000 - 53_600_000 - 464_000 + 60_000_000 - 400_000
    )
    assert _position(db, seeded["experiment_id"], seeded["token_yes"]) is None
    realized = db.execute(
        "SELECT COALESCE(SUM(amount_micros), 0) FROM ledger_postings "
        "WHERE account = 'REALIZED_PNL'"
    ).fetchone()[0]
    assert realized == -6_400_000
    assert _anomalies(db, "tx_sell") is None


def test_winning_settlement_pays_cash_and_closes_position(db, seeded):
    fx.insert_ledger_transaction(
        db, "tx_deposit", fx.deposit_postings(), kind="deposit",
        ref_type="experiment", ref_id=seeded["experiment_id"],
    )
    fx.insert_ledger_transaction(
        db, "tx_buy", fx.buy_postings(seeded["token_yes"]), kind="fill",
        ref_type="fill", ref_id="fill_fixture_001",
    )
    fx.insert_ledger_transaction(
        db, "tx_settle", fx.settlement_win_postings(seeded["token_yes"]),
        kind="settlement", ref_type="market_resolution",
        ref_id=seeded["resolution_event"],
    )
    assert _sum_amounts(db, "tx_settle") == 0
    assert _cash(db, seeded["experiment_id"]) == (
        1_000_000_000 - 53_600_000 - 464_000 + 100_000_000
    )
    assert _position(db, seeded["experiment_id"], seeded["token_yes"]) is None
    assert _anomalies(db, "tx_settle") is None


def test_losing_settlement_has_no_cash_and_records_loss(db, seeded):
    fx.insert_ledger_transaction(
        db, "tx_deposit", fx.deposit_postings(), kind="deposit",
        ref_type="experiment", ref_id=seeded["experiment_id"],
    )
    fx.insert_ledger_transaction(
        db, "tx_buy", fx.buy_postings(seeded["token_yes"]), kind="fill",
        ref_type="fill", ref_id="fill_fixture_001",
    )
    fx.insert_ledger_transaction(
        db, "tx_settle", fx.settlement_lose_postings(seeded["token_yes"]),
        kind="settlement", ref_type="market_resolution",
        ref_id=seeded["resolution_event"],
    )
    assert _sum_amounts(db, "tx_settle") == 0
    assert _cash(db, seeded["experiment_id"]) == 1_000_000_000 - 53_600_000 - 464_000
    assert _position(db, seeded["experiment_id"], seeded["token_yes"]) is None
    realized = db.execute(
        "SELECT COALESCE(SUM(amount_micros), 0) FROM ledger_postings "
        "WHERE account = 'REALIZED_PNL'"
    ).fetchone()[0]
    assert realized == 53_600_000
    assert _anomalies(db, "tx_settle") is None


def test_fee_in_outcome_token_reduces_position_without_cash_movement(db, seeded):
    """Couverture A5 conservée, mais différée par Q-011.

    Le scénario d'origine (frais prélevés en parts, position réduite, aucun
    mouvement de cash) n'est pas autorisé en V1 : `outcome_token` est suspendu.
    La règle D-034 impose aussi une seule transaction par fill, frais inclus.
    Ce test vérifie donc qu'une transaction `fee` séparée sur un fill est
    refusée ; le scénario complet sera réactivé si Q-011 est tranchée.
    """
    fx.insert_ledger_transaction(
        db, "tx_deposit", fx.deposit_postings(), kind="deposit",
        ref_type="experiment", ref_id=seeded["experiment_id"],
    )
    fx.insert_ledger_transaction(
        db, "tx_buy", fx.buy_postings(seeded["token_yes"]), kind="fill",
        ref_type="fill", ref_id="fill_fixture_001",
    )
    cash_before = _cash(db, seeded["experiment_id"])
    position_before = _position(db, seeded["experiment_id"], seeded["token_yes"])
    fee_in_parts = [
        {"account": "POSITION", "token_id": seeded["token_yes"],
         "amount_micros": -1_072_000, "quantity_micros": -2_000_000},
        {"account": "REALIZED_PNL", "amount_micros": 1_072_000},
    ]
    with pytest.raises(sqlite3.IntegrityError, match="frais.*fill"):
        fx.insert_ledger_transaction(
            db, "tx_fee_parts", fee_in_parts, kind="fee", ref_type="fill",
            ref_id="fill_fixture_003",
        )
    assert db.execute(
        "SELECT COUNT(*) FROM ledger_transactions WHERE transaction_id = 'tx_fee_parts'"
    ).fetchone()[0] == 0
    assert _cash(db, seeded["experiment_id"]) == cash_before
    assert tuple(position_before) == tuple(
        _position(db, seeded["experiment_id"], seeded["token_yes"])
    )


def test_reversal_restores_the_previous_state(db, seeded):
    fx.insert_ledger_transaction(
        db, "tx_deposit", fx.deposit_postings(), kind="deposit",
        ref_type="experiment", ref_id=seeded["experiment_id"],
    )
    buy = fx.buy_postings(seeded["token_yes"])
    fx.insert_ledger_transaction(
        db, "tx_buy", buy, kind="fill", ref_type="fill",
        ref_id="fill_fixture_001",
    )
    cash_after_buy = _cash(db, seeded["experiment_id"])
    fx.insert_ledger_transaction(
        db, "tx_reversal", fx.negate_postings(buy), kind="reversal",
        ref_type="fill", ref_id="fill_fixture_001",
        idempotency_key="idem:reversal:fill_fixture_001",
    )
    assert _sum_amounts(db, "tx_reversal") == 0
    assert _cash(db, seeded["experiment_id"]) == 1_000_000_000
    assert _position(db, seeded["experiment_id"], seeded["token_yes"]) is None
    assert _anomalies(db, "tx_reversal") is None
    assert cash_after_buy != 1_000_000_000


def test_unbalanced_transaction_is_accepted_but_flagged(db, seeded):
    """Caractérisation : la somme nulle n'est pas une contrainte SQL."""
    fx.insert_ledger_transaction(
        db, "tx_unbalanced",
        [
            {"account": "CASH", "amount_micros": 100},
            {"account": "CAPITAL", "amount_micros": -90},
        ],
        kind="adjustment", ref_type="manual", ref_id="manual_1",
    )
    anomaly = _anomalies(db, "tx_unbalanced")
    assert anomaly is not None
    assert anomaly["posting_count"] == 2
    assert anomaly["imbalance_micros"] == 10


def test_single_posting_transaction_is_flagged(db, seeded):
    fx.insert_ledger_transaction(
        db, "tx_single", [{"account": "CASH", "amount_micros": 100}],
        kind="adjustment", ref_type="manual", ref_id="manual_2",
    )
    anomaly = _anomalies(db, "tx_single")
    assert anomaly is not None
    assert anomaly["posting_count"] == 1


def test_negative_cash_is_accepted_but_flagged(db, seeded):
    """Caractérisation : CASH >= 0 n'est pas une contrainte SQL."""
    fx.insert_ledger_transaction(
        db, "tx_overdraft",
        [
            {"account": "POSITION", "token_id": seeded["token_yes"],
             "amount_micros": 200, "quantity_micros": 100},
            {"account": "CASH", "amount_micros": -200},
        ],
    )
    negative = db.execute(
        "SELECT cash_micros FROM v_negative_cash WHERE experiment_id = ?",
        (seeded["experiment_id"],),
    ).fetchone()
    assert negative is not None
    assert negative["cash_micros"] == -200


def test_negative_position_is_accepted_but_flagged(db, seeded):
    """Caractérisation : l'interdiction du short n'est pas une contrainte SQL."""
    fx.insert_ledger_transaction(
        db, "tx_short",
        [
            {"account": "POSITION", "token_id": seeded["token_yes"],
             "amount_micros": -100, "quantity_micros": -100},
            {"account": "CASH", "amount_micros": 100},
        ],
    )
    negative = db.execute(
        "SELECT quantity_micros FROM v_position_anomalies "
        "WHERE experiment_id = ? AND token_id = ?",
        (seeded["experiment_id"], seeded["token_yes"]),
    ).fetchone()
    assert negative is not None
    assert negative["quantity_micros"] == -100


def test_latest_snapshot_view_returns_most_recent(db, seeded):
    fx.insert_snapshot(
        db, seeded["experiment_id"], snapshot_id="snap_old",
        as_of_timestamp=fx.TS1, cash_micros=100, positions_value_micros=50,
    )
    fx.insert_snapshot(
        db, seeded["experiment_id"], snapshot_id="snap_new",
        as_of_timestamp=fx.TS2, cash_micros=200, positions_value_micros=25,
    )
    rows = db.execute(
        "SELECT snapshot_id, equity_micros FROM v_experiment_latest_snapshot "
        "WHERE experiment_id = ?",
        (seeded["experiment_id"],),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["snapshot_id"] == "snap_new"
    assert rows[0]["equity_micros"] == 225


def test_order_execution_view_computes_vwap_and_fees(db, seeded):
    row = db.execute(
        "SELECT * FROM v_order_execution WHERE order_id = ?",
        (seeded["order_id"],),
    ).fetchone()
    assert row["filled_size_micros"] == 100_000_000
    assert row["vwap_micros"] == 536_000
    assert row["fees_collateral_micros"] == 464_000
    assert row["fees_outcome_micros"] == 0
    assert row["fill_count"] == 2


def test_experiment_cash_view_is_zero_before_deposit(db, seeded):
    assert _cash(db, seeded["experiment_id"]) == 0
