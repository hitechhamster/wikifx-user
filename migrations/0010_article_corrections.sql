CREATE TABLE IF NOT EXISTS article_corrections (
 item_id TEXT PRIMARY KEY,
 original_item_id TEXT NOT NULL,
 original_delivery_id TEXT NOT NULL UNIQUE,
 original_hub_id TEXT NOT NULL,
 external_id TEXT NOT NULL UNIQUE,
 release_confirmed INTEGER NOT NULL DEFAULT 0 CHECK(release_confirmed IN (0,1)),
 created_at TEXT NOT NULL
);
