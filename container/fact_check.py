"""Deterministic evidence matching; no model calls. Findings are review hints, not verdicts."""
import re, html, unicodedata, hashlib
from decimal import Decimal, InvalidOperation
from fact_numbers import word_quantities, derivation, MONTH_NAMES
from html.parser import HTMLParser
class Text(HTMLParser):
 def __init__(self):super().__init__();self.parts=[]
 def handle_data(self,s):self.parts.append(s)
def plain(s):
 p=Text();p.feed(s or '');return ''.join(p.parts)
def norm(s):return re.sub(r'[^\w]', '',unicodedata.normalize('NFKC',s).casefold())
SCALE={'thousand':1000,'million':1000000,'billion':1000000000,'trillion':1000000000000,'ribu':1000,'juta':1000000,'miliar':1000000000,'triliun':1000000000000,'mil':1000,'millones':1000000,'milhões':1000000,'milhão':1000000,'千':1000,'万':10000,'萬':10000,'亿':100000000,'億':100000000,'兆':1000000000000,'만':10000,'억':100000000,'조':1000000000000}
SCALE.update({'crore':10000000,'crores':10000000,'lakh':100000,'lakhs':100000,'ألف':1000,'آلاف':1000,'مليون':1000000,'مليار':1000000000,'triệu':1000000,'tỷ':1000000000,'nghìn':1000,'ล้าน':1000000})
NUM=re.compile(r'(?<![\d])(?:\d{1,3}(?:[, .\u00a0]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)(?:\s*(?:'+ '|'.join(sorted(SCALE,key=len,reverse=True))+r'))?(?:\s*(?:%|％|percent|per cent|persen|por cento))?',re.I)
# CJK numbers adjacent to text do not have word boundaries.
CJKNUM=re.compile(r'\d+(?:[.,]\d+)?(?:千|万|萬|亿|億|兆|만|억|조)(?:\d+(?:千|万|萬)?)?')
DATE=re.compile(r'\b(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\b|\d{4}年\d{1,2}月\d{1,2}日|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b')
MONTHS={m:i+1 for i,m in enumerate(['january','february','march','april','may','june','july','august','september','october','november','december'])}
MONTHS.update({m:i+1 for i,m in enumerate(['januari','februari','maret','april','mei','juni','juli','agustus','september','oktober','november','desember'])})
MONTHS.update({m:i+1 for i,names in enumerate(MONTH_NAMES) for m in names})
MONTHS.update({m[:3]:i for m,i in list(MONTHS.items())})
VIDATE=re.compile(r'(?:ngày\s+)?\d{1,2}\s+tháng\s+\d{1,2}(?:\s+năm\s+\d{4})?',re.I)
VIMONTH=re.compile(r'tháng\s+(\d{1,2})',re.I)
LOCALDATE=re.compile(r'(?:\d{4}[年년]\s*)?\d{1,2}[月월]\s*\d{1,2}[日일]')
MONTHDATE=re.compile(r'\b(\d{1,2})\s+('+ '|'.join(MONTHS)+r')(?:\s+(\d{4}))?\b|\b('+ '|'.join(MONTHS)+r')\s+(\d{1,2})(?:,?\s+(\d{4}))?\b',re.I)
def number(s):
 s=unicodedata.normalize('NFKC',s).lower();scale=1
 if re.fullmatch(r'\d+(?:[.,]\d+)?[万萬亿億兆千]\d+',s):
  m=re.fullmatch(r'(\d+(?:[.,]\d+)?)([万萬亿億兆千])(\d+)',s);return ('number',str((Decimal(m[1].replace(',','.'))*SCALE[m[2]]+Decimal(m[3])).normalize()))
 for unit in sorted(SCALE,key=len,reverse=True):
  if unit in s:scale=SCALE[unit];s=s.replace(unit,'');break
 percent=bool(re.search(r'%|percent|per cent|persen|por cento',s));s=re.sub(r'[^\d.,]','',s)
 if ',' in s and '.' in s:
  dec=',' if s.rfind(',')>s.rfind('.') else '.';s=s.replace('.' if dec==',' else ',','').replace(dec,'.')
 elif not percent and scale==1 and re.fullmatch(r'\d{1,3}(?:[.,]\d{3})+',s):s=s.replace(',','').replace('.','')
 else:s=s.replace(',','.')
 try:return ('percent' if percent else 'number',str((Decimal(s)*scale).normalize()))
 except InvalidOperation:return ('unparsed',s)
def date_value(s):
 m=MONTHDATE.fullmatch(s)
 if m:return f"{int(m[3] or m[6] or 0):04d}-{MONTHS[(m[2] or m[4]).lower()]:02d}-{int(m[1] or m[5]):02d}"
 n=list(map(int,re.findall(r'\d+',s)))
 if len(n)==3 and n[0]>31:y,mo,d=n
 elif len(n)==3:d,mo,y=n
 else:
  if re.search('[月월]',s):mo,d=n
  else:d,mo=n
  y=0
 return f'{y:04d}-{mo:02d}-{d:02d}'
def quantities(s):
 occupied=[m.span() for m in re.finditer(r'24/7',s)];out=[]
 for pattern,kind in [(VIDATE,'date'),(DATE,'date'),(LOCALDATE,'date'),(MONTHDATE,'date'),(VIMONTH,'month'),(CJKNUM,'number'),(NUM,'number')]:
  for m in pattern.finditer(s):
   if m[0]=='24/7':continue
   if any(m.start()<b and m.end()>a for a,b in occupied):continue
   occupied.append(m.span());out.append((m.start(),m.end(),kind,date_value(m[0]) if kind=='date' else ('month',str(int(m[1]))) if kind=='month' else number(m[0])))
 for pattern in [VIMONTH]:
  for m in pattern.finditer(s):
   if not any(m.start()<b and m.end()>a for a,b in occupied):
    occupied.append(m.span());out.append((m.start(),m.end(),'month',('month',str(int(m[1])))))
 for m in re.finditer(r'\b(?:'+ '|'.join(sorted(MONTHS,key=len,reverse=True))+r')\b',s,re.I):
  if len(m[0])<=3 and m[0]!='May':continue
  if not any(m.start()<b and m.end()>a for a,b in occupied):
   occupied.append(m.span());out.append((m.start(),m.end(),'month',('month',str(MONTHS[m[0].lower()]))))
 for entry in word_quantities(s):
  if not any(entry[0]<b and entry[1]>a for a,b in occupied):out.append(entry)
 return out
# Capitalized multiword names, acronyms, and CJK name/organization suffixes.
LATIN=re.compile(r'\b(?:[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+|[A-Z]{2,})(?:[ -](?:(?:of|the|de|da|do|del|y|and|&|di)\s+)?(?:[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+|[A-Z]{2,})){1,5}\b|\b[A-Z]{2,}[A-Z0-9.]*\b')
EAST=re.compile(r'[\u3400-\u9fff\u30a0-\u30ff]{2,16}(?:銀行|银行|証券|证券|委員会|委员会|通信社|新聞|日报|日報|財務省|金融庁|金融厅)|[가-힣]{2,12}(?:은행|증권|위원회|뉴스)|[\u3400-\u9fff]{2,6}(?=氏|さん|首相|大統領|総裁)|[가-힣]{2,4}(?=\s*(?:대통령|총재|장관))')
PERSON=re.compile(r'\b(?:Mr\.?|Ms\.?|Dr\.?|President|Governor|Minister|CEO)\s+([A-Z][a-z]+(?:[ -][A-Z][a-z]+){0,3})')
IGNORE={'AML','CFT','KTP','OTP','CFD','VPS','GHS','South Asia','South Asian','US Dollar','USD','EUR','JPY','KRW','IDR','MYR','GBP','AUD','CHF','CAD','CNY','TWD','BRL','INR','PKR','US','UK','EU','HTML','JSON','AM','PM','Sources','Impact Scope','Risk Warning','West African'}
ALIASES=[['Federal Reserve','Fed','美联储','美聯儲','米連邦準備制度','연방준비제도'],['Bank of Japan','BOJ','日本銀行','日本央行'],['European Central Bank','ECB','欧洲央行','歐洲央行'],['International Monetary Fund','IMF','FMI','国际货币基金组织'],['Financial Services Authority','OJK','Otoritas Jasa Keuangan'],['Bank Negara Malaysia','BNM','马来西亚国家银行']]
def strings(obj):
 if isinstance(obj,str):return [obj]
 if isinstance(obj,list):return sum((strings(v) for v in obj),[])
 if isinstance(obj,dict):return sum((strings(v) for k,v in obj.items() if k not in ('url','id','topic_id','run_date','content_status','type')),[])
 return []
# Common translations are explicit, versioned aliases; the generated article cannot invent aliases.
ALIASES += [
 ['Bank of Japan','BOJ','日本銀行','日銀','日本央行','일본은행'],
 ['Bank Negara Malaysia','BNM','马来西亚国家银行','馬來西亞國家銀行','Bank Sentral Malaysia'],
 ['Nirmala Sitharaman','尼尔玛拉·西塔拉曼','尼爾瑪拉·西塔拉曼'],
 ['Sanae Takaichi','高市早苗','다카이치 사나에'],
 ['Financial Services Agency','金融庁','日本金融厅','日本金融廳'],
 ['Financial Conduct Authority','FCA','英国金融行为监管局','英國金融行為監管局'],
 ['Securities and Exchange Board of India','SEBI','印度证券交易委员会','印度證券交易委員會'],
 ['Dubai Financial Services Authority','DFSA','迪拜金融服务管理局','杜拜金融服務管理局'],
 ['Reuters','路透社','ロイター','로이터'],['Bloomberg','彭博','ブルームバーグ','블룸버그'],
 ['The Star','星报','星報'],['Malay Mail','马来邮报','馬來郵報'],
 ['Finance Magnates','FinanceMagnates.com'],['CNBC','CNBC Indonesia'],
 ['First Information Report','FIR'],['Computer Emergency Response Team','CERT-In'],
 ['Structured Financial Messaging System','SFMS'],['Bank of Ghana','加纳央行','迦納央行']
]
# Avoid treating every title-cased news headline as a personal name.
NARRATIVE=set('menurut di phía beyond jadi incaran jalur ilegal theo el en ungghahan their breath momentum fades euro zone malaysian regulator regulators warn warns warning warned traders investors platform fraudulent investment risk impact scope what why how who when where across for amid against about after before from into with as on in at to the a an and news report reported reports orders order final penalty refund year market ban says said sees faces higher lower hold rates rate long term bull case tested policy week packed edges dollar dollar rupiah ringgit gold stolen scam fraud economy billion million crore miliar nyaris kabur dalam tas sampai menempel tubuh kenapa emas begitu menarik yang perlu diperhatikan pengadilan batalkan denda putusan unggahan cek rekening anda sebelum percaya kabar wakil ketua'.split())
ORG=re.compile(r'bank|banco|banca|banque|securities|authority|commission|committee|council|ministry|ministerio|reserve|news|times|mail|post|journal|magnates|academy|group|capital|markets|broker|police',re.I)
ROLE=re.compile(r'(?:minister|president|governor|chairman|chair|chief|CEO|Mr\.?|Ms\.?|Dr\.?)\s+([A-Z][a-z]+(?:[ -][A-Z][a-z]+){1,3})')
def name_candidates(text):
 candidates=[]
 for pattern in [LATIN,EAST,PERSON,ROLE]:
  for m in pattern.finditer(text):
   a,b=m.span(1) if pattern in [PERSON,ROLE] else m.span();name=text[a:b]
   if pattern is EAST:
    if re.search(r'[的是這这其類类則则將将]',name):continue
   else:
    # Split off leading narrative words and conjunctions; keep organizations intact.
    words=list(re.finditer(r"[\wÀ-ÿ]+",name));trim=0
    while trim<len(words) and words[trim][0].casefold() in NARRATIVE:trim+=1
    if trim==len(words):continue
    a+=words[trim].start();name=text[a:b]
    # Known narrative verbs terminate a name, rather than extending it across a headline.
    stop=re.search(r'\s+(?:Flags|Await|Face|Sebut|Peringatkan|Cap|Laporkan|Likely|Warns|Edges|Weighs|Converge|Stolen|Reported|Reports|Batalkan|Sampai|Menempel)\b',name)
    if stop:b=a+stop.start();name=text[a:b]
    tokens=re.findall(r"[\wÀ-ÿ]+",name)
    if any(t.casefold() in NARRATIVE for t in tokens) and not ORG.search(name):continue
    if len(tokens)>4 and not ORG.search(name):continue
   if name in IGNORE or len(name)<2:continue
   # A conjunction joins separate names; don't invent a larger composite entity.
   pieces=list(re.finditer(r'[^\n]+?(?=\s+(?:and|dan|y|e)\s+|$)',name))
   if len(pieces)>1:
    for part in pieces:
     clean=re.sub(r'^\s*(?:and|dan|y|e)\s+','',part[0]).strip();offset=part[0].find(clean)
     candidates.append((a+part.start()+offset,a+part.start()+offset+len(clean),clean))
    continue
   candidates.append((a,b,name))
 # Explicit known translated names are recognized even when capitalization differs.
 for group in ALIASES:
  for alias in group:
   for m in re.finditer(re.escape(alias),text,re.I):
    if alias.isascii() and ((m.start() and text[m.start()-1].isalnum()) or (m.end()<len(text) and text[m.end()].isalnum())):continue
    candidates.append((*m.span(),m[0]))
 return sorted(set(candidates),key=lambda x:(x[0],-(x[1]-x[0])))


# Common financial vocabulary is exempt, not proof for any attributed claim.
COMMON_TERMS={norm(x) for x in [
 'FX','Forex','Fed','FOMC','ECB','BoJ','Federal Reserve','Federal Open Market Committee','European Central Bank','Bank of Japan','Banco Central','Banco Central Europeu','Banco Central Europeo','Reserva Federal','Comitê Federal de Mercado Aberto','Comité Federal de Mercado Abierto','Banco do Japão','Banco de Japón','Bursa Efek Indonesia','BEI','Indonesia Stock Exchange','IDX','central bank','bank sentral','bank pusat','banque centrale','Zentralbank',
 '美联储','美聯儲','联邦公开市场委员会','聯邦公開市場委員會','欧洲央行','歐洲央行','欧洲中央银行','歐洲中央銀行','日本央行','日本銀行','日銀','中央银行','中央銀行','央行','印尼证券交易所','印尼證券交易所',
 '米連邦準備制度理事会','連邦公開市場委員会','欧州中央銀行','中央銀行','연방준비제도','연방준비제도이사회','연방공개시장위원회','유럽중앙은행','일본은행','중앙은행','인도네시아 증권거래소',
 'Cục Dự trữ Liên bang','Ủy ban Thị trường Mở Liên bang','Ngân hàng Trung ương châu Âu','Ngân hàng Nhật Bản','ngân hàng trung ương',
 'ธนาคารกลางสหรัฐ','ธนาคารกลางยุโรป','ธนาคารกลางญี่ปุ่น','ธนาคารกลาง','คณะกรรมการนโยบายการเงินสหรัฐ',
 'الاحتياطي الفيدرالي','اللجنة الفيدرالية للسوق المفتوحة','البنك المركزي الأوروبي','بنك اليابان','البنك المركزي','بورصة إندونيسيا'
]}
def common_remainder(name):
 value=norm(name)
 for term in sorted(COMMON_TERMS,key=len,reverse=True):value=value.replace(term,'')
 return value
def heading_spans(content):
 # Match offsets in the same concatenated text representation used for highlights.
 return [(len(plain(content[:m.start()])),len(plain(content[:m.end()]))) for m in re.finditer(r'<h[1-6]\b[^>]*>.*?</h[1-6]>',content,re.I|re.S)]

def check_article(title,summary,content,material):
 evidence=plain('\n'.join(strings(material)));source=norm(evidence);q=quantities(evidence);values={str(x[3]) for x in q};findings=[];derived=[];checked=0
 for field,text in [('title',title),('summary',summary),('content',plain(content))]:
  spans=[];article_q=quantities(text)
  for a,b,kind,value in article_q:
   if not re.search(r"\d|[万萬亿億千百十兆]",text[a:b]):continue
   checked+=1;supported=str(value) in values
   if kind=='month' and not supported:supported=any(x[2]=='date' and str(int(str(x[3]).split('-')[1]))==value[1] for x in q)
   if kind=='date' and not supported:supported=any(x[2]=='date' and (value.startswith('0000') or str(x[3]).startswith('0000')) and str(x[3])[-5:]==value[-5:] for x in q)
   if not supported and kind=='number':
    proof=derivation(text,a,b,value,evidence,q,article_q)
    if proof:
     derived.append({'field':field,'start':a,'end':b,'text':text[a:b],'kind':'derived','reason':'推算：'+proof['formula'],**proof});continue
   if not supported:spans.append((a,b,kind))
  for a,b,name in name_candidates(text):
   if field=='summary':continue
   if field=='content' and any(a<y and b>x for x,y in heading_spans(content)):continue
   if norm(name) in COMMON_TERMS or not common_remainder(name):continue
   if field=='title' and not (ORG.search(name) or any(norm(name)==norm(alias) for group in ALIASES for alias in group) or any(m.span(1)==(a,b) for m in ROLE.finditer(text))):continue
   if norm(name) in source:continue
   matched=any(norm(name) in [norm(x) for x in group] and any(norm(x) in source for x in group) for group in ALIASES)
   checked+=1
   if not matched and not any(a<y and b>x for x,y,_ in spans):spans.append((a,b,'name'))
  for a,b,kind in sorted(spans):findings.append({'field':field,'start':a,'end':b,'text':text[a:b],'kind':kind,'reason':'素材中未找到'})
 title_unmatched=any(f['field']=='title' for f in findings)
 return {'version':'deterministic-v3-low-false-positive','count':len(findings),'checked':checked,'findings':findings,'derived':derived,'derived_count':len(derived),'title_unmatched':title_unmatched,'needs_retry':len(findings)>3 or title_unmatched,'passed':not findings,'limitations':'数字与名称素材匹配；规则和译名字典可能漏检或误报，不能自动判断事件归属、因果或数字语义是否正确。'}
