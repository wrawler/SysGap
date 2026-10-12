-- server/backend/db/schema.sql

CREATE TABLE IF NOT EXISTS cpus (
    id SERIAL PRIMARY KEY,
    brand TEXT,
    model TEXT,
    socket TEXT,
    core_count INT,
    single_core_score INT,      -- Added for bottleneck math
    multi_core_score INT,       -- Added for bottleneck math
    tdp_watts INT
);

CREATE TABLE IF NOT EXISTS gpus (
    id SERIAL PRIMARY KEY,
    brand TEXT,
    model TEXT,
    vram_gb INT,                -- Added: Critical for AI/Gaming checks
    perf_score_gaming INT,      -- Added: Normalized performance index
    tdp_watts INT,
    length_mm INT
);

CREATE TABLE IF NOT EXISTS reports (
    report_id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    system_summary JSON,
    telemetry JSON,
    diagnosis JSON
);