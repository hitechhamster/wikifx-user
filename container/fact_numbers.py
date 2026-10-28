"""Offline multilingual number helpers. No network or language model."""
import re
from decimal import Decimal
DIGITS=dict(zip('零〇一二三四五六七八九','00123456789'));DIGITS.update({'两':'2','兩':'2'})
UNITS={'十':10,'百':100,'千':1000,'万':10000,'萬':10000,'亿':100000000,'億':100000000}
def han_number(text):
 if re.fullmatch('[零〇一二三四五六七八九]+',text):return Decimal(''.join(DIGITS[c] for c in text))
 total=section=current=0
 for c in text:
  if c in DIGITS:current=current*10+int(DIGITS[c])
  elif c in UNITS:
   unit=UNITS[c]
   if unit<10000:section+=(current or 1)*unit
   else:total+=(section+current or 1)*unit;section=0
   current=0
 return Decimal(total+section+current)
WORDS={}
for words in [['zero','one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve','thirteen','fourteen','fifteen','sixteen','seventeen','eighteen','nineteen'],['nol','satu','dua','tiga','empat','lima','enam','tujuh','delapan','sembilan','sepuluh'],['cero','uno','dos','tres','cuatro','cinco','seis','siete','ocho','nueve','diez'],['zero','um','dois','três','quatro','cinco','seis','sete','oito','nove','dez']]:
 for i,w in enumerate(words):WORDS[w]=i
WORDS.update({'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90,'hundred':100,'thousand':1000,'million':1000000,'billion':1000000000})
WORD=re.compile(r'\b(?:'+ '|'.join(sorted(WORDS,key=len,reverse=True))+r')(?:[- ](?:and )?(?:'+ '|'.join(sorted(WORDS,key=len,reverse=True))+r'))*\b',re.I)
HAN=re.compile(r'[零〇一二三四五六七八九十百千万萬亿億两兩]+(?=(?:美元|日元|日圓|円|元|万|億|倍|家|名|筆|笔|条|條|人|年|月|日|件|次|公斤|公克|%|％))')
MONTH_NAMES=[['january','januari','enero','janeiro','janvier'],['february','februari','febrero','fevereiro','février'],['march','maret','marzo','março','mars'],['april','abril','avril'],['may','mei','mayo','maio','mai'],['june','juni','junio','junho','juin'],['july','juli','julio','julho','juillet'],['august','agustus','agosto','août'],['september','septiembre','setembro','septembre'],['october','oktober','octubre','outubro','octobre'],['november','novembro','noviembre','novembre'],['december','desember','diciembre','dezembro','décembre']]
def word_quantities(text):
 out=[]
 for m in HAN.finditer(text):out.append((m.start(),m.end(),'number',('number',str(han_number(m[0]).normalize()))))
 for m in WORD.finditer(text):
  following=text[m.end():m.end()+28].lower();word=m[0].lower()
  if word in ('um dos','one another'):continue
  if word in ('one','satu') and re.match(r"(?:[ -](?:of|another|time|off|way)\b|['’]s\b)",following):continue
  if word in ('two','dua') and re.match(r'[ -](?:factor|step|faktor|langkah|hal)\b',following):continue
  if word in ('um','uno','dos') and not re.match(r'\s+(?:mil|milhão|milhões|millones|percent|por cento|bancos|millón|veces|días|años)\b',following):continue
  # Skip indefinite articles / word fragments, retain explicit numeric words.
  tokens=re.findall(r'\w+',m[0].lower());value=section=0
  for token in tokens:
   n=WORDS.get(token)
   if n is None:continue
   if n==100:section=(section or 1)*n
   elif n>=1000:value+=(section or 1)*n;section=0
   else:section+=n
  out.append((m.start(),m.end(),'number',('number',str(Decimal(value+section).normalize()))))
 return out

def unit_at(text,a,b):
 left=text[max(0,a-8):a];right=text[b:b+20]
 for label,pat in [('USD',r'USD\s*$|US\$\s*$|\$\s*$'),('IDR',r'Rp\s*$|IDR\s*$'),('INR',r'₹\s*$|INR\s*$'),('EUR',r'€\s*$|EUR\s*$'),('JPY',r'¥\s*$|JPY\s*$')]:
  if re.search(pat,left,re.I):return label,Decimal(1)
 for label,pat in [('USD',r'^\s*(?:美元|dollars?)'),('JPY',r'^\s*(?:円|日元|日圓|yen)'),('INR',r'^\s*(?:rupees?)'),('IDR',r'^\s*(?:rupiah)')]:
  if re.search(pat,right,re.I):return label,Decimal(1)
 for pat,factor in [(r'^\s*(?:kg\b|kilograms?\b|kilogram\b|公斤|킬로그램)',1000),(r'^\s*(?:tonnes?\b|tons?\b|吨|噸)',1000000),(r'^\s*(?:g\b|grams?\b|gram\b|公克|克)',1)]:
  if re.search(pat,right,re.I):return 'mass_g',Decimal(factor)
 return '',Decimal(1)

def derivation(text,a,b,value,source_text,source_q,article_q):
 """Ratios require an explicit ratio cue and both operands in the same article sentence.
 We do not search arbitrary arithmetic combinations of unrelated source numbers.
 """
 if value[0]!='number':return None
 target=Decimal(value[1]);unit,factor=unit_at(text,a,b)
 if unit=='mass_g':
  for sa,sb,sk,sv in source_q:
   if sk!='number' or sv[0]!='number':continue
   su,sf=unit_at(source_text,sa,sb)
   if su==unit and Decimal(sv[1])*sf==target*factor:
    return {'formula':f'{source_text[sa:sb]} × {sf} ÷ {factor} = {text[a:b]}','source_operands':[source_text[max(0,sa-10):sb+16]],'operation':'unit_conversion'}
 # Unit prices require money and mass operands in one short evidence passage.
 suffix=text[b:b+30]
 per_gram=bool(re.search(r'^\s*(?:per gram\b|/\s*g\b|每克)',suffix,re.I) or re.search(r'per gram(?:nya)?|每克',text[max(0,a-55):a],re.I))
 per_kg=bool(re.search(r'^\s*(?:per (?:kg|kilogram)\b|/\s*kg\b|每公斤)',suffix,re.I) or re.search(r'per (?:kg|kilogram)|每公斤',text[max(0,a-55):a],re.I))
 if unit in ('USD','IDR','INR','EUR','JPY') and (per_gram or per_kg):
  amounts=[];masses=[]
  for sa,sb,sk,sv in source_q:
   if sk!='number' or sv[0]!='number':continue
   su,sf=unit_at(source_text,sa,sb)
   if su==unit:amounts.append((Decimal(sv[1]),sa,sb))
   if su=='mass_g':masses.append((Decimal(sv[1])*sf,sa,sb))
  for amount,aa,ab in amounts:
   for mass,ma,mb in masses:
    if not mass or abs(aa-ma)>240:continue
    computed=amount/mass*(1000 if per_kg else 1)
    literal=re.search(r'\d+(?:[.,]\d+)?',text[a:b]);decimal_places=len(re.split('[.,]',literal[0])[1]) if literal and re.search('[.,]',literal[0]) else 0
    display_scale=target/Decimal(literal[0].replace(',','.')) if literal and Decimal(literal[0].replace(',','.')) else Decimal(1)
    tolerance=display_scale*(Decimal(10)**(-decimal_places))/2
    if abs(computed-target)<=tolerance:
     return {'formula':f'{amount} ÷ {mass} g'+(' × 1000' if per_kg else '')+f' ≈ {target}','source_operands':[source_text[max(0,aa-8):ab+15],source_text[max(0,ma-8):mb+15]],'operation':'unit_price'}
 sentence_start=max(text.rfind('.',0,a),text.rfind('。',0,a),text.rfind('\n',0,a))+1
 ends=[x for x in (text.find('.',b),text.find('。',b),text.find('\n',b)) if x>=0];sentence_end=min(ends) if ends else len(text)
 sentence=text[sentence_start:sentence_end]
 if not re.search(r'倍|times\b|kali\b|vezes\b|veces\b|배',sentence,re.I):return None
 operands=[]
 for aa,bb,kind,v in article_q:
  if aa==a or kind!='number' or v[0]!='number' or not(sentence_start<=aa<sentence_end):continue
  hits=[(sa,sb) for sa,sb,sk,sv in source_q if sk=='number' and sv==v]
  if hits:operands.append((Decimal(v[1]),text[aa:bb],hits[0],unit_at(text,aa,bb)[0]))
 for av,at,asp,au in operands:
  for bv,bt,bsp,bu in operands:
   if not bv or asp==bsp or au!=bu:continue
   # Require source values in the same short evidence passage as well.
   if abs(asp[0]-bsp[0])>240:continue
   computed=av/bv
   if abs(computed-target)<=max(Decimal('0.000001'),abs(target)*Decimal('0.001')):
    return {'formula':f'{at} ÷ {bt} = {text[a:b]}','source_operands':[source_text[max(0,x[0]-20):x[1]+20] for x in [asp,bsp]],'operation':'ratio'}
 return None
