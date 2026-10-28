# WikiFX Signal Cloud 维护交接

交接日期：2026-10-28（Asia/Shanghai）。仓库：`hitechhamster/wikifx-user`。
本次只整理、校验并提交交接快照，没有部署、停止采集或修改线上数据库。
应用户最终确认，目标仓库使用 public；任何密钥和生产业务数据均不属于本仓库。

## 线上基线

- Worker：`wikifx-signal-hub`，100% 线上版本 `41c16e8e-7ba2-43b4-88af-ccb71839f2b0`，部署于北京时间 2026-10-27 18:08:44。
- 审核页：<https://review.wikifxusers.com/>。目前公开访问，审核人为自填姓名，不是身份认证。
- 正式接收：`POST https://hotspots.wikifxusers.com/api/v1/hotspots/daily-batches`，按来源 Token 鉴权。
- 测试接收：同一路径，域名 `hotspots-test.wikifxusers.com`，独立测试 D1。
- `SUBMISSION_MODE=live`、`WRITER_READY=true`，每天生成上限 100、送稿上限 60；IP 每分钟最多 10 次送稿操作。
- `wrangler.corrections-deploy.json` 是当前线上对应的固定镜像配置。交接时本地 dry-run Worker bundle 与从 Cloudflare 下载的线上 bundle SHA-256 完全相同，见 `docs/deployment-snapshot.json`。
- 写稿镜像：`sha256:eb2d86be8ebd746aaa16cb39e8ffa7db5eec1bba67c53d0ab374f99df0b819ec`。
- 采集镜像：`sha256:200626b9479ca4b3a31c04f49b88671fcf81aed31139555495d23e2df44c8ae2`。
- 交接时 Docker Desktop 引擎未运行，因此没有重新构建镜像；保留线上固定 digest，避免误换镜像。两个镜像的完整项目源码及 Dockerfile 均提交。Python 基础镜像及 pip 依赖未全部锁定 digest/version，未来 rebuild 不保证二进制相同。

## 项目结构与职责

| 路径 | 职责 |
| --- | --- |
| `src/index.ts` | 路由、静态资源、Coordinator、串行状态修改、Cron 分发 |
| `src/ingest.ts`、`protocol.ts` | 双来源接收、分页、幂等、修订版本与回执 |
| `src/ai.ts`、`material.ts`、`editorial.ts` | 地区预选、中文标题、规则过滤和结构化理由 |
| `src/enrich.ts`、`verify.ts`（若有） | 正文及搜索佐证、传闻核实、调用预算 |
| `src/pipeline.ts` | Workflows 编排、写稿容器、AI 审核及异步任务 |
| `src/actions.ts`、`review.ts` | 选题/审稿/已送稿三阶段，审批版本绑定与额度 |
| `src/delivery.ts`、`article-sources.ts` | Content Hub 请求、错误分类、幂等与默认来源附录 |
| `src/images.ts` | 公司图片任务、语言门槛、3 并发、R2 存图及送稿附件 |
| `src/collector.ts`、`collector/` | Containers 采集；legacy 为杭州 Python 采集与配置的迁移副本 |
| `container/` | Flask/Waitress 写稿容器，DeepSeek Flash、HTML、语言校验、事实核查和 AI 审核 |
| `public/` | 审核页；乐观勾选与后台保存、全文审稿、图片和送稿进度 |
| `migrations/` | D1 建表及升级，包括历史记录、三阶段审核、修正版、头图 |
| `tests/`、`container/test_*.py`、`collector/test_collector.py` | 本地规则及协议测试 |
| `scripts/` | 运维、迁移、对比和历史一次性操作脚本；不能批量执行 |
| `docs/prompts/` | 最新写稿、预选、AI 审核 prompt 的可读导出；运行源码才是唯一权威 |
| `OPERATIONS.txt` | 按时间追加的运维记录，开头的旧状态不代表当前状态 |

写稿 prompt 权威文件是 `container/writer-prompt.md`，system/user 组装见 `container/news_policy.py`；预选 prompt 在 `src/ai.ts`；AI 审核 prompt 在 `container/ai_audit.py`。均使用 DeepSeek Flash，写稿 temperature 0.3，预选与审核 0.2。OpenRouter/Claude 方案已取消。

## Cloudflare 资源

| Binding/资源 | 名称 |
| --- | --- |
| Worker | `wikifx-signal-hub` |
| DB | `wikifx-signal-hub`，ID `a3b7d718-0ef1-4db0-81e0-bcd562663f15` |
| TEST_DB | `wikifx-signal-acceptance`，ID `2373de8f-6018-4551-8a8f-e891ee1d7002` |
| ARCHIVE | R2 `wikifx-signal-archive` |
| PIPELINE | Workflow `wikifx-signal-pipeline` |
| COORDINATOR | Durable Object `Coordinator` |
| WRITER | Durable Object/Container `ArticleContainer`，最多 2 实例 |
| COLLECTOR | Durable Object/Container `CollectorContainer`，最多 1 实例 |

Cloudflare account ID、database ID、镜像 digest 是资源标识，不是访问凭据。D1 的业务行、settings、任务和稿件状态不在 Git；R2 的原始文件、素材、稿件、图片与回执也不在 Git，需单独授予新维护人员账户访问。

R2 主要目录：`cloud/YYYY-MM-DD/`、`hangzhou/history/`、`hangzhou/daily/`、`ai/`、`articles/<job>/`、`deliveries/<delivery>/`、`images/<id>/`、`comparisons/`、`manual-import/`。重新提交与重试前应检查数据库和既有回执。

## 本地准备与部署

需要 Node.js（测试使用 Node 24）、pnpm、Cloudflare 账户权限；构建两个容器还需要可运行的 Linux Docker 引擎。先检查脚本目标，避免测试连接生产。

```powershell
pnpm install --frozen-lockfile
node node_modules/wrangler/bin/wrangler.js login
node node_modules/typescript/bin/tsc --noEmit
node node_modules/tsx/dist/cli.mjs --test tests/*.test.ts
python -m unittest discover -s container -p "test_*.py"
python -m unittest discover -s collector -p "test_*.py"
```

Python 测试需要相应 requirements 依赖；可在写稿/采集镜像中执行。部分集成脚本要求先启动本地 Wrangler 并设置测试假 Token，不可直接指向线上。`tests/example.json` 是协议样例。

```powershell
# 只打包验证，不上传或发布
node node_modules/wrangler/bin/wrangler.js deploy --dry-run --config wrangler.corrections-deploy.json --outdir .handover-local/build
# 同账户 Worker/前端更新，两个线上镜像保持固定
node node_modules/wrangler/bin/wrangler.js deploy --config wrangler.corrections-deploy.json
# 更新写稿容器，采集镜像保持固定
node node_modules/wrangler/bin/wrangler.js deploy --config wrangler.writer-deploy.json
# 完整构建两个容器：确认采集改动范围后再用
node node_modules/wrangler/bin/wrangler.js deploy --config wrangler.jsonc
# D1 迁移：先备份，确认迁移范围后执行
node node_modules/wrangler/bin/wrangler.js d1 migrations apply wikifx-signal-hub --remote
```

交接快照不会自动触发 GitHub Actions 或部署。新账户部署需要修改资源 ID、域名和镜像 registry；原账户只需正确授权。现有 wrangler 配置是 live 模式，不要在不知情的情况下连生产运行迁移、送稿或一次性脚本。

## Secrets（只列名称）

2026-10-28 只读查询线上 Secret 名称：

| 名称 | 用途 |
| --- | --- |
| `DEEPSEEK_API_KEY` | 预选、翻译、写稿、AI 审核、采集 AI |
| `APIFY_TOKEN` | 社媒采集 |
| `SERPER_API_KEYS` | 多 Key 英文逗号分隔、证据搜索 |
| `RADAR_INGEST_TOKEN` | 对方来源接收鉴权 |
| `SIGNAL_INGEST_TOKEN` | 自有采集推送和内部归档鉴权 |
| `CONTENT_INGEST_TOKEN` | Content Hub 真实收稿 |
| `AIGC_API_KEY` | 公司图片接口 |
| `OPENROUTER_API_KEY` | 历史遗留，当前代码不使用；删除需先获维护负责人确认 |

配置每个变量时使用 `node node_modules/wrangler/bin/wrangler.js secret put <名称> --config wrangler.corrections-deploy.json`，由负责人在交互提示中输入值。新维护人不应把值写入命令参数、代码、文档或截图。`secret list` 只能用于核对名称；无需导出线上值。杭州 SSH 凭据不在 Cloudflare，也不在本仓库。

## 定时任务与数据流

- Cron `0 1 * * *`：UTC 01:00 / 北京时间每天 09:00，自有采集串行跑 global、india、pakistan、indonesia。global→MY，india+pakistan→SA，indonesia→ID，通过同一接收协议推送。
- Cron `* * * * *`：每分钟分发已入队任务和清理限流记录，不是每分钟采集。
- 任何来源到达即触发对应地区预选，晚到数据可重排未处理 candidate；已生成等条目不会被覆盖。没有另加 09:40 的独立 Cron。
- 17 个地区和目标语言在 `src/regions.ts`。AU/SG/NA/EU 未安排采集。MY 接受马来西亚本地及重大全球外汇新闻；地区与跨区数量门槛另见 ai.ts。
- 候选默认不勾选。`candidate → generating/draft → approved → sending → sent/failed`；draft 不得送出。审批绑定生成版本。
- Content Hub 200/201 成功后保存 data.id；400 不重试，401 暂停并查 Token；500/超时最多 3 次额外重试，同 externalId 和冻结 payload。这里的 sent/published 表示已收稿，最终发布由编辑控制。
- 传闻、资料不足和事实核查提示需人工判断。生成计数和送稿计数不同，失败也可能占额度，不能改 ID 绕过限额。

## 已知问题和待办

1. 审核域名目前公开。可在 Cloudflare 后台为域名启用 Access；审核人只是自填字符串，不能当身份审计。接收域名继续 Token 鉴权。
2. 程序化核查仅匹配素材，存在误报和漏报；AI 审核也会误判归因、同义改写。模型仍偶有语言夹杂、元叙述、无依据推断，送稿前应人工通读。不能将“0 标黄”解释为新闻真实。
3. 公司图片自动检测语言实测 ko/id/zh-HK/en 可用；th/ar/ja/vi/pt/es 曾输出英文。D1 `image_language_*` 门槛控制默认配图。人工核验图片使用 `manual-verified:` 触发标识，只对该张图放行，不代表公司接口该语言已修复。图片在 R2，不在源码仓库。
4. 2026-10-27 最后 12 篇重投 ID 为 248–259，均 201。底部 Sources/来源标题和列表已通过一次性脚本删除，正文中的信源归因与头图保留。**默认新稿路径仍会调用 `referenceFooter()` 附加来源列表**，本次是 12 篇数据修订，不能误报为全系统已永久关闭来源附录。若需要永久变更，应另行改代码、测试、部署。
5. 旧 Content Hub 稿件未被本系统撤回或删除。修正版与多次重投有新的 externalId，旧稿清理由编辑负责。不可批量重跑 scripts 中的 historical resend、迁移、secret 修改、导入或配图脚本。
6. ID“印尼盾 18,108”曾退回选题；按用户后续明确授权，重投使用其原稿正文，只删除底部来源区并配图。因此它仍可能包含旧版元叙述，不能当作最新 prompt 的合格样例。
7. 杭州 09:00 采集、8091、18082 和 SEO Copilot 保留。至少三天并行比对及最终停机需要用户确认；交接时没有停用。对比为本机 `python scripts/compare-daily.py --date YYYY-MM-DD`，通过现有本机 SSH 只读拉取杭州 daily 并上传报告到 R2；没有云端杭州凭据。尚不能确认三天全部完成。
8. Workflow describe 偶有 10001/internal_server；先查数据库、R2 回执和调用记录，再决定重试，避免重复付费。
9. `OPERATIONS.txt` 是历史日志，内有旧 dry_run、旧配额和旧推荐策略，当前状态以本文、配置和线上查询为准。生产数据和人工修改不会通过 clone 自动恢复。

## 交接核验与保密

`.gitignore` 排除 node_modules、.wrangler、artifacts、outputs、.env/.env.*、.dev.vars*、SQLite、归档、日志和私钥文件。提交前对实际候选/暂存文件做密钥模式扫描，并人工核对测试假 Token；不将本地 Git 历史迁入新仓库。
GitHub main 保存交接快照；无部署提交的 commit 标注是因为本次明确不部署。源码与线上 Worker bundle 的 SHA-256 对照、静态文件 hash、镜像 digest 在 `docs/deployment-snapshot.json`，可由下一位维护者复核。
