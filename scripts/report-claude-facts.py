import json,html,re
from pathlib import Path
root=Path('artifacts/claude-facts');rows=json.loads((root/'old-audit.json').read_text(encoding='utf-8'));old=json.loads((root/'before.json').read_text(encoding='utf-8'));status=json.loads((root/'sample-status.json').read_text(encoding='utf-8'))
parts=['<!doctype html><meta charset="utf-8"><title>Claude 写稿迁移与事实提示验收</title><style>body{font:16px/1.7 system-ui;max-width:1100px;margin:32px auto;padding:20px;background:#f6f7fa}section{background:white;padding:24px;margin:20px 0;border-radius:12px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;text-align:left}mark{background:#ffe681}summary{cursor:pointer}h1{font-size:26px}</style><h1>Claude 写稿迁移：接口失败，重生成尚未完成</h1><p>部署版本：8d8fb7dd-82e1-4e90-ba57-d29007d83a7e。写稿已改 OpenRouter anthropic/claude-sonnet-5.5，temperature=0.3；预选仍用 DeepSeek。Key 只读检查成功且有额度。生成上限已恢复100。</p><p>25篇目标稿件已备份。首批4篇未成功，其余21篇未启动。未送出任何稿件；13篇原送稿不变，13篇修正版仍锁定待编辑确认。</p><table><tr><th>地区</th><th>结果</th><th>新稿/核查数/单篇费用</th></tr>']
for x in status:parts.append(f'<tr><td>{x["region_code"]}</td><td>{html.escape(x.get("error") or x["review_state"])}</td><td>无成功新稿；不提供虚构全文或核查数量。403请求未返回token用量，系统记录估算0，不等于供应商账单核验。</td></tr>')
parts.append('</table><section><h2>事实匹配的范围</h2><p>只使用该条标题、摘要、正文、佐证文字；数字归一化覆盖常用千分位、小数、规模单位和日期格式。名称由确定性规则、别名字典识别，不调用AI。名称提取和跨语言匹配仍可能漏报、误报；数值存在也不能证明归因或因果关系正确，因此黄色提示不是“已证实的幻觉”。高亮不阻止通过，不写入Content Hub正文。</p><p>测试：28项TypeScript测试、9项写稿测试、3项数字匹配测试通过；浏览器验证跨标签数字与Unicode偏移，未执行注入脚本。</p></section><section><h2>旧稿中需要核对的实例</h2><ul><li>MY旧稿中的 Bank Negara Malaysia：本条欧央行报道素材未出现此机构，背景解读引入了素材外名称。</li><li>LA旧稿中的 Ministerio de Economía：素材未找到该机构名称，需要人工核对。</li><li>SA旧稿中的 Finance Minister Nirmala Sitharaman：现有素材未找到完整人物名称，需要核对。</li></ul><p>这些是素材依据不足的提示，不能直接认定事实为假。对原文确有依据的日文30年、Rp18.110及Dh771,330，匹配修正后不再误报。</p></section>')
for r in rows:
 parts.append(f'<section><h2>{r["region"]} · {html.escape(r["title"])}</h2><p>旧稿提示 {r["check"]["count"]} 处</p><ul>')
 for f in r['check']['findings']:parts.append(f'<li>{f["field"]}：<mark>{html.escape(f["text"])}</mark> — {f["reason"]}</li>')
 parts.append('</ul></section>')
(root/'report.html').write_text(''.join(parts),encoding='utf-8')
