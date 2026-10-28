from pathlib import Path
import json,re,markdown,bleach
from news_policy import validate
from app import language_ok
root=Path('/work/sent-corrections');out=root/'edited';out.mkdir(exist_ok=True)
langs={'195':'en','196':'en','197':'id','214':'vi','216':'id','217':'id','219':'pt','220':'es','222':'zh','223':'th'}
for hub,lang in langs.items():
 r=json.loads((root/'results'/f'{hub}.json').read_text(encoding='utf-8'));a=r['article'];body=a['body'];notes=[]
 if hub=='195':
  body=re.sub(r'据 The Star 和 Free Malaysia Today 报道.*?\n\n',"According to The Star and Free Malaysia Today, the ringgit edged higher against the US dollar in early trading on Monday amid caution ahead of the FOMC statement. The Malaysian Reserve and Free Malaysia Today reported a weaker close on Friday, citing concerns about AI-related share prices and caution ahead of the Fed announcement. Free Malaysia Today also described widespread expectations that interest rates would hold steady.\n\n",body,flags=re.S)
  body=re.sub(r'Malay Mail 在周末的报道中称.*?\n\n',"Malay Mail reported expectations for the ringgit to trade within a narrow RM4.07–RM4.08 range against the US dollar in the following week. That range is a forecast attributed to the report, not a forecast made by this article.\n\n",body,flags=re.S)
  a['meta_description']='The Star and Free Malaysia Today reported a modest early gain for the ringgit against the dollar amid caution ahead of the FOMC statement.';a['keywords']=['ringgit','US dollar','FOMC','Malaysia'];notes=['Translate mixed-language paragraphs; explicitly attribute the published range forecast.']
 elif hub=='196':
  body=body.replace('In a genuine brokerage, client funds sit with a regulated custodian and trades are executed on an exchange.','A trading interface alone does not establish that its operator is licensed or that the displayed transactions took place.')
  body=re.sub(r'HPCL employees, like staff.*?\n\n','',body,flags=re.S)
  body=body.replace(' The report did not specify the outcome of any investigation or recovery of funds.','');notes=['Remove unsupported targeting claim and overbroad brokerage statement; remove material-limit narration.']
 elif hub=='197':
  a['title']='Didik Mukrianto: Pengadilan Jakarta Batalkan Denda Rp755 Miliar ke 97 Pinjol'
  a['meta_description']='Didik Mukrianto menyebut Pengadilan Niaga Jakarta Pusat membatalkan denda KPPU Rp755 miliar terhadap 97 perusahaan pinjol karena batas bunga mengikuti arahan OJK.'
  body='Menurut unggahan Didik Mukrianto di X, '+body[0].lower()+body[1:]
  body=body.replace('menurut penulis','menurut Didik Mukrianto').replace('OJK memang mengatur batas manfaat ekonomi','Unggahan Didik Mukrianto menyebut OJK mengatur batas manfaat ekonomi');notes=['Make social-post attribution explicit in title, summary and claims.']
 elif hub=='214':
  body=body.replace('hôm thứ Hai (27/10)','hôm thứ Hai')
  body=re.sub(r'Nhật Bản là thị trường môi giới duy nhất.*?\n\n','',body,flags=re.S);notes=['Remove unsupported parenthetical date and off-topic broker-traffic paragraph.']
 elif hub=='216':
  a['title']='Lambe Saham Sebut Rupiah di 18.108/USD; ChatNews.id Laporkan 18.110'
  a['meta_description']='Unggahan Lambe Saham menyebut rupiah di 18.108 per dolar AS, sementara ChatNews.id melaporkan penutupan 18.110 pada 26 Oktober sebagai yang terlemah dalam empat bulan.'
  body=re.sub(r'\A.*?\n\n',"Unggahan akun Lambe Saham di X menyebut rupiah kembali melemah ke 18.108 per dolar AS. Secara terpisah, ChatNews.id melaporkan level 18.110 pada penutupan Senin (26/10/2026) dan menyebutnya sebagai penutupan terlemah dalam empat bulan. Angka dan klaim dari kedua sumber tersebut perlu dibedakan; unggahan media sosial itu tidak membuktikan rekor sepanjang masa.\n\n",body,count=1,flags=re.S)
  body=body.replace('angka 18.108 maupun 18.110 adalah hasil perdagangan hari itu','angka 18.108 berasal dari unggahan Lambe Saham, sedangkan 18.110 adalah level yang diberitakan ChatNews.id')
  body=body.replace('Kedua, saham-saham di IHSG bisa tertekan oleh arus keluar dana asing seperti yang dilaporkan Bloomberg Technoz.','Kedua, Bloomberg Technoz melaporkan pelemahan IHSG pada perdagangan pagi dengan latar depresiasi rupiah.')
  body=re.sub(r'Pelemahan rupiah ke 18\.108 per dolar AS adalah fakta perdagangan hari Senin\..*$', 'Pelaporan kurs dan pengumuman resmi menjadi rujukan lanjutan. Waspadai klaim rekor atau tawaran investasi yang beredar melalui akun tidak resmi.',body,flags=re.S);notes=['Separate social 18.108 claim from media 18.110 report; remove unverified record framing.']
 elif hub=='217':
  body=re.sub(r'Dalam hitungan sederhana, 25,88 kilogram.*?jaringan penyelundup\.','',body,flags=re.S)
  body=body.replace('Kedua, penumpang internasional pada umumnya, karena pengawasan di lima bandara tersebut diperketat dan proses pemeriksaan bisa memakan waktu lebih lama.','Kedua, penumpang internasional yang membawa emas melalui bandara.')
  body=body.replace('Bea Cukai belum merinci identitas para pelaku maupun kronologi lengkap masing-masing penindakan. ','');notes=['Remove added calculation and unsupported claim about wider airport checks.']
 elif hub=='219':
  body=body.replace('no dia seguinte à vitória de Lula','em contexto associado à vitória de Lula')
  body=re.sub(r'É o tipo de número que, em uma única sessão,.*?como o conhecemos hoje\.','',body,flags=re.S)
  body=body.replace('O que vem depois depende de uma combinação de fatores que nenhum texto pode antecipar com honestidade: o comportamento dos fluxos externos, a reação do Banco Central e o noticiário político.','');notes=['Remove incorrect double-digit description and unsupported next-day timing.']
 elif hub=='220':
  body=body.replace('El resultado no fue una caída del dólar, sino una suba más contenida de la que se habría visto sin esa intervención.','')
  body=body.replace('Pero la intervención no cambia la tendencia de fondo: solo la modera. Por eso el billete igual avanzó 0,75%.','El avance de 0,75% corresponde a la jornada descrita por el analista citado en iProfesional.')
  body=re.sub(r'Hay una razón de fondo que suele explicar estas decisiones:.*?para intervenir\.\n\n','',body,flags=re.S);notes=['Remove unsupported counterfactual and judgement about the underlying price trend.']
 elif hub=='222':
  body=body.replace('八萬元換二七〇萬元，投報率超過三十倍，這正是「出金手」這個角色存在的理由。','本案先匯出八萬元、後使被害人投入二七〇萬元，呈現了詐團以小額入帳取信被害人的手法。');notes=['Remove added return calculation from fraud-mechanism explanation.']
 elif hub=='223':
  body=body.replace('официаль','ทางการ')
  body=body.replace('เมื่อต้องทำธุรกรรมเงินสดก้อนใหญ่ ควรเตรียมเอกสารที่แสดงที่มาของเงินให้พร้อม และติดต่อธนาคารล่วงหน้าเพื่อสอบถามขั้นตอนที่ต้องใช้\n\n','')
  body=body.replace(' ผู้ที่วางแผนทำธุรกรรมเงินสดมูลค่าสูงผ่านสาขาควรเผื่อเวลาและเตรียมเอกสารให้พร้อมตั้งแต่ตอนนี้','');notes=['Correct stray Russian word; close on the effective date instead of procedural advice.']
 a['body']=body.strip();html=bleach.clean(markdown.markdown(a['body']),tags=['p','h2','h3','strong','em','ul','ol','li','a','blockquote'],attributes={'a':['href','title']},protocols=['https','http'],strip=True)
 units=validate(html,a['title'],True,lang);assert language_ok(html,lang)[0],hub
 assert not (lang in ('en','id','vi','pt','es') and len(re.findall(r'[\u3400-\u9fff]',html))>20),hub
 footer=r['content'][r['content'].rfind('<p><strong>'):];assert footer.startswith('<p><strong>')
 r.update(content=html+footer,word_count=units,editorial_review={'changes':notes,'policy':'news-v3-no-investment-advice'})
 payload=json.loads((root/'bases'/f'{hub}.json').read_text(encoding='utf-8'));payload.update(title=a['title'],summary=a['meta_description'],content=r['content'],keywords=','.join(a.get('keywords',[])))
 (out/f'{hub}.result.json').write_text(json.dumps(r,ensure_ascii=False),encoding='utf-8');(out/f'{hub}.payload.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8');print(hub,lang,units,'validated')
