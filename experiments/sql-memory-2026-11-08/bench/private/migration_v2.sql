
-- V2 changes instrumentation, not historical measurements. Existing tables survive.
CREATE TABLE execution_cells(cell_id INTEGER PRIMARY KEY, cell_key TEXT NOT NULL UNIQUE, service_id INTEGER NOT NULL REFERENCES services, pool_id INTEGER NOT NULL REFERENCES worker_pools, profile_id INTEGER NOT NULL REFERENCES policy_profiles, release_id INTEGER NOT NULL REFERENCES releases, effective_from_ms INTEGER NOT NULL, effective_to_ms INTEGER, CHECK(effective_to_ms IS NULL OR effective_to_ms>effective_from_ms));
CREATE TABLE outcome_events(outcome_id INTEGER PRIMARY KEY, operation_id INTEGER NOT NULL UNIQUE REFERENCES logical_operations, cell_id INTEGER NOT NULL REFERENCES execution_cells, completed_at_ms INTEGER NOT NULL, final_code_id INTEGER NOT NULL REFERENCES failure_codes, attempt_count INTEGER NOT NULL CHECK(attempt_count>=1), total_queue_ms INTEGER NOT NULL CHECK(total_queue_ms>=0), total_execution_ms INTEGER NOT NULL CHECK(total_execution_ms>=0), total_backoff_ms INTEGER NOT NULL CHECK(total_backoff_ms>=0));
CREATE INDEX outcomes_cell ON outcome_events(cell_id,operation_id);

-- Data and registry migration: see migrate() in generate.py.
