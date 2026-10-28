export interface Env {
 AIGC_API_KEY?:string;
 SERPER_API_KEYS?:string;
 APIFY_TOKEN?:string; COLLECTOR:DurableObjectNamespace;
 DB:D1Database; TEST_DB:D1Database; ARCHIVE:R2Bucket; ASSETS:Fetcher; COORDINATOR:DurableObjectNamespace;
 WRITER:DurableObjectNamespace; PIPELINE:Workflow;
 RADAR_INGEST_TOKEN?:string; SIGNAL_INGEST_TOKEN?:string; DEEPSEEK_API_KEY?:string; CONTENT_INGEST_TOKEN?:string;
 REVIEW_HOST:string; INGEST_HOST:string; DAILY_SUBMISSION_LIMIT:string; DAILY_GENERATION_LIMIT:string; DEFAULT_REVIEWER:string;
 WRITER_MODEL?:string; DEEPSEEK_MODEL:string; SUBMISSION_MODE:string; TEST_MODE?:string; WRITER_READY:string;
}
