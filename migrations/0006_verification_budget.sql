CREATE TABLE verification_budgets(run_date TEXT NOT NULL,region_code TEXT NOT NULL,serper_calls INTEGER NOT NULL CHECK(serper_calls BETWEEN 0 AND 20),PRIMARY KEY(run_date,region_code));
CREATE TABLE rumor_verifications(item_id TEXT NOT NULL,revision INTEGER NOT NULL,run_date TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(item_id,revision,run_date));
