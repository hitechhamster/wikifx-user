import json
from pathlib import Path
for x in json.loads(Path('artifacts/rerun-v6/after.json').read_text(encoding='utf-8')):
 a=x.get('article')
 if not a:continue
 for q in a['ai_review']['issues']:
  if q['category']=='meta_narration':print(x['region_code'],x['job_id'],q['quote'],q['reason'])
