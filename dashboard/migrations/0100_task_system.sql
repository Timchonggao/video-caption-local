-- Current task-based schema; existing remote tables are untouched until an explicit migration.
CREATE TABLE IF NOT EXISTS cs_clips(version TEXT,id TEXT,data TEXT NOT NULL,PRIMARY KEY(version,id));
CREATE TABLE IF NOT EXISTS cs_tasks(version TEXT,task_id TEXT,clip_id TEXT,camera_id TEXT,media_id TEXT,data TEXT NOT NULL,PRIMARY KEY(version,task_id));
CREATE TABLE IF NOT EXISTS cs_samples(version TEXT,sample_id TEXT,annotation_json TEXT,inventory_json TEXT,PRIMARY KEY(version,sample_id));
CREATE TABLE IF NOT EXISTS cs_media(version TEXT,id TEXT,object_key TEXT,PRIMARY KEY(version,id));
CREATE TABLE IF NOT EXISTS cs_runs(id TEXT PRIMARY KEY,config TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cs_results(version TEXT,task_id TEXT,run_id TEXT,data TEXT NOT NULL,PRIMARY KEY(version,task_id,run_id));
CREATE TABLE IF NOT EXISTS cs_reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,version TEXT,task_id TEXT,clip_id TEXT,camera_id TEXT,target TEXT,run_id TEXT,reviewer TEXT,accuracy TEXT,omission TEXT,notes TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS cs_review_target ON cs_reviews(version,task_id,target,run_id);
CREATE TABLE IF NOT EXISTS cs_rate_limits(key TEXT PRIMARY KEY,count INTEGER,expires INTEGER);
CREATE TABLE IF NOT EXISTS cs_datasets(version TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,ready INTEGER NOT NULL DEFAULT 0);
