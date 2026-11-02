
CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY,
    script_path TEXT NOT NULL,
    arguments_json TEXT NOT NULL DEFAULT '[]',

    mode TEXT NOT NULL
        CHECK (mode IN ('normal', 'detailed', 'deep')),

    pid INTEGER,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_ms INTEGER,

    status TEXT NOT NULL
        CHECK (status IN (
            'RUNNING',
            'COMPLETED',
            'FAILED',
            'TIMEOUT',
            'MEMORY_LIMIT',
            'CPU_LIMIT',
            'INTERRUPTED',
            'INTERNAL_ERROR'
        )),

    classification TEXT NOT NULL DEFAULT 'UNDETERMINED'
        CHECK (classification IN (
            'NORMAL',
            'WARNING',
            'CRITICAL',
            'UNDETERMINED'
        )),

    exit_code INTEGER,
    timeout_seconds INTEGER NOT NULL DEFAULT 120
        CHECK (timeout_seconds > 0),

    memory_limit_bytes INTEGER NOT NULL
        CHECK (memory_limit_bytes > 0),

    configuration_json TEXT NOT NULL DEFAULT '{}',
    error_summary TEXT,

    CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY,
    execution_id INTEGER NOT NULL,
    collected_at TEXT NOT NULL,
    elapsed_ms INTEGER NOT NULL
        CHECK (elapsed_ms >= 0),

    cpu_percent REAL
        CHECK (cpu_percent IS NULL OR cpu_percent >= 0),

    memory_rss_bytes INTEGER
        CHECK (memory_rss_bytes IS NULL OR memory_rss_bytes >= 0),

    memory_vms_bytes INTEGER
        CHECK (memory_vms_bytes IS NULL OR memory_vms_bytes >= 0),

    child_memory_rss_bytes INTEGER
        CHECK (
            child_memory_rss_bytes IS NULL
            OR child_memory_rss_bytes >= 0
        ),

    thread_count INTEGER
        CHECK (thread_count IS NULL OR thread_count >= 0),

    process_count INTEGER
        CHECK (process_count IS NULL OR process_count >= 0),

    FOREIGN KEY (execution_id)
        REFERENCES executions(id)
        ON DELETE CASCADE,

    UNIQUE (execution_id, elapsed_ms)
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY,
    execution_id INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,

    elapsed_ms INTEGER
        CHECK (elapsed_ms IS NULL OR elapsed_ms >= 0),

    level TEXT NOT NULL
        CHECK (level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR')),

    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY (execution_id)
        REFERENCES executions(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_samples_execution_elapsed
    ON samples(execution_id, elapsed_ms);

CREATE INDEX IF NOT EXISTS idx_logs_execution_recorded
    ON logs(execution_id, recorded_at);

CREATE INDEX IF NOT EXISTS idx_executions_started
    ON executions(started_at);
