ALTER TABLE content_items ADD COLUMN appeal_score INTEGER CHECK(appeal_score BETWEEN 1 AND 5);
ALTER TABLE content_items ADD COLUMN reason_facts_json TEXT;
CREATE TABLE enrichment_runs(id TEXT PRIMARY KEY,item_id TEXT NOT NULL,revision INTEGER NOT NULL,reason TEXT NOT NULL,state TEXT NOT NULL,content_status TEXT,serper_calls INTEGER NOT NULL DEFAULT 0,fetch_attempts INTEGER NOT NULL DEFAULT 0,fetch_successes INTEGER NOT NULL DEFAULT 0,result_json TEXT,created_at TEXT NOT NULL,UNIQUE(item_id,revision));
