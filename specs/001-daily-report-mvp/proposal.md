# 项目提案（proposal.md）：智能日报生成器 v1（MVP）

> 编号：001　|　版本：v1.0　|　状态：评审中　|　作者：项目组　|　评审人：项目组 / 指导教师　|　更新日期：2026-11-27
> 关联：`specs/001-daily-report-mvp/design.md`、`tasks.md`；项目级提案 `proposal.md`（仓库根目录）；需求澄清 `docs/需求澄清报告.md`

## 1. 项目名称与一句话描述

- **项目名称**：智能日报生成器 v1（daily-report-mvp）
- **一句话描述**：一线员工下班前通过飞书登录，系统自动采集当天飞书日历、云文档、任务与 GitHub 提交，生成可追溯的四段式日报草稿；员工编辑确认后一键推送至飞书，团队负责人查看不含排名的团队汇总。

## 2. 背景与目标

### 2.1 背景

| 编号 | 痛点 | 现状 | 影响 |
|---|---|---|---|
| P-01 | 写日报耗时 | 员工每天花 10–30 分钟回忆、翻记录、组织语言 | 无效工时累积，临近下班时抵触情绪强 |
| P-02 | 数据来源分散 | 日历、文档、任务、代码提交分布在飞书与 GitHub 等系统 | 凭记忆汇总容易漏项，日报不完整 |
| P-03 | 格式不统一 | 各人各写，四段式模板靠自觉执行 | 管理者汇总、检索、对比成本高 |
| P-04 | 内容形式化 | 缺少事实支撑，容易写成流水账或套话 | 日报失去过程管理价值 |
| P-05 | 隐私与信任顾虑 | 员工担心采集数据被用于绩效考核或行为监控 | 抵触使用，或敷衍填写 |

### 2.2 目标

| 编号 | 目标 | 度量口径 | 关联成功标准 |
|---|---|---|---|
| G-01 | 打通「采集 → 生成 → 编辑确认 → 推送 → 团队汇总」闭环 | Mock 模式一次流水线产出日报、条目、推送记录；重复执行幂等 | SC-01～SC-08 |
| G-02 | 降低员工写日报的时间成本 | 单份日报生成 P95 ≤ 5 秒；确认操作 ≤ 2 步 | SC-10、SC-11 |
| G-03 | 日报内容真实、可追溯 | 自动写入条目 100% 带 `source_event_ids`；无来源条目不进入草稿 | SC-04 |
| G-04 | 负责人快速掌握团队进展 | 汇总只含已提交日报与阻塞项，不出现排名或评分 | SC-08 |
| G-05 | 数据最小必要、可审计、密钥安全 | 越权访问返回 403；审计只存元数据；仓库无真实密钥 | SC-09、SC-26 |

## 3. 范围

### 3.1 做什么（本期范围）

> 本文件使用 R-xx 编号；`design.md` 第 2 节「对应提案条目」沿用项目级 `proposal.md` §5 的 P0/P1 描述，二者对应关系见本节表格的「设计承接」列。

| 编号 | 范围条目 | 说明 | 优先级 | 设计承接 |
|---|---|---|---|---|
| R-01 | 飞书 OAuth 2.0 登录与成员建档 | 通过企业自建应用授权换取 `open_id`，首次登录自动建成员，签发会话 JWT；支持前端授权跳转 | P0 | `orchestrator/api`、`auth` |
| R-02 | 飞书日历采集 | 拉取当天本人为组织者/参会人的日程及参会人，映射为 `WorkEvent` | P0 | `collectors/feishu_calendar` |
| R-03 | 飞书云文档元数据采集 | 拉取当天编辑过的云文档标题、协作者与最后编辑时间，不下载正文 | P0 | `collectors/feishu_doc` |
| R-04 | 飞书任务采集 | 拉取当天任务变更与负责人，只读，不修改任务状态 | P0 | `collectors/feishu_task` |
| R-05 | 多源聚合、去重与协作归属 | 按 `(source, source_id)` 去重；按 owner/协作者/参会人/reviewer 计算归属与置信度，分为自动写入、待确认、丢弃 | P0 | `generation/aggregator`、`generation/attribution` |
| R-06 | 四段式 AI 日报生成与降级 | 「今日完成 / 进行中 / 风险与阻塞 / 明日计划」四段；模型只改写事实；Schema 校验、无来源剔除、失败降级模板 | P0 | `generation/builder`、`generation/llm`、`generation/validator` |
| R-07 | 草稿编辑、确认提交与版本快照 | 本人可查看/编辑/提交草稿；提交生成版本快照；非草稿状态不可编辑；他人不可操作 | P0 | `orchestrator/api`、`storage` |
| R-08 | 飞书推送与推送幂等 | 推送个人消息卡片；同一幂等键不重复发送；失败保留记录并可定位 | P0 | `publishers/feishu` |
| R-09 | 权限隔离、审计与密钥管理 | 本人/直属负责人数据边界；审计只记元数据；密钥仅环境变量注入，日志脱敏 | P0 | `orchestrator/api`、`audit`、`storage` |
| R-10 | 流水线幂等与定时调度 | `run_key` 保证同日同范围只成功执行一次；工作日 17:30 生成、17:45 汇总；单成员失败隔离 | P0 | `orchestrator/pipeline`、`orchestrator/scheduler` |
| R-11 | GitHub commit / PR 采集 | 白名单仓库指定时间窗内的 commit 与 PR；支持 ETag 增量与显式 `GITHUB_LOGIN` 匹配 PR 作者 | P1（本期交付） | `collectors/github` |
| R-12 | 团队汇总（最小版） | 负责人查看直属成员日报汇总与阻塞项；只聚合已提交日报；不生成排名 | P1（本期交付） | `orchestrator/pipeline`、`rollup`、`orchestrator/api` |

### 3.2 不做什么（本期明确排除）

| 编号 | 排除项 | 排除理由 | 后续计划 |
|---|---|---|---|
| N-01 | 邮件推送 | 飞书推送已覆盖主流程；SMTP 配置与退信处理会增加运维成本，需求澄清 Q-09 将邮件列为 P2 | 保留 `EmailPublisher` 与 `E-PUSH-010` 协议；教师确认必做后接入服务装配 |
| N-02 | 群聊消息采集 | 闲聊与敏感信息多，「谁贡献了什么」难以可靠归属，隐私风险高于收益（Q-01） | P2 再议；若纳入，按「仅本人相关消息 + 逐条可排除」执行 |
| N-03 | 周报 / 月报 | 依赖稳定的日报数据积累，首期先保证日报闭环 | 阶段二基于日报聚合 |
| N-04 | 模板管理与自由模板编辑器 | 首期固定四段式 + 字段开关已满足验收（Q-12） | P2 提供团队模板配置 |
| N-05 | Jira / 禅道适配 | 课程周期内无真实系统可联调，接口收益低 | 保留 `Collector` 适配接口，按需新增实现 |
| N-06 | 绩效排名、行为监控、考勤统计 | 产品信任底线：日报不用于绩效考核与排名（Q-17） | 永久不做；审计与汇总明确标注 |
| N-07 | 请假 / 出差 / 节假日自动识别 | 依赖飞书审批数据源，未纳入本期采集契约（Q-05） | 接入审批数据后按工作日历生成；本期由员工手动跳过或补写 |
| N-08 | 独立「采集预览」页与逐条排除 | 本期草稿条目已展示来源 ID 且可编辑/删除，独立预览页需要新增契约与 UI | 评审若要求，按 H-01 增补预览接口与页面（开放问题 O-03） |
| N-09 | 提交后撤回、版本对比 / 回滚 UI | 本期只落版本快照，不提供撤回与对比接口（Q-08 的 24 小时 / 10 版本为建议值） | 阶段二实现撤回、diff 与回滚 |
| N-10 | 多语言、多时区 | 首期中文 + `Asia/Shanghai`，跨时区团队不在验收范围（Q-13） | 时区/工作日历可配置化后扩展 |
| N-11 | 移动端原生 App | 飞书消息卡片 + H5 已覆盖移动场景（需求澄清附录 X-02） | 不做 |
| N-12 | 部门 / HR 周期导出与归档 | 本期交付个人日报与团队汇总，未设计导出契约（Q-11） | 阶段二提供 CSV/Excel 导出与归档 |
| N-13 | 历史数据自动清理任务 | 保留期策略已确认但未实现定时清理，避免误删风险 | 与隐私政策一起上线（O-05） |

## 4. 技术约束

| 类别 | 约束内容 | 来源 / 依据 |
|---|---|---|
| 语言与运行环境 | Python ≥ 3.12、uv 管理依赖；前端 Node.js + Vue 3 + TypeScript + Vite | `pyproject.toml`、`web/package.json` |
| 框架与库 | FastAPI、SQLAlchemy 2.0、Alembic、httpx（异步 + `MockTransport`）、Celery[redis]、PyJWT、pydantic-settings | `pyproject.toml`、`design.md` ADR-001/003/004 |
| 数据库与存储 | SQLite 单文件 `data/daily_report.db`，开启 WAL、`busy_timeout=5000`、外键约束；Redis 7 作为 Celery broker/backend | `design.md` ADR-002、`.env.example` |
| 外部系统与凭证 | 飞书企业自建应用 OAuth（日历只读、文档元数据、任务只读、消息发送）；GitHub REST v3 只读 PAT；DeepSeek `deepseek-chat`，经 `LLMProvider` 可切换 | `design.md` §6、`.env.example` |
| 部署与运行 | 单机 Docker Compose；API 服务、Celery Worker/Beat、Redis；`data/` 目录随项目可复制 | `design.md` §1.2 |
| 合规与安全 | 密钥仅环境变量注入，仓库只保留 `.env.example`；审计不存日报正文；日志脱敏；SQL 参数化/ORM；最小权限 scope | `design.md` §6、`docs/需求澄清报告.md` Q-11/Q-17 |
| 持续集成 | GitHub Actions 执行 `ruff check`、`mypy src`、`pytest -q` 与密钥扫描 | `.github/workflows/ci.yml` |
| 数据库口径说明 | 需求澄清 C-06 曾建议 PostgreSQL；`design.md` ADR-002 与当前实现最终选择 SQLite，本提案以设计 ADR 为准 | `design.md` ADR-002、O-10 |

## 5. 成功标准

### 5.1 功能验收

| 编号 | 成功标准 | 验证方式 |
|---|---|---|
| SC-01 | 飞书 OAuth 回调成功换取会话并自动建成员；同一 `open_id` 重复登录不产生重复成员 | `tests/test_api.py::test_oauth_callback_creates_member`、`tests/test_feishu_oauth.py` |
| SC-02 | 日历、云文档、任务三个采集器均能解析响应并过滤到指定时间窗；Mock 全链路产出 4 条事件（四源各 1 条） | `tests/test_collectors_feishu.py`、`tests/test_pipeline.py` |
| SC-03 | GitHub 只采集成员本人的 commit 与 PR；ETag 304 跳过重复拉取；`GITHUB_LOGIN` 可显式匹配 PR 作者 | `tests/test_collectors_github.py` |
| SC-04 | 聚合按 `(source, source_id)` 去重并按时间排序；归属分为 auto / pending / dropped；草稿固定四段，auto 条目 100% 带来源事件 ID | `tests/test_generation.py`、`tests/test_pipeline.py` |
| SC-05 | 本人可编辑草稿条目；他人操作返回 403；已提交/已推送不可编辑（409）；提交写入版本快照，重置后再次提交版本号递增 | `tests/test_api.py` |
| SC-06 | 提交后可推送飞书卡片；同一幂等键不重复发送；推送失败返回 502 且保留 `push_record(failed)` 与错误详情 | `tests/test_publishers.py`、`tests/test_api.py::test_push_failure_persists_record_and_detail` |
| SC-07 | 同一成员同一天重复运行流水线返回 `skipped`，不重复生成或推送；全员流水线单成员失败标记 `partial`；Beat 工作日 17:30 / 17:45 可配置 | `tests/test_pipeline.py`、`src/daily_report/celery_app.py` |
| SC-08 | 团队汇总只聚合 `submitted/pushed` 日报，未提交成员显示「未提交」，内容不含排名；仅团队负责人可访问 | `tests/test_pipeline.py::test_team_rollup_contains_no_ranking`、`tests/test_api.py` |
| SC-09 | 未携带令牌返回 401，越权访问返回 403；审计日志只存操作元数据；密钥只从环境变量读取，日志中的令牌/邮箱被脱敏 | `tests/test_api.py`、`tests/test_errors_audit.py`、`tests/test_config_logging.py` |

### 5.2 性能验收

| 编号 | 指标 | 目标值 | 测量方法 |
|---|---|---|---|
| SC-10 | 单份日报生成耗时（不含人工编辑） | P95 ≤ 5 秒 | Mock 全链路计时；真实环境在 T-32 联调时补测 |
| SC-11 | 员工确认操作步数 | ≤ 2 步（打开日报 → 提交） | 管理端演示路径；`tests/test_api.py::test_report_flow` |
| SC-12 | 50 人团队全量流水线 | ≤ 3 分钟 | 压测脚本 / 多成员 Mock 运行；当前未执行（见 T-31） |
| SC-13 | 采集成功率 | ≥ 95% | 任务日志与 `pipeline_run.stats_json`；需真实凭证或试点数据 |
| SC-14 | 单源采集超时与重试 | 单源超时 10 秒；429/超时最多重试 3 次、指数退避；4xx 不重试 | `tests/test_http.py` |

### 5.3 边界与异常场景

| 编号 | 场景 | 期望行为 |
|---|---|---|
| SC-20 | 当天没有任何可采集数据 | 生成空草稿并落库，不推送，流水线状态为成功 |
| SC-21 | 单个采集源返回 401/403 | 隔离该源并记录错误，其它源继续，日报仍可生成 |
| SC-22 | 采集遇到 429 或超时 | 按 `Retry-After`/指数退避重试，达到上限后返回可定位错误，不无限等待 |
| SC-23 | 模型超时、限流或返回非法 JSON | 降级为事实模板，`degraded=true`，不阻断草稿生成与提交 |
| SC-24 | 飞书推送失败 | 保留 `push_record(failed)` 与错误详情，流水线标记 `partial`，接口返回 502 |
| SC-25 | 重复触发流水线或重复推送 | 按 `run_key` 与幂等键去重，不生成重复日报、不重复发送 |
| SC-26 | 访问他人日报或非负责人访问团队汇总 | 返回 403，不泄露数据 |
| SC-27 | 缺少 `APP_SECRET_KEY` | 启动即失败并提示配置项，不使用默认密钥 |
| SC-28 | 对已提交/已推送日报再次编辑 | 返回 409，提示当前状态不可编辑 |
| SC-29 | 飞书授权 scope 不足 | 返回 401 并在错误信息中附带 scope 提示，便于管理员补授权 |

## 6. 术语定义

| 术语 | 定义 |
|---|---|
| 日报草稿 | 系统生成、尚未提交的日报，可编辑、可提交；状态为 `draft` |
| WorkEvent | 采集层输出的标准化工作事实，按 `(source, source_id)` 唯一 |
| 归属 | 把协作成果映射到具体成员的过程，结果分 auto / pending / dropped |
| 置信度 | 0–1 的归属可信程度；≥0.9 自动写入，0.5–0.9 待确认，<0.5 丢弃 |
| 待确认条目 | 中置信度条目，`confirmed=false`，在草稿中由员工确认或调整 |
| 四段式 | 今日完成 / 进行中 / 风险与阻塞 / 明日计划 |
| 降级 | 模型失败时回退到基于事实的模板草稿，保证日报可提交 |
| 幂等键 | 推送去重键（`report_id + version + channel + target`），重复调用不重复发送 |
| `run_key` | 流水线运行键（`date:member:<id>` / `date:daily:<scope>`），保证同范围只成功执行一次 |
| Mock 模式 | `MOCK_MODE=true` 时使用内存假采集器与记录型推送器，不访问外部系统 |

## 7. 开放问题

| 编号 | 问题 | 影响范围 | 负责人 | 状态 |
|---|---|---|---|---|
| O-01 | 飞书自建应用的 scope 清单与审批周期；测试企业是否可用 | R-01～R-04、T-32 | 配置管理员 | 待确认 |
| O-02 | 真实联调所需飞书应用、GitHub PAT、DeepSeek Key 的提供时间 | SC-10、SC-13、T-32 | 项目负责人 | 待确认 |
| O-03 | 独立采集预览页、逐条排除与「未确认条目提交拦截」是否为本期验收必需（H-01/H-02） | R-05、R-07、T-33 | 项目组 | 待确认 |
| O-04 | 提交后撤回、版本对比/回滚的交付批次（Q-08 的建议值） | N-09 | 项目组 | 待排期 |
| O-05 | 数据保留期自动清理与隐私政策文本 | N-13、合规 | 项目组 | 待编写 |
| O-06 | 团队汇总最小版是否强制纳入本期验收（Q-18/O-06） | R-12 | 项目负责人 | 待确认 |
| O-07 | 产品类指标（提交率、采纳率、编辑占比、节省时间）需试点数据，本地验收按 N/A 处理 | SC-11～SC-13 | 项目负责人 | 已确认口径 |
| O-08 | `design.md` §4.5 接口清单需补 `/api/me`、`/api/health`、`/api/oauth/feishu/login-url`、`/api/reports/{date}/generate` | 规格一致性 | 架构师 | 待同步（T-34） |
| O-09 | 邮件推送是否由教师确认为必做项（Q-09/O-01） | N-01 | 项目负责人 | 待确认 |
| O-10 | 数据库最终口径：`design.md` ADR-002 选择 SQLite，需求澄清 C-06 曾建议 PostgreSQL | 技术约束、答辩 | 指导教师 | 待确认 |

## 8. 变更记录

| 日期 | 版本 | 变更内容 | 作者 |
|---|---|---|---|
| 2026-11-27 | v1.0 | 初稿：按 v1 实现补档，明确 R-01～R-12、13 条排除项、SC 成功标准与开放问题 | 项目组 |

## 9. 自查清单

- [x] 每条范围条目（R-xx）都有对应成功标准（SC-xx），映射见 `tasks.md` 第 4 节
- [x] 「不做什么」不少于 3 条，且每条有理由与后续计划（N-01～N-13）
- [x] 成功标准全部可度量，验证方式指向测试、命令或人工演示
- [x] 技术约束与 `design.md` 的 ADR 结论一致（SQLite、httpx、LLMProvider、Celery）
- [x] 与根目录 `proposal.md`、`docs/需求澄清报告.md` 的 P0/P1 口径一致；差异项已列入开放问题
