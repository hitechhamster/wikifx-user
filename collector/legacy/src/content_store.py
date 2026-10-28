"""Additive SQLite content library. No network calls; original reports are read-only."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BJ = ZoneInfo("Asia/Shanghai")
MARKETS = ("global", "india", "indonesia", "pakistan")
DATA = Path(__file__).resolve().parent.parent / "data"

def now_bj():
    return datetime.now(BJ).isoformat(timespec="seconds")

def timestamp(value, naive_tz=timezone.utc):
    if not value:
        return None
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=naive_tz)
    return dt.astimezone(BJ).isoformat(timespec="seconds")

def connect(data=DATA):
    db = sqlite3.connect(str(Path(data) / "signal.sqlite3"), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=15000")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS content_items (
      id TEXT PRIMARY KEY,
      market TEXT NOT NULL CHECK(market IN ('global','india','indonesia','pakistan')),
      title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
      url TEXT NOT NULL, source TEXT NOT NULL DEFAULT '', heat REAL NOT NULL DEFAULT 0,
      ai_rank INTEGER, ai_reason TEXT,
      status TEXT NOT NULL DEFAULT 'candidate' CHECK(status IN ('candidate','selected','published','failed','legacy_hot')),
      reviewed_by TEXT, reviewed_at TEXT, queued_at TEXT, published_at TEXT, publish_result TEXT,
      run_date TEXT NOT NULL, category TEXT, opportunity_score REAL NOT NULL DEFAULT 0,
      engagement_total TEXT NOT NULL DEFAULT '{}', lead_created_at TEXT,
      topic_key TEXT NOT NULL, article_path TEXT,
      dedup_key TEXT NOT NULL, provenance_json TEXT NOT NULL DEFAULT '{}',
      UNIQUE(market, dedup_key)
    );
    CREATE INDEX IF NOT EXISTS idx_content_market_date ON content_items(market,run_date);
    CREATE INDEX IF NOT EXISTS idx_content_status ON content_items(status,queued_at);
    CREATE INDEX IF NOT EXISTS idx_content_topic ON content_items(market,topic_key);
    """)
    return db

def upsert(db, topic, market, run_date, review=None, review_tz=timezone.utc, provenance=None):
    lead = topic.get("lead") or {}
    zh = (topic.get("i18n") or {}).get("zh") or {}
    title = zh.get("label") or topic.get("label") or lead.get("text") or lead.get("url") or "Untitled"
    url = lead.get("url") or ""
    key = url or f"rank-{topic.get('rank')}"
    # Original source title/text is stable when AI labels change on reruns.
    original_title = " ".join((lead.get("text") or title).split())
    digest = hashlib.sha256(json.dumps([url, original_title],ensure_ascii=False).encode()).hexdigest()
    item_id = hashlib.sha256((market+":"+digest).encode()).hexdigest()
    existing = db.execute("SELECT id FROM content_items WHERE market=? AND topic_key=?",(market,key)).fetchone()
    # A historical review can be matched by its stable legacy key even after a rerun.
    if existing and review:
        item_id = existing['id']
    else:
        db.execute("""INSERT INTO content_items
          (id,market,title,summary,url,source,heat,run_date,category,opportunity_score,
           engagement_total,lead_created_at,topic_key,dedup_key,provenance_json)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(market,dedup_key) DO UPDATE SET
          title=excluded.title,summary=excluded.summary,source=excluded.source,
          run_date=MAX(content_items.run_date,excluded.run_date),
          heat=excluded.heat,opportunity_score=excluded.opportunity_score,
          engagement_total=excluded.engagement_total,category=excluded.category
          """,(item_id,market,title,zh.get('summary') or lead.get('text',''),url,
          lead.get('news_source') or ':'.join(filter(None,[lead.get('platform'),lead.get('author')])),
          (topic.get('opportunity') or {}).get('score',0),run_date,
          (topic.get('category') or {}).get('id'),(topic.get('opportunity') or {}).get('score',0),
          json.dumps((topic.get('stats') or {}).get('engagement_total') or lead.get('engagement') or {}),
          timestamp(lead.get('created_at')),key,digest,json.dumps(provenance or {},ensure_ascii=False)))
    if review and review.get('decision') == 'hot':
        reviewed = timestamp(review.get('decided_at'),review_tz)
        article = review.get('article')
        article_path = str(Path('articles') / market / run_date / article) if article else None
        db.execute("""UPDATE content_items SET status=CASE WHEN status='candidate' OR (status='selected' AND reviewed_by='legacy-import') THEN 'legacy_hot' ELSE status END,
          reviewed_at=COALESCE(reviewed_at,?), queued_at=CASE WHEN status IN ('candidate','legacy_hot') OR (status='selected' AND reviewed_by='legacy-import') THEN NULL ELSE queued_at END,
          article_path=COALESCE(article_path,?), reviewed_by=COALESCE(reviewed_by,'legacy-import')
          WHERE id=?""",(reviewed,article_path,item_id))
    return item_id

def import_daily(data, date):
    data=Path(data);counts={}
    with connect(data) as db:
        for market in MARKETS:
            f=data/'daily'/market/(date+'.json')
            if not f.exists():continue
            payload=json.loads(f.read_text(encoding='utf-8'))
            generated=timestamp(payload.get('generated_at'))
            run_date=generated[:10] if generated else payload['date']
            for t in payload.get('topics',[]):
                upsert(db,t,market,run_date,provenance={'daily_file':str(f.relative_to(data))})
            counts[market]=len(payload.get('topics',[]))
    return counts

def import_reviews(data):
    data=Path(data);count=0;fallbacks=0
    with connect(data) as db:
        for f in sorted((data/'review').glob('*/*.json')):
            market=f.parent.name
            if market not in MARKETS:continue
            reviews=json.loads(f.read_text(encoding='utf-8'))
            daily=data/'daily'/market/f.name
            payload=json.loads(daily.read_text(encoding='utf-8')) if daily.exists() else {}
            topics={t.get('lead',{}).get('url') or f"rank-{t.get('rank')}":t for t in payload.get('topics',[])}
            generated=payload.get('generated_at')
            # Legacy timestamps are naive; use the corresponding report's timezone.
            tz=datetime.fromisoformat(generated).tzinfo if generated else timezone.utc
            tz=tz or timezone.utc
            for key,review in reviews.items():
                if review.get('decision')!='hot':continue
                t=topics.get(key)
                fallback=t is None
                if fallback:
                    fallbacks+=1
                    t={'label':review.get('article_title') or key,'lead':{'url':key,'text':review.get('article_title') or key}}
                upsert(db,t,market,f.stem,review,tz,{'review_file':str(f.relative_to(data)),'legacy_record':review,'missing_daily_topic':fallback,'naive_review_timezone':str(tz)})
                count+=1
    return {'hot_records':count,'missing_daily_topic':fallbacks}
