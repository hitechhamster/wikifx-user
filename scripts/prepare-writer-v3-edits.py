from pathlib import Path
import json,re,markdown,bleach
from news_policy import validate,count_units
from app import language_ok
root=Path('/work/writer-v3'); out=root/'edited';out.mkdir(exist_ok=True)
ids=['86f1b9e8-4de2-4150-983d-1de32c30c722','c9f2386e-2842-4706-837d-2ec91d5cf2ac','c66c1ac2-58b4-4592-afb6-3c4c113469b4','577ab96a-d5e0-4e94-a99c-18c2376ff160','f997889f-8039-426e-95bc-8252e312c797','3c8da703-220b-4476-9f84-390efd658365']
for id in ids:
    source=root/'after'/f'{id}.json'
    if not source.exists():source=sorted((root/'before').glob(f'previous-attempt-*-{id}.json'))[-1]
    result=json.loads(source.read_text(encoding='utf-8-sig'));a=result['article'];body=a['body'];edits=[]
    if id.startswith('86f1'):
        a['title']='OJK Peringatkan Akun Palsu yang Mengatasnamakan Anggota Dewan Komisioner'
        a['meta_description']='OJK mengingatkan masyarakat agar waspada terhadap akun media sosial yang mengatasnamakan Anggota Dewan Komisioner dan memverifikasi informasi melalui Kontak OJK 157.'
        a['keywords']=['OJK','akun palsu','penipuan','keamanan akun']
        body=re.sub(r'Perlu dicatat, pengumuman ini tidak menyebut.*?jalur resmi\.\n\n','',body,flags=re.S)
        edits=['Translate title, summary and keywords into Indonesian; remove material-limit narration.']
    elif id.startswith('c9f2'):
        a['title']='Fed, ECB and BoJ Decisions Converge With UK Budget in Packed Policy Week'
        a['meta_description']='Reuters flags a cluster of central-bank decisions and economic releases, while a social-media calendar also lists the UK Budget. The events concern several major currencies and the institutions and businesses using them.'
        body='''A crowded policy calendar brings decisions from the Federal Reserve, European Central Bank and Bank of Japan into the same stretch of the week, according to Reuters’ markets preview. A social-media calendar also lists the UK Budget, a Bank of Canada decision and US growth and inflation releases. The events concern the dollar, euro, yen, sterling and Canadian dollar, as well as markets connected to those currencies.

## Several institutions, separate decisions

Reuters’ preview focuses on the Fed, ECB and BoJ alongside a heavy run of economic data. The Star reports that the three central banks will probably hold rates steady. That is the newspaper’s assessment ahead of the announcements, rather than an announced policy outcome.

Equiti Global’s week-ahead note identifies inflation releases, weak housing data and concerns about artificial-intelligence spending as part of the backdrop. Each institution has its own remit and decision process; sharing a week on the calendar does not mean their announcements have a common outcome.

The UK Budget is a fiscal event, distinct from central-bank monetary-policy decisions. Its inclusion makes the calendar relevant to both government finances and interest-rate expectations. The precise content of these announcements comes from the issuing institutions, rather than from advance commentary.

## How announcements enter market prices

Central-bank communications describe policy decisions and the reasoning behind them. Interest rates affect borrowing costs and the income associated with interest-bearing assets. Exchange rates express the relative value of two currencies, so information about either economy can be relevant to the same currency pair.

Economic data provide a separate channel. Growth and inflation releases describe activity and prices, while fiscal announcements concern government revenue, spending and financing. Market participants interpret these different kinds of information together. The mechanisms explain why multiple markets can respond to the same calendar without establishing any particular future price or exchange-rate direction.

## Impact extends beyond currency trading

The currencies on the calendar are used in cross-border trade, business funding, remittances and foreign-currency accounts. Companies with invoices or liabilities in those currencies, households with overseas payments and financial institutions handling settlement all fall within the scope.

For Malaysian markets, currency conversion links those payments and balances to ringgit amounts. Retail foreign-exchange and CFD platforms are another point of contact, alongside funds and other products holding foreign-currency assets. Differences in settlement currency and product structure explain how the same announcement can concern different groups; they are not instructions to change an investment position.

## Official announcements and account safety

The policy statements, the UK Budget and the listed economic releases are the follow-up events in the reporting. Any dates or decisions should be checked against the issuing institution’s official calendar and announcements.

Account-security reminders remain relevant: verify a platform’s regulatory registration through official records, enable two-factor authentication and be alert to messages impersonating a broker or public institution. Do not transfer funds to a private account on the basis of an unsolicited message. These checks concern identity and account security, not market timing or investment allocation.'''
        edits=['Remove timing/position advice, including quoted social-post trading instructions; retain attributed policy expectations and objective mechanisms.']
    elif id.startswith('c66c'):
        body=body.replace('That is the whole of the confirmed move — a small gain, not a breakout — and it sets the tone for a week in which the ringgit\'s direction will likely be decided in Washington rather than in Kuala Lumpur.','The reports describe a modest opening gain ahead of the scheduled FOMC announcement.')
        edits=['Remove unattributed forward-looking judgement about the ringgit.']
    elif id.startswith('577a'):
        a['title']='Bloomberg: ECB Likely to Hold Rates as Euro-Zone Momentum Fades'
        a['meta_description']='Bloomberg reports that fading euro-zone momentum is one reason the ECB will probably hold off on raising rates. The report concerns euro-linked currency markets, borrowing costs and institutions exposed to the region.'
        edits=['Attribute the policy expectation in the headline and summary; preserve uncertainty.']
    elif id.startswith('f997'):
        body=body.replace('In one of the most brazen cyber heists to hit India\'s banking system, Central Bank of India','Central Bank of India')
        body=body.replace('The slight discrepancy in the figures—₹13.97 crore versus ₹13.96 crore—reflects different stages of the complaint and investigation. ','')
        body=re.sub(r'For retail traders and investors, the direct impact.*?\n\n','',body,flags=re.S)
        body=re.sub(r'Separately, the Enforcement Directorate.*?\n\n','',body,flags=re.S)
        body=body.replace('The RBI and CERT-In are expected to release further details as the investigation progresses.','The investigation described in the reports remains the follow-up event.')
        edits=['Remove unsupported discrepancy explanation, personal-account reassurance and unrelated case; retain the reported investigation.']
    else:
        body=body.replace('Perkembangan lanjutan soal klaim Jusuf Hamka maupun langkah hukum terkait penyebaran narasi tersebut belum diumumkan secara rinci dalam pemberitaan yang ada.','')
        edits=['Remove material-limit narration from closing paragraph.']
    body=re.sub(r'\A\s*#{1,3} [^\n]+\n+', '', body).strip();a['body']=body
    footer=result['content'][result['content'].rfind('<p><strong>'):]
    assert footer.startswith('<p><strong>')
    content=bleach.clean(markdown.markdown(body),tags=['p','h2','h3','strong','em','ul','ol','li','a','blockquote'],attributes={'a':['href','title']},protocols=['https','http'],strip=True)
    lang='id' if id.startswith(('86f1','3c8d')) else 'en'
    units=validate(content,a['title'],True,lang)
    assert language_ok(content,lang)[0] and language_ok(a['title']+' '+a['meta_description'],lang)[0]
    result.update(content=content+footer,word_count=units,state='complete',detected_language=lang,editorial_review={'policy':'news-v3-no-investment-advice','changes':edits,'source_file':source.name})
    payload=json.loads((out/f'{id}.base.json').read_text(encoding='utf-8-sig'));payload.update(title=a['title'],summary=a['meta_description'],content=result['content'],keywords=','.join(a.get('keywords',[])))
    (out/f'{id}.result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');(out/f'{id}.payload.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    print(id,lang,units,'validated')

