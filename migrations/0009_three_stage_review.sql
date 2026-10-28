ALTER TABLE content_items ADD COLUMN review_state TEXT NOT NULL DEFAULT 'candidate' CHECK(review_state IN ('candidate','generating','draft','approved','sending','sent','failed'));
ALTER TABLE submission_jobs ADD COLUMN approved_generation_id TEXT;
ALTER TABLE submission_jobs ADD COLUMN approved_by TEXT;
ALTER TABLE submission_jobs ADD COLUMN approved_at TEXT;
UPDATE content_items SET review_state=CASE
 WHEN EXISTS(SELECT 1 FROM delivery_jobs d WHERE d.item_id=content_items.id AND d.mode='live' AND d.state='sent') THEN 'sent'
 WHEN EXISTS(SELECT 1 FROM delivery_jobs d WHERE d.item_id=content_items.id AND d.mode='live' AND d.state IN ('queued','sending')) THEN 'sending'
 WHEN EXISTS(SELECT 1 FROM delivery_jobs d WHERE d.item_id=content_items.id AND d.mode='live' AND d.state='failed') THEN 'failed'
 WHEN EXISTS(SELECT 1 FROM submission_jobs j WHERE j.item_id=content_items.id AND j.state IN ('queued','writing')) THEN 'generating'
 WHEN EXISTS(SELECT 1 FROM submission_jobs j WHERE j.item_id=content_items.id AND j.payload_key IS NOT NULL) THEN 'draft'
 WHEN EXISTS(SELECT 1 FROM submission_jobs j WHERE j.item_id=content_items.id AND j.state='failed') THEN 'failed'
 ELSE 'candidate' END WHERE status!='legacy_hot';
UPDATE submission_jobs SET state='draft',approved_generation_id=NULL,approved_by=NULL,approved_at=NULL WHERE item_id IN(SELECT id FROM content_items WHERE review_state='draft');
DELETE FROM review_picks;
DELETE FROM review_pick_preferences;
UPDATE region_reviews SET locked=0 WHERE status!='skipped';
