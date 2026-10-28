import json,sys
from pathlib import Path
sys.path.insert(0,'container');from fact_check import plain
for x in json.loads(Path('artifacts/flash-facts/after.json').read_text(encoding='utf-8')):
 a=x.get('article')
 if not a:continue
 for f in a['fact_check']['findings']:
  txt=plain(a['content']) if f['field']=='content' else a['summary'] if f['field']=='summary' else a['title'];print(x['region_code'],repr(txt[max(0,f['start']-65):f['end']+80]))
