"""Deterministic editorial checks across the ten publishing languages."""
import re
from fact_check import plain
PATTERNS={
 'zh':r'素材|资料|資料|搜索结果|搜尋結果|来源局限|來源局限|未确认|未確認|未提及|现有信息不包括|現有資訊不包括|仍需核实原文|仍需核實原文|已确认与未确认|已確認與未確認|给读者的说明|給讀者的說明|可用信息|可用范围|可用範圍|片段',
 'en':r'not (?:been )?(?:independently )?(?:established|confirmed|verified)|not mentioned|available (?:material|information|sources?|evidence)|snippets?|what is not (?:established|confirmed)|(?:source|material|coverage) limitations?|search results?|provided material|(?:report|source) does not (?:mention|specify|include|detail)|unconfirmed information|note to (?:the )?readers|could not be (?:confirmed|verified)',
 'ja':r'本稿の(?:描く|構成|説明)|スニペット|素材|提供された資料|資料の(?:限界|不足)|確認されていない|確認できていない|未確認|言及されていない|記載されていない|読者への説明|検索結果',
 'ko':r'스니펫|입력된 자료|제공된 자료|확인되지 않(?:은|았)|언급되지 않|자료(?:의 한계|가 부족)|검색 결과|독자에게 드리는 설명',
 'id':r'belum (?:dapat )?dikonfirmasi|tidak tercantum dalam materi|materi yang tersedia|informasi yang tersedia|cuplikan|hasil pencarian|tidak disebutkan|keterbatasan sumber|apa yang belum',
 'th':r'ยังไม่ได้รับการยืนยัน|ข้อมูลที่มีอยู่|ผลการค้นหา|ข้อจำกัดของแหล่งข้อมูล|ไม่ได้ระบุไว้|สิ่งที่ยังไม่ยืนยัน',
 'vi':r'chưa được xác nhận|tài liệu (?:được cung cấp|hiện có)|thông tin hiện có|kết quả tìm kiếm|đoạn trích|không được đề cập|giới hạn của nguồn',
 'pt':r'não está confirmado|não foi confirmado|material disponível|informações disponíveis|não é mencionado|não foi mencionado|trecho fornecido|resultados de busca|limitações d[ao]s? fontes',
 'es':r'no se detalla|no está confirmado|no se ha confirmado|material disponible|información disponible|no se menciona|fragmento proporcionado|resultados de búsqueda|limitaciones de las fuentes',
 'ar':r'لم يتضمن|لم تتضمن|ما لا تتضمنه|غير مؤكد|لم يتم تأكيد|لم يذكر|المواد المتاحة|المعلومات المتاحة|نتائج البحث|مقتطف|حدود المصادر'
}
def editorial_checks(content,title='',summary=''):
 issues=[]
 for field,text in [('title',title),('summary',summary),('content',plain(content))]:
  for language,pattern in PATTERNS.items():
   for m in re.finditer(pattern,text,re.I):issues.append({'field':field,'start':m.start(),'end':m.end(),'text':m[0],'kind':'meta_narration','language':language,'reason':'禁止元叙述'})
  for m in re.finditer(r'#{2,}|\*\*|```|\[[^\]]+\]\(https?://|(?:^|\n)\s*- ',text):issues.append({'field':field,'start':m.start(),'end':m.end(),'text':m[0],'kind':'markdown','reason':'Markdown 残留'})
 for m in re.finditer(r'<(?:h[1-6]|p)[^>]*>\s*(?:<strong>)?\s*(?:Sources?|References?|来源|來源|出典|Sumber)\s*(?:</strong>)?\s*</(?:h[1-6]|p)>',content,re.I):issues.append({'field':'content','text':plain(m[0]),'kind':'source_list','reason':'模型生成了来源列表'})
 return {'count':len(issues),'meta_count':sum(x['kind']=='meta_narration' for x in issues),'markdown_count':sum(x['kind']=='markdown' for x in issues),'issues':issues,'review_alert':bool(issues),'version':'multilingual-v1'}
