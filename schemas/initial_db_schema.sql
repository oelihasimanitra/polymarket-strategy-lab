-- Schéma logique initial SQLite ; à valider par A0 avant implémentation.
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS traders (
 trader_id TEXT PRIMARY KEY, display_name TEXT NOT NULL,
 public_identifier TEXT NOT NULL UNIQUE, category TEXT NOT NULL DEFAULT 'crypto',
 selection_notes TEXT, selected_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS markets (
 market_id TEXT PRIMARY KEY, condition_id TEXT, slug TEXT, question TEXT,
 category TEXT, end_time TEXT, status TEXT, metadata_json TEXT
);
CREATE TABLE IF NOT EXISTS market_events (
 event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, source TEXT NOT NULL,
 market_id TEXT, token_id TEXT, source_timestamp TEXT NOT NULL,
 received_timestamp TEXT NOT NULL, sequence_number TEXT, side TEXT, price REAL,
 size REAL, currency TEXT, payload_json TEXT NOT NULL,
 quality_flags_json TEXT NOT NULL DEFAULT '[]',
 FOREIGN KEY (market_id) REFERENCES markets(market_id)
);
CREATE INDEX IF NOT EXISTS idx_events_market_time ON market_events(market_id, source_timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type_time ON market_events(event_type, source_timestamp);
CREATE TABLE IF NOT EXISTS book_snapshots (
 snapshot_id TEXT PRIMARY KEY, market_id TEXT NOT NULL, token_id TEXT NOT NULL,
 source_timestamp TEXT NOT NULL, received_timestamp TEXT NOT NULL,
 bids_json TEXT NOT NULL, asks_json TEXT NOT NULL, is_stale INTEGER NOT NULL DEFAULT 0,
 quality_flags_json TEXT NOT NULL DEFAULT '[]',
 FOREIGN KEY (market_id) REFERENCES markets(market_id)
);
CREATE TABLE IF NOT EXISTS strategies (
 strategy_id TEXT NOT NULL, version TEXT NOT NULL, trader_id TEXT,
 hypothesis_json TEXT NOT NULL, config_json TEXT NOT NULL, status TEXT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(strategy_id, version),
 FOREIGN KEY (trader_id) REFERENCES traders(trader_id)
);
CREATE TABLE IF NOT EXISTS experiments (
 experiment_id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL, strategy_version TEXT NOT NULL,
 period_type TEXT NOT NULL CHECK(period_type IN ('research','validation','final_test','paper_live')),
 start_time TEXT NOT NULL, end_time TEXT, initial_capital REAL NOT NULL,
 currency TEXT NOT NULL, config_hash TEXT NOT NULL, code_version TEXT,
 data_quality_summary_json TEXT, status TEXT NOT NULL,
 FOREIGN KEY(strategy_id, strategy_version) REFERENCES strategies(strategy_id, version)
);
CREATE TABLE IF NOT EXISTS simulated_orders (
 order_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL, strategy_id TEXT NOT NULL,
 strategy_version TEXT NOT NULL, market_id TEXT NOT NULL, token_id TEXT NOT NULL,
 side TEXT NOT NULL CHECK(side IN ('BUY','SELL')), requested_size REAL NOT NULL,
 filled_size REAL NOT NULL DEFAULT 0, average_fill_price REAL, fee_amount REAL NOT NULL DEFAULT 0,
 status TEXT NOT NULL, decision_timestamp TEXT NOT NULL, simulated_arrival_timestamp TEXT,
 book_snapshot_id TEXT, assumptions_json TEXT NOT NULL,
 FOREIGN KEY(experiment_id) REFERENCES experiments(experiment_id),
 FOREIGN KEY(book_snapshot_id) REFERENCES book_snapshots(snapshot_id)
);
CREATE TABLE IF NOT EXISTS simulated_fills (
 fill_id TEXT PRIMARY KEY, order_id TEXT NOT NULL, level_index INTEGER NOT NULL,
 price REAL NOT NULL, size REAL NOT NULL, fee_amount REAL NOT NULL DEFAULT 0,
 currency TEXT NOT NULL, fill_timestamp TEXT NOT NULL,
 FOREIGN KEY(order_id) REFERENCES simulated_orders(order_id)
);
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
 snapshot_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL, timestamp TEXT NOT NULL,
 cash_balance REAL NOT NULL, positions_json TEXT NOT NULL, realized_pnl REAL NOT NULL,
 unrealized_pnl REAL NOT NULL, estimated_equity REAL NOT NULL, metrics_json TEXT NOT NULL DEFAULT '{}',
 FOREIGN KEY(experiment_id) REFERENCES experiments(experiment_id)
);
CREATE TABLE IF NOT EXISTS benchmark_runs (
 benchmark_run_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL, benchmark_type TEXT NOT NULL,
 config_json TEXT NOT NULL, metrics_json TEXT, status TEXT NOT NULL,
 FOREIGN KEY(experiment_id) REFERENCES experiments(experiment_id)
);
