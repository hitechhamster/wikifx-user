from pathlib import Path
p=Path('container/fact_check.py');s=p.read_text(encoding='utf-8');s=s.replace('for a,b,kind,value in article_q:\n   checked','for a,b,kind,value in article_q:\n   if not re.search(r"\\d|[万萬亿億千百十兆]",text[a:b]):continue\n   checked');s=s.replace('for a,b,name in name_candidates(text):\n   if norm(name)', '''for a,b,name in name_candidates(text):
   if field=='summary':continue
   if field=='content' and any(a<y and b>x for x,y in heading_spans(content)):continue
   if norm(name) in COMMON_TERMS:continue
   if field=='title' and not (ORG.search(name) or any(norm(name)==norm(alias) for group in ALIASES for alias in group) or any(m.span(1)==(a,b) for m in ROLE.finditer(text))):continue
   if norm(name)''');s=s.replace("'deterministic-v2.1'","'deterministic-v3-low-false-positive'");insert='''
# Common financial vocabulary is exempt, not proof for any attributed claim.
COMMON_TERMS={norm(x) for x in [
 'Fed','FOMC','ECB','BoJ','Federal Reserve','Federal Open Market Committee','European Central Bank','Bank of Japan','Banco Central','Banco Central Europeu','Banco Central Europeo','Reserva Federal','Comitê Federal de Mercado Aberto','Comité Federal de Mercado Abierto','Banco do Japão','Banco de Japón','Bursa Efek Indonesia','BEI','Indonesia Stock Exchange','IDX','central bank','bank sentral','bank pusat','banque centrale','Zentralbank',
 '美联储','美聯儲','联邦公开市场委员会','聯邦公開市場委員會','欧洲央行','歐洲央行','欧洲中央银行','歐洲中央銀行','日本央行','日本銀行','日銀','中央银行','中央銀行','央行','印尼证券交易所','印尼證券交易所',
 '米連邦準備制度理事会','連邦公開市場委員会','欧州中央銀行','中央銀行','연방준비제도','연방준비제도이사회','연방공개시장위원회','유럽중앙은행','일본은행','중앙은행','인도네시아 증권거래소',
 'Cục Dự trữ Liên bang','Ủy ban Thị trường Mở Liên bang','Ngân hàng Trung ương châu Âu','Ngân hàng Nhật Bản','ngân hàng trung ương',
 'ธนาคารกลางสหรัฐ','ธนาคารกลางยุโรป','ธนาคารกลางญี่ปุ่น','ธนาคารกลาง','คณะกรรมการนโยบายการเงินสหรัฐ',
 'الاحتياطي الفيدرالي','اللجنة الفيدرالية للسوق المفتوحة','البنك المركزي الأوروبي','بنك اليابان','البنك المركزي','بورصة إندونيسيا'
]}
def heading_spans(content):
 # Match offsets in the same concatenated text representation used for highlights.
 return [(len(plain(content[:m.start()])),len(plain(content[:m.end()]))) for m in re.finditer(r'<h[1-6]\\b[^>]*>.*?</h[1-6]>',content,re.I|re.S)]

''';s=s.replace('def check_article(title,summary,content,material):',insert+'def check_article(title,summary,content,material):');p.write_text(s,encoding='utf-8')
p=Path('container/writer-prompt.md');s=p.read_text(encoding='utf-8').replace('每个关键事实都要标明出处，例如','只有当某个事实明确来自某家媒体的报道时，才写“据 XX 报道”。来源不明确的事实用“据报道”或直接陈述，不要把多个媒体并列为同一事实的来源，不要为了显得权威而堆砌媒体名。\n有明确来源的关键事实标明出处，例如');p.write_text(s,encoding='utf-8')
p=Path('container/ai_audit.py');s=p.read_text(encoding='utf-8').replace('每一项reason必须用简体中文','日期等价概括不算问题，例如10月15日至17日写成10月中旬；素材里已有只是措辞不同的事实不要标出。对投资建议保持严格，不放宽禁止操作建议和本文走势判断的规则。每一项reason必须用简体中文');p.write_text(s,encoding='utf-8')
