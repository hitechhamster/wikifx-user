CREATE TABLE historical_records(source_table TEXT NOT NULL,source_id TEXT NOT NULL,row_json TEXT NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(source_table,source_id));
