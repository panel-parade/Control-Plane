-- Control Plane v1: Work Register schema (SQLite).
-- Status is never stored on a work item (ADR-003).

CREATE TABLE IF NOT EXISTS work_items (
    work_id        TEXT PRIMARY KEY NOT NULL CHECK (length(work_id) > 0),
    project_id     TEXT NOT NULL CHECK (length(project_id) > 0),
    assigned_to    TEXT,
    state          TEXT NOT NULL CHECK (state IN (
                       'Assigned', 'Active', 'Blocked',
                       'Claimed Complete', 'Complete', 'Archived')),
    done_criterion TEXT NOT NULL CHECK (length(trim(done_criterion)) > 0),
    block_reason   TEXT,
    required       INTEGER NOT NULL DEFAULT 0 CHECK (required IN (0, 1)),
    created_ts     TEXT NOT NULL,
    last_update_ts TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_work_items_assigned_to ON work_items (assigned_to);
CREATE INDEX IF NOT EXISTS idx_work_items_state ON work_items (state);
CREATE INDEX IF NOT EXISTS idx_work_items_project_id ON work_items (project_id);
CREATE INDEX IF NOT EXISTS idx_work_items_last_update_ts ON work_items (last_update_ts);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id    TEXT NOT NULL REFERENCES work_items (work_id),
    event_type TEXT NOT NULL CHECK (event_type IN (
                   'CREATE', 'ASSIGNMENT', 'TRANSITION', 'VERIFICATION_FAILURE')),
    old_state  TEXT,
    new_state  TEXT NOT NULL,
    actor      TEXT NOT NULL CHECK (length(actor) > 0),
    timestamp  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_log_work_id ON audit_log (work_id);

-- Audit log is append-only.
CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

-- evidence_ref is a list of evidence records per work item, in order of attachment.
-- Each record is linked to the audit entry that attached it and is append-only.
CREATE TABLE IF NOT EXISTS evidence_refs (
    work_id     TEXT NOT NULL REFERENCES work_items (work_id),
    seq         INTEGER NOT NULL CHECK (seq >= 1),
    audit_id    INTEGER NOT NULL REFERENCES audit_log (audit_id),
    evidence_id TEXT NOT NULL CHECK (length(trim(evidence_id)) > 0),
    PRIMARY KEY (work_id, seq)
);

CREATE TRIGGER IF NOT EXISTS evidence_refs_no_update
BEFORE UPDATE ON evidence_refs
BEGIN
    SELECT RAISE(ABORT, 'evidence_refs is append-only');
END;

CREATE TRIGGER IF NOT EXISTS evidence_refs_no_delete
BEFORE DELETE ON evidence_refs
BEGIN
    SELECT RAISE(ABORT, 'evidence_refs is append-only');
END;

-- Direct writes to state are prohibited: only the state machine may set it.
-- The state machine sets the session flag below inside its transaction.
CREATE TABLE IF NOT EXISTS register_guard (
    id     INTEGER PRIMARY KEY CHECK (id = 1),
    allow_state_write INTEGER NOT NULL DEFAULT 0 CHECK (allow_state_write IN (0, 1))
);

INSERT OR IGNORE INTO register_guard (id, allow_state_write) VALUES (1, 0);

CREATE TRIGGER IF NOT EXISTS work_items_state_guard
BEFORE UPDATE OF state ON work_items
WHEN (SELECT allow_state_write FROM register_guard WHERE id = 1) = 0
BEGIN
    SELECT RAISE(ABORT, 'direct state writes prohibited; use the state machine');
END;

-- Work items are never deleted (audit integrity).
CREATE TRIGGER IF NOT EXISTS work_items_no_delete
BEFORE DELETE ON work_items
BEGIN
    SELECT RAISE(ABORT, 'work items cannot be deleted');
END;

-- Observation Registry (Observation-Registry-Spec). Separate from the Work Register:
-- recording or resolving never changes work_items or audit_log.
CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY NOT NULL CHECK (length(observation_id) > 0),
    project_id     TEXT NOT NULL CHECK (length(project_id) > 0),
    work_id        TEXT REFERENCES work_items (work_id),
    kind           TEXT NOT NULL CHECK (kind IN (
                       'missing_artefact', 'duplicate_detected', 'stale_reference',
                       'verification_issue', 'reproduction_issue', 'spec_gap',
                       'decision', 'validation', 'policy', 'authority',
                       'ratification', 'strategic_direction')),
    detail         TEXT NOT NULL CHECK (length(trim(detail)) > 0),
    reference      TEXT,
    recorded_by    TEXT NOT NULL CHECK (length(recorded_by) > 0),
    recorded_ts    TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    resolved_by    TEXT,
    resolved_ts    TEXT,
    CHECK (
        (status = 'open' AND resolved_by IS NULL AND resolved_ts IS NULL)
        OR (status = 'resolved' AND resolved_by IS NOT NULL AND resolved_ts IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_observations_work_id ON observations (work_id);
CREATE INDEX IF NOT EXISTS idx_observations_project_id ON observations (project_id);
CREATE INDEX IF NOT EXISTS idx_observations_kind ON observations (kind);
CREATE INDEX IF NOT EXISTS idx_observations_status ON observations (status);

-- Observations are never deleted.
CREATE TRIGGER IF NOT EXISTS observations_no_delete
BEFORE DELETE ON observations
BEGIN
    SELECT RAISE(ABORT, 'observations cannot be deleted');
END;

-- The only permitted update is open -> resolved, which may change only
-- status, resolved_by and resolved_ts. Everything else is immutable.
CREATE TRIGGER IF NOT EXISTS observations_update_guard
BEFORE UPDATE ON observations
WHEN NOT (
    OLD.status = 'open' AND NEW.status = 'resolved'
    AND NEW.observation_id IS OLD.observation_id
    AND NEW.project_id IS OLD.project_id
    AND NEW.work_id IS OLD.work_id
    AND NEW.kind IS OLD.kind
    AND NEW.detail IS OLD.detail
    AND NEW.reference IS OLD.reference
    AND NEW.recorded_by IS OLD.recorded_by
    AND NEW.recorded_ts IS OLD.recorded_ts
)
BEGIN
    SELECT RAISE(ABORT, 'observations are append-only; only open -> resolved is permitted');
END;
