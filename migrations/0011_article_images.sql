CREATE TABLE article_images (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL, generation_id TEXT NOT NULL,
 version INTEGER NOT NULL, trigger_key TEXT NOT NULL, client_request_id TEXT NOT NULL UNIQUE,
 state TEXT NOT NULL DEFAULT 'queued', task_id TEXT, original_key TEXT, thumbnail_key TEXT,
 original_size INTEGER, mime_type TEXT, error TEXT, created_at TEXT NOT NULL,
 started_at TEXT, finished_at TEXT,
 UNIQUE(job_id,version), UNIQUE(job_id,generation_id,trigger_key)
);
CREATE INDEX article_images_queue ON article_images(state,created_at);
