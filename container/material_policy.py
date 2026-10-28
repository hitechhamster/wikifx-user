"""Thin-material policy, independent of network and model clients."""
import re
from urllib.parse import urlparse
def writing_material(item):
    material={k:item.get(k) for k in ('title','summary','sources','url','source_name','content_status')}
    material['type']='social' if urlparse(item.get('url','')).hostname in ('twitter.com','x.com','www.reddit.com','reddit.com','facebook.com','www.facebook.com','instagram.com','t.me','tiktok.com') else 'news'
    thin=item.get('content_status')=='unavailable'
    if item.get('content_status') in ('full','partial'):material['content']=item.get('content')
    return material,thin
def short_enough(body):
    return len(re.findall(r'[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]',body))<=220 and len(body.split())<=120
THIN_INSTRUCTION='''
以下短讯要求覆盖前文全部常规篇幅要求：本条正文不可用且没有搜索佐证，资料不足。只准使用本条原始标题和摘要，其他来源列表已移除。只写1—2个短段落，最多100词（中日韩语最多180字），素材只有标题时允许仅1—2句话。不得扩写背景、时间、人物、原因、影响或建议；不可用常识补足。不要生成小标题。非空摘要只能忠实压缩同样的已知信息，不引入新事实。保留原题中的传闻/预测/条件限定，存在矛盾就归因给报道标题，不自行修正。
'''
