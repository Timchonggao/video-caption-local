-- Additive publication state and immutable per-result sampling evidence.
CREATE TABLE IF NOT EXISTS cs_dashboard(version TEXT PRIMARY KEY,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cs_sampling(version TEXT,run_id TEXT,task_id TEXT,result_id TEXT,input_id TEXT,data TEXT NOT NULL,PRIMARY KEY(version,run_id,task_id,result_id));
CREATE INDEX IF NOT EXISTS cs_sampling_input ON cs_sampling(version,run_id,task_id,input_id);
