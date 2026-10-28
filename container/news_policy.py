"""News prompt and deterministic output checks; no network or credentials."""
import re,html
from pathlib import Path
DOCUMENT=Path(__file__).with_name('writer-prompt.md').read_text(encoding='utf-8-sig')
SYSTEM,THIN_SYSTEM=re.findall(r'```text\s*\n(.*?)\n```',DOCUMENT,re.S)[:2]
def limits(thin,target):
    cjk=target.split('-')[0] in ('zh','ja','ko')
    return ((800,1100) if thin else (1200,1800)) if cjk else ((450,650) if thin else (700,1000))
def messages(material,region,thin):
    system=SYSTEM.replace('{region_name}',region['name']).replace('{language}',region['language'])
    if thin:system+='\n'+THIN_SYSTEM
    return [{'role':'system','content':system},{'role':'user','content':__import__('json').dumps({'language':region['language'],'region':region['name'],'material':material},ensure_ascii=False)}]
def plain(content):return html.unescape(re.sub('<[^>]+>',' ',content))
def count_units(content,target):
    text=plain(content)
    if target.split('-')[0] in ('zh','ja','ko'):return len(re.findall(r'[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7afA-Za-z0-9]',text))
    return len(re.findall(r"\b[\w’'-]+\b",text))
def validate(content,title,thin,target,allow_editorial_warnings=False):
    text=plain(content)
    if target.split('-')[0] in ('en','id','vi','pt','es') and len(re.findall(r'[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]',title))>3:raise ValueError('TITLE_LANGUAGE_MISMATCH')
    if not allow_editorial_warnings and re.search(r'#{2,}|\*\*|```|\[[^\]]+\]\(https?://|(?:^|\n)\s*- ',text):raise ValueError('MARKDOWN_RESIDUE')
    if not allow_editorial_warnings and re.search(r'素材|搜索结果|搜尋結果|未能确认|未能確認|可用信息|materials provided|search results|could not be confirmed|未确定|未確定|现有报告未说明|現有報告未說明|我查到|可用范围|可用範圍|信源分歧|资料不全|資料不全|全文尚未|唯一能查到|coverage discrepancies|available (?:information|scope|material|sources)|sources? (?:disagree|conflict)|only information (?:available|I)|(?:report|source) does not (?:specify|provide)|could not (?:confirm|verify)|informasi yang tersedia|belum (?:dapat )?dikonfirmasi|sumber yang tersedia|確認できていない|入手できる情報|資料の限界|未確認の部分|확인되지 않은 부분|자료가 부족|확인할 수 있는 정보',text,re.I):raise ValueError('META_NARRATION')
    if re.search(r'(?i)\btrade less\b|\brewards patience\b|\b(?:confirm|check|review) (?:your )?(?:margin requirements|overnight financing|position sizes)|\b(?:you|traders|investors|readers) (?:should|must) (?:buy|sell|hedge|diversify|adjust (?:your |their )?positions)',text):raise ValueError('INVESTMENT_ADVICE')
    headings=len(re.findall(r'<h[23]\b',content,re.I))
    if headings>4:raise ValueError('TOO_MANY_HEADINGS')
    units=count_units(content,target)
    return units
