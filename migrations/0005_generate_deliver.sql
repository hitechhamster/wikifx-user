CREATE TABLE review_pick_preferences(item_id TEXT PRIMARY KEY,picked INTEGER NOT NULL,updated_at TEXT NOT NULL);
ALTER TABLE submission_jobs ADD COLUMN generation_request_id TEXT;
CREATE TABLE generation_requests(id TEXT PRIMARY KEY,job_id TEXT,run_date TEXT NOT NULL,created_at TEXT NOT NULL);
INSERT OR IGNORE INTO generation_requests SELECT id,NULL,substr(created_at,1,10),created_at FROM review_ai_calls WHERE kind='article' AND COALESCE(error_code,'')!='CACHED_RESULT_REUSED';
CREATE TABLE delivery_jobs(id TEXT PRIMARY KEY,job_id TEXT NOT NULL,item_id TEXT NOT NULL,mode TEXT NOT NULL,external_id TEXT NOT NULL UNIQUE,run_date TEXT NOT NULL,reviewed_by TEXT NOT NULL,state TEXT NOT NULL,payload_key TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,http_status INTEGER,hub_id TEXT,error TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(job_id,mode));
UPDATE submission_jobs SET state='ready' WHERE state='dry_run';
