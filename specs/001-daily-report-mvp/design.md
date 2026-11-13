# 系统设计（design.md）：智能日报生成器 v1

> 关联提案：`proposal.md`（仓库根目录）　|　关联记录：`docs/需求澄清报告.md`、`docs/架构与技术栈选型.md`
> 版本：v0.1　|　状态：评审中　|　作者：架构师　|　评审人：项目组　|　更新日期：2026-11-10

## 1. 系统架构

### 1.1 分层架构

系统按「采集层 → 生成层 → 推送层 → 主编排入口」四层构建：下层只暴露稳定契约，上层不得绕过编排层直接调用下层。依赖方向单向向下，采集层不感知生成与推送。

```
┌──────────────────────────────────────────────────────────────┐
│ 主编排入口                                                    │
│   FastAPI 接口（授权/草稿/确认/推送） · CLI 手动触发 ·         │
│   Celery Beat 定时调度 · 流水线状态机与幂等控制                │
├──────────────────────────────────────────────────────────────┤
│ 采集层（只读外部系统，产出标准化 WorkEvent）                    │
│   飞书日历 · 飞书云文档 · 飞书任务 · GitHub（commit/PR）       │
│   统一 Collector 协议 · 增量游标 · 限流 · 失败隔离             │
├──────────────────────────────────────────────────────────────┤
│ 生成层（事实 → 草稿）                                          │
│   聚合去重 → 协作归属 → 四段式草稿 → LLM 生成 → Schema 校验/降级│
├──────────────────────────────────────────────────────────────┤
│ 推送层（草稿/汇总 → 外部渠道）                                  │
│   飞书个人卡片 · 飞书群卡片 · 邮件（P2，预留接口）              │
└──────────────────────────────────────────────────────────────┘
                    SQLite（WAL）· Redis（队列/缓存）
```

**架构说明**：
1. 采用模块化单体，而非微服务：瓶颈在外部 API 调用（I/O 密集），拆分服务只会增加联调成本。
2. 四层之间只通过数据结构与函数契约交互，采集层结果统一为 `WorkEvent`，生成层不依赖任何平台的 SDK 类型。
3. 主编排入口负责幂等、重试、降级与状态流转，业务层不重复实现这些横切逻辑。
4. 外部系统通过适配器隔离，数据源可替换（开发期 mock 采集器与真实采集器实现同一协议）。

### 1.2 部署视图

| 组件 | 部署形态 | 依赖 | 说明 |
|---|---|---|---|
| API 服务 | uvicorn（Docker） | SQLite、Redis | 处理飞书 OAuth 回调、草稿编辑、确认与推送请求 |
| Worker | Celery Worker（Docker） | SQLite、Redis | 执行采集、生成、推送任务 |
| 调度器 | Celery Beat（Docker） | Redis | 每工作日 17:30 触发个人日报流水线，17:45 触发团队汇总 |
| 数据库 | SQLite 文件 `data/daily_report.db` | - | 开启 WAL、`busy_timeout`、外键约束 |
| 队列/缓存 | Redis 7 | - | Celery broker/backend、限流计数、LLM 结果缓存 |
| 管理端 | Vue 3 静态资源（Nginx） | API 服务 | 日报列表、权限与模板配置 |

> 部署要求：单机 Docker Compose；SQLite 文件与 `data/` 目录整体可拷贝，保证答辩环境可复现。

## 2. 模块职责

| 模块 | 所属层 | 职责边界（一句话） | 明确不负责 | 对应提案条目 |
|---|---|---|---|---|
| `orchestrator/pipeline` | 主编排 | 按「采集→生成→推送」顺序驱动单成员/团队流水线，控制幂等与状态流转 | 不实现采集、生成、推送的具体逻辑 | §5 P0 全流程 |
| `orchestrator/api` | 主编排 | 提供 OAuth 回调、草稿读写、确认提交、手动推送接口 | 不直接调用外部平台 API | §5 P0 登录与草稿编辑 |
| `orchestrator/scheduler` | 主编排 | 定义定时任务与重跑入口 | 不存放业务规则 | §5 P0 推送 |
| `collectors/github` | 采集 | 拉取白名单仓库指定时间窗内的 commit 与 PR，映射为 `WorkEvent` | 不做内容摘要、不做归属判定 | §5 P1 Git 采集 |
| `collectors/feishu_calendar` | 采集 | 拉取当天日程及参会人 | 不拉取会议纪要正文 | §5 P0 日历采集 |
| `collectors/feishu_doc` | 采集 | 拉取当天编辑过的云文档及协作者 | 不下载文档全文，只取元数据与标题 | §5 P0 文档采集 |
| `collectors/feishu_task` | 采集 | 拉取任务状态变更与负责人 | 不修改任务状态 | §5 P0 任务采集 |
| `collectors/base` | 采集 | 定义 `Collector` 协议、时间窗、结果结构与错误模型 | 不包含任何平台逻辑 | - |
| `generation/aggregator` | 生成 | 归一化、去重、按人聚合事件 | 不生成自然语言 | §5 P0 AI 生成 |
| `generation/attribution` | 生成 | 依据 owner/协作者/参会人/commit author 计算归属与置信度 | 不写入未经确认的低置信度项 | §5 P0 生成；澄清 Q-04 |
| `generation/builder` | 生成 | 组织四段式草稿（完成/进行中/风险与阻塞/明日计划） | 不调用模型 | §5 P0 AI 生成 |
| `generation/llm` | 生成 | 封装 `LLMProvider`，负责提示词、超时、缓存与降级 | 不校验业务语义 | §5 P0 AI 生成 |
| `generation/validator` | 生成 | Schema 校验、来源引用校验、空内容兜底 | 不修改用户已确认内容 | §5 P0 生成；澄清 Q-07 |
| `publishers/feishu` | 推送 | 发送个人/群消息卡片，处理幂等与重试 | 不组装日报内容 | §5 P0 推送 |
| `publishers/email` | 推送 | SMTP 发送（P2 预留，协议先定） | 一期不启用 | §5 P2 |
| `publishers/base` | 推送 | 定义 `Publisher` 协议、`PushResult` 与错误码 | - | - |
| `storage` | 共享基础 | SQLAlchemy 模型、迁移、事务与查询封装 | 不含业务规则 | - |

## 3. 数据模型

### 3.1 实体清单

| 实体 | 说明 | 关键字段 | 对应模块 |
|---|---|---|---|
| Member | 成员 | `open_id`、姓名、部门 | 全部 |
| Team / TeamMember | 团队与成员关系 | 团队、负责人、角色 | 团队汇总 |
| WorkEvent | 采集到的标准化工作事实 | `source + source_id` 唯一、发生时间、归属人、置信度 | 采集层 |
| EventParticipant | 协作关系（一个事件对多人） | 角色（owner/collaborator/reviewer/attendee）、置信度 | 生成层 |
| Report | 日报主实体 | 成员 + 日期唯一、状态、版本号 | 生成/推送 |
| ReportItem | 日报条目 | 所属段落、内容、来源事件、是否已确认 | 生成/推送 |
| ReportVersion | 日报历史快照 | 版本号、快照 JSON | 编辑/撤回 |
| PushRecord | 推送记录与幂等键 | 渠道、目标、状态、重试次数 | 推送层 |
| SyncCursor | 各数据源增量游标 | 数据源、范围、ETag/分页游标 | 采集层 |
| PipelineRun | 流水线运行状态 | 日期、状态、耗时、统计 | 主编排 |
| AuditLog | 审计日志（不含正文） | 操作人、动作、对象、结果 | 全层 |

### 3.2 日报实体与 SQLite 表结构

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE member (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    open_id     TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    email       TEXT,
    dept        TEXT,
    status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE team (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    lead_member_id  INTEGER REFERENCES member(id),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE team_member (
    team_id     INTEGER NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    member_id   INTEGER NOT NULL REFERENCES member(id) ON DELETE CASCADE,
    role        TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('lead', 'member')),
    PRIMARY KEY (team_id, member_id)
);

CREATE TABLE work_event (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL CHECK (source IN ('github', 'feishu_calendar', 'feishu_doc', 'feishu_task')),
    source_id       TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    owner_member_id INTEGER REFERENCES member(id),
    occurred_at     TEXT NOT NULL,
    title           TEXT NOT NULL,
    summary         TEXT,
    url             TEXT,
    confidence      REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    payload_json    TEXT NOT NULL DEFAULT '{}',
    collected_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source, source_id)
);

CREATE INDEX idx_work_event_member_time ON work_event (owner_member_id, occurred_at);

CREATE TABLE event_participant (
    event_id    INTEGER NOT NULL REFERENCES work_event(id) ON DELETE CASCADE,
    member_id   INTEGER NOT NULL REFERENCES member(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('owner', 'collaborator', 'reviewer', 'attendee')),
    confidence  REAL NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    PRIMARY KEY (event_id, member_id, role)
);

CREATE TABLE report (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id       INTEGER NOT NULL REFERENCES member(id),
    report_date     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'submitted', 'pushed', 'withdrawn')),
    template_version TEXT NOT NULL DEFAULT 'v1',
    version         INTEGER NOT NULL DEFAULT 1,
    generated_at    TEXT,
    submitted_at    TEXT,
    pushed_at       TEXT,
    UNIQUE (member_id, report_date)
);

CREATE TABLE report_item (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES report(id) ON DELETE CASCADE,
    section         TEXT NOT NULL CHECK (section IN ('done', 'doing', 'risk', 'plan')),
    content         TEXT NOT NULL,
    source_event_ids TEXT NOT NULL DEFAULT '[]',
    confidence      REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    confirmed       INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (0, 1)),
    sort_order      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_report_item_report ON report_item (report_id, section, sort_order);

CREATE TABLE report_version (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES report(id) ON DELETE CASCADE,
    version         INTEGER NOT NULL,
    snapshot_json   TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (report_id, version)
);

CREATE TABLE push_record (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES report(id) ON DELETE CASCADE,
    channel         TEXT NOT NULL CHECK (channel IN ('feishu', 'email')),
    target_type     TEXT NOT NULL CHECK (target_type IN ('user', 'chat')),
    target_id       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'sent', 'failed')),
    retry_count     INTEGER NOT NULL DEFAULT 0,
    provider_msg_id TEXT,
    error           TEXT,
    pushed_at       TEXT,
    UNIQUE (report_id, channel, target_type, target_id)
);

CREATE TABLE sync_cursor (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    scope_key       TEXT NOT NULL,
    cursor_value    TEXT,
    etag            TEXT,
    last_synced_at  TEXT,
    UNIQUE (source, scope_key)
);

CREATE TABLE pipeline_run (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_key         TEXT NOT NULL UNIQUE,
    run_date        TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('running', 'success', 'partial', 'failed')),
    stats_json      TEXT NOT NULL DEFAULT '{}',
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT
);

CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id        INTEGER,
    action          TEXT NOT NULL,
    object_type     TEXT NOT NULL,
    object_id       TEXT,
    result          TEXT NOT NULL,
    ip              TEXT,
    detail_json     TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_audit_log_time ON audit_log (created_at);
```

### 3.3 关键约束与理由

| 表 | 约束 | 目的 |
|---|---|---|
| `work_event` | `UNIQUE(source, source_id)` | 重复采集幂等，避免同一 commit 重复进日报 |
| `report` | `UNIQUE(member_id, report_date)` | 一人一天一份主日报 |
| `report_item` | `confidence` 低于阈值未 `confirmed` 不进入推送 | 协作归属可控（澄清 Q-04） |
| `push_record` | `UNIQUE(report_id, channel, target_type, target_id)` | 推送幂等，重试不重复发送 |
| `pipeline_run` | `run_key` 唯一（`date:team:member`） | 同一天同一范围只跑一次，可重跑覆盖 |
| `audit_log` | 不存日报正文 | 满足合规与最小必要（澄清 Q-11） |

### 3.4 ER 关系说明

- `member` 1—N `work_event`（owner），N—N `work_event`（通过 `event_participant`）；
- `member` 1—N `report`，`report` 1—N `report_item`、`report_version`、`push_record`；
- `team` N—N `member`（通过 `team_member`）；
- `sync_cursor`、`pipeline_run`、`audit_log` 为独立运维表，不与业务实体建立外键。
- ER 图见第 7 节 UML-04。

## 4. 接口契约

### 4.1 采集层契约

```python
class TimeWindow(NamedTuple):
    since: datetime          # 含
    until: datetime          # 不含
    tz: str = "Asia/Shanghai"

@dataclass
class WorkEvent:
    source: str              # github | feishu_calendar | feishu_doc | feishu_task
    source_id: str           # 平台内唯一 ID
    event_type: str          # commit | pr | meeting | doc_edit | task_update
    owner_open_id: str
    occurred_at: datetime
    title: str
    summary: str | None
    url: str | None
    confidence: float
    payload: dict

@dataclass
class CollectResult:
    events: list[WorkEvent]
    next_cursor: str | None
    errors: list[CollectError]   # 单源失败不阻断其它源

class Collector(Protocol):
    source: str
    async def collect(self, member: Member, window: TimeWindow) -> CollectResult: ...
```

| 契约 | 实现 | 入参 | 出参 | 行为约束 |
|---|---|---|---|---|
| C-COL-01 | `GitHubCollector.collect` | `member`、`window`、`repos: list[str]` | `CollectResult` | 每源超时 10s；分页 `per_page=100`；使用 ETag 增量；429 按 `Retry-After` 退避 |
| C-COL-02 | `FeishuCalendarCollector.collect` | `member`、`window` | `CollectResult` | 只取本人为组织者/参会人的日程；不取纪要正文 |
| C-COL-03 | `FeishuDocCollector.collect` | `member`、`window` | `CollectResult` | 只取元数据（标题、协作者、最后编辑时间），不下正文 |
| C-COL-04 | `FeishuTaskCollector.collect` | `member`、`window` | `CollectResult` | 只读，不改任务状态 |
| C-COL-05 | `collect_all` | `member`、`window`、`enabled_sources` | `dict[source, CollectResult]` | 并发上限 3；单源失败记 `errors` 并继续 |

### 4.2 生成层契约

```python
class LLMProvider(Protocol):
    async def generate(self, prompt: str, schema: dict, timeout: float = 20.0) -> str: ...

async def aggregate(member: Member, results: dict[str, CollectResult]) -> list[WorkEvent]
async def attribute(events: list[WorkEvent]) -> AttributionResult
async def build_report(member: Member, events: list[WorkEvent],
                       provider: LLMProvider, template: str = "v1") -> ReportDraft
async def validate_draft(draft: ReportDraft) -> ValidationResult
```

| 契约 | 函数 | 入参 | 出参 | 行为约束 |
|---|---|---|---|---|
| C-GEN-01 | `aggregate` | 成员、各源结果 | 去重排序后的事件 | 按 `(source, source_id)` 去重；窗口外事件丢弃 |
| C-GEN-02 | `attribute` | 事件列表 | 归属结果（含置信度） | 高置信度自动写入；中置信度进“待确认”；低置信度不写入 |
| C-GEN-03 | `build_report` | 成员、事件、Provider、模板 | `ReportDraft`（四段式） | 模型超时 20s；失败降级为模板 + 事实条目，不阻断提交 |
| C-GEN-04 | `validate_draft` | 草稿 | 校验结果 | 无来源引用的条目必须剔除；Schema 不符时降级 |

### 4.3 推送层契约

```python
@dataclass
class PushPayload:
    title: str
    content_md: str
    report_id: int
    target_type: str          # user | chat
    target_id: str

@dataclass
class PushResult:
    success: bool
    provider_msg_id: str | None
    error_code: str | None
    retryable: bool

class Publisher(Protocol):
    channel: str              # feishu | email
    async def publish(self, payload: PushPayload, idempotency_key: str) -> PushResult: ...
```

| 契约 | 实现 | 入参 | 出参 | 行为约束 |
|---|---|---|---|---|
| C-PUSH-01 | `FeishuPublisher.publish` | `PushPayload`、幂等键 | `PushResult` | 超时 10s；失败重试 3 次（指数退避）；同幂等键不重复发送 |
| C-PUSH-02 | `EmailPublisher.publish` | 同上 | `PushResult` | P2 预留；未配置 SMTP 时返回 `E-PUSH-010` 并跳过 |
| C-PUSH-03 | `publish_team_digest` | 团队、日期、目标 | `PushResult` | 汇总只读已提交日报；无数据不发送空卡片 |

### 4.4 主编排契约

| 契约 | 函数 | 入参 | 出参 | 行为约束 |
|---|---|---|---|---|
| C-ORC-01 | `run_member_pipeline` | `member_id`、`report_date` | `PipelineResult` | `run_key=date:member` 幂等；已成功则直接返回 |
| C-ORC-02 | `run_daily_pipeline` | `report_date`、`team_id?` | `PipelineRunResult` | 逐个成员执行，单成员失败不影响其他成员，最终状态 `partial` |
| C-ORC-03 | `run_team_rollup` | `team_id`、`report_date` | `TeamDigest` | 仅聚合 `submitted/pushed` 状态日报 |
| C-ORC-04 | `submit_report` | `report_id`、`actor_id` | `Report` | 仅本人可提交；草稿状态校验；写审计日志 |

### 4.5 对外接口

| 编号 | 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|---|
| API-01 | GET | `/api/oauth/feishu/callback` | 飞书 OAuth 回调，换取会话 | 公开 |
| API-02 | GET | `/api/reports/{date}` | 获取本人指定日期草稿 | 本人 |
| API-03 | PUT | `/api/reports/{id}/items` | 编辑草稿条目 | 本人 |
| API-04 | POST | `/api/reports/{id}/submit` | 确认提交 | 本人 |
| API-05 | POST | `/api/reports/{id}/push` | 手动推送 | 本人 |
| API-06 | GET | `/api/teams/{id}/digest` | 团队汇总 | 团队负责人 |

### 4.6 错误码

| 错误码 | 含义 | 触发条件 | 处理方式 | 是否重试 |
|---|---|---|---|---|
| E-COL-001 | 凭证无效或过期 | 401/403 | 标记成员凭证失效，跳过该源 | 否 |
| E-COL-002 | 触发限流 | 429 | 按 `Retry-After` 退避 | 是 |
| E-COL-003 | 采集超时 | 超过 10s | 记录并继续其它源 | 是（≤2 次） |
| E-GEN-001 | 模型输出不符合 Schema | 校验失败 | 重试 1 次后降级模板 | 是（1 次） |
| E-GEN-002 | 条目无来源引用 | 校验发现 | 剔除该条目 | 否 |
| E-GEN-003 | 模型限流/超时 | 429/超时 | 降级为事实模板 | 是（≤2 次） |
| E-PUSH-001 | 飞书凭证失效 | 401 | 标记需重新授权 | 否 |
| E-PUSH-002 | 目标不存在或无权限 | 404/403 | 记录并提示 | 否 |
| E-PUSH-010 | 渠道未配置 | SMTP/渠道缺失 | 跳过并记录 | 否 |

## 5. 技术选型 ADR

### ADR-001：HTTP 客户端选用 httpx

- **状态**：已接受
- **背景**：采集层需要并发调用飞书与 GitHub 两类 REST API，需异步、连接复用、细粒度超时，且在测试中可注入模拟响应。
- **备选项**：

| 备选项 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| `httpx` | 同步/异步双 API；原生支持 `MockTransport`；超时、重试、HTTP/2 配置齐全 | 生态小于 requests；团队需熟悉 async | 采纳 |
| `requests` | 最普及、示例多 | 不支持 async，并发需线程池；与 FastAPI/Celery 异步链路不匹配 | 否决：并发与异步成本高 |
| `aiohttp` | 性能好、异步成熟 | API 较底层，连接管理与测试 mock 需额外封装 | 否决：开发与测试成本高于收益 |
| 各平台官方 SDK | 封装完整、字段映射省事 | 飞书/ GitHub 两套 SDK 风格不一，异常模型难以统一；版本升级受制于 SDK | 部分采纳：仅在 SDK 明显降低复杂度时包装为适配器，不直接暴露给业务层 |

- **决策**：统一使用 `httpx.AsyncClient`，按数据源一个实例，超时、重试、限流在客户端层配置。
- **理由**：项目瓶颈是外部 API 的并发等待；httpx 的 async + `MockTransport` 能同时解决性能与可测试性，且避免引入两套 SDK 的异常模型。
- **影响**：采集层全部为 async；测试用 `httpx.MockTransport` 回放录制响应；连接池大小与超时纳入配置。

### ADR-002：存储选用 SQLite（WAL 模式）

- **状态**：已接受
- **背景**：系统需要持久化日报、原始事件、推送记录与审计日志；课程环境为单机演示，数据量在十万行级别；部署越简单越好，答辩环境需可复制。
- **备选项**：

| 备选项 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| SQLite（WAL） | 零运维、单文件、随仓库目录复制；支持 JSON 函数与 FTS5 | 并发写弱；多实例部署有锁竞争 | 采纳 |
| PostgreSQL | 并发与事务能力强，适合多实例 | 需额外部署与运维；答辩环境多一个依赖 | 否决：当前规模用不上，成本更高 |
| MySQL | 普及度高、资料多 | 同样需要独立服务；JSON 能力较弱 | 否决：同上 |
| 仅文件（JSON/CSV） | 实现最快 | 无事务、查询与并发能力缺失 | 否决：无法支撑状态机与审计 |

- **决策**：v1 使用 SQLite 单文件，开启 WAL、`busy_timeout=5000`、外键约束；写入集中在 Worker 侧串行执行。
- **理由**：本项目的复杂度在外部集成而非数据规模；SQLite 能把部署依赖降到最低，并让数据随项目目录整体拷贝。并发压力（多人同时写）不在 v1 范围内。
- **影响**：所有写操作经仓储层统一事务；多实例前必须迁移 PostgreSQL；`DATABASE_URL` 作为唯一切换点，ORM 层不写 SQLite 方言。

### ADR-003：大模型接入采用统一 `LLMProvider` 抽象

- **状态**：已接受
- **背景**：生成层需要把结构化事实转成四段式日报；模型供应商价格、限流、合规要求可能变化，且测试环境不能依赖真实模型。
- **备选项**：

| 备选项 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| 统一 `LLMProvider` + 默认国内模型 | 可切换供应商；测试可注入 FakeProvider；业务代码不感知厂商 | 多一层抽象与提示词适配 | 采纳 |
| 直接调用单一厂商 SDK | 代码最短、上手快 | 供应商锁定；切换成本高；测试需联网 | 否决：风险集中 |
| 自部署开源模型 | 数据不出域 | 需 GPU 与运维；课程周期内不可行 | 否决：成本过高，作为后续私有化选项 |

- **决策**：定义 `generate(prompt, schema, timeout) -> str` 协议；默认 DeepSeek `deepseek-chat`，配置切换；测试使用 FakeProvider。
- **理由**：生成质量与合规策略是易变项，抽象层把变化隔离在配置与提示词内，同时保证生成层可离线测试。
- **影响**：提示词与 Schema 版本化；调用设超时、限流与缓存；失败必须降级为模板，不得阻断日报提交。

### ADR-004：调度采用 Celery + Redis

- **状态**：已接受
- **背景**：每天需在固定时间触发全体成员流水线，失败任务需重试与可观测，部分任务耗时长（模型调用）。
- **备选项**：

| 备选项 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| Celery + Redis | 定时、重试、任务状态成熟；可与 FastAPI 共享配置 | 组件重、调试成本高；Windows 本地需 Docker | 采纳 |
| APScheduler 进程内 | 零额外组件 | 多实例重复执行；无持久化与重试 | 否决：无法支撑重跑与失败恢复 |
| 系统 cron + CLI | 简单直观 | 任务状态不可查；重试与并发控制需自建 | 否决：运维证据不足 |

- **决策**：Celery Beat 触发，Worker 执行；`run_key` 保证幂等，失败可手动重跑。
- **理由**：课程验收需要可展示的任务状态、重试记录与幂等证据，Celery 直接提供这些能力。
- **影响**：引入 Redis 依赖；部署增加 Worker/Beat 两个容器；任务函数必须幂等且可重入。

## 6. 非功能性约束

| 类别 | 约束 | 度量方式 | 验证阶段 |
|---|---|---|---|
| 性能 | 单份日报生成（不含人工编辑）P95 ≤ 5s；采集单源超时 10s | 服务端埋点与 `pipeline_run.stats_json` | 集成测试 |
| 性能 | 50 人团队全量流水线 ≤ 3 分钟 | 压测脚本 | 第 2 周验证 |
| 采集频率 | GitHub 认证请求 ≤ 5000 次/小时；飞书按应用配额；同源最小间隔 1s，抖动 ±20% | 客户端令牌桶 + 请求日志 | 代码审查 |
| 采集增量 | 二次采集不重复拉取全量，使用 ETag/游标 | `sync_cursor` 命中率 | 集成测试 |
| 重试策略 | 仅对超时、429、5xx 重试，指数退避（1s/2s/4s + 抖动），最多 3 次；4xx 不重试 | 重试日志与 `push_record.retry_count` | 单元测试 |
| 幂等 | 采集按 `(source, source_id)`、推送按幂等键、流水线按 `run_key` | 重复执行不产生重复数据 | 集成测试 |
| 密钥管理 | 全部通过环境变量注入；仓库只保留 `.env.example` 占位；令牌不入库、不入日志 | `git grep` 扫描 + 启动检查 | 安全自检 |
| 密钥权限 | GitHub PAT 仅只读；飞书应用最小 scope（日历只读、文档元数据、任务只读、消息发送） | 权限清单核对 | 部署前 |
| 密钥轮换 | 支持不重启滚动更新；失效返回明确错误码并通知 | 轮换演练 | 第 4 周自检 |
| 日志安全 | 日志脱敏：不打印令牌、正文、邮箱；审计只记录元数据 | 日志抽样 | 代码审查 |
| 数据安全 | SQL 全部参数化/ORM；敏感字段最小化采集 | 静态扫描 + 代码审查 | CI |
| 可用性 | 单源失败不影响整体；模型失败降级模板；推送失败可重试 | 故障注入测试 | 集成测试 |
| 兼容性 | Python 3.12+；SQLite ≥ 3.35；飞书开放平台 v1 接口；GitHub REST v3 | CI 矩阵 | CI |

## 7. UML 附件清单

| 编号 | 图类型 | 文件 | 表达内容 | 关联章节 |
|---|---|---|---|---|
| UML-01 | 用例图 | `uml/use-case.png` | 员工、负责人、HR、管理员、外部系统 | 第 2 节 |
| UML-01a | 用例模板与用例详述 | `uml/usecase-spec.md` | 21 个用例清单、标准模板、6 个关键用例详述 | 第 2、4 节 |
| UML-02 | 数据流图 | `uml/data-flow.png` | 四层数据流与存储边界 | 第 1 节 |
| UML-03 | 类图 | `uml/class.png` | Collector/Generator/Publisher/Repository | 第 2、4 节 |
| UML-04 | ER 图 | `uml/er.png` | 3.2 节表结构与关系 | 第 3 节 |
| UML-05 | 关键序列图 | `uml/sequence-daily.png` | 定时流水线：采集→生成→推送 | 第 4 节 |

> 全部使用 PlantUML 绘制（1.2025.9），`.puml` 源文件与导出 PNG 一并入库；用例图/ER 图使用 Smetana 布局，类图/数据流图使用 ELK 布局。

## 8. 测试策略

| 测试层级 | 覆盖对象 | 用例来源 | 通过标准 |
|---|---|---|---|
| 单元测试 | 采集器解析、归属规则、校验器、重试策略 | 接口契约 C-COL/C-GEN/C-PUSH | 覆盖率 ≥ 70%，关键规则 100% |
| 集成测试 | 流水线端到端（mock 外部 API + FakeProvider） | 成功标准 SC-xx | 全流程可重复执行，幂等验证通过 |
| 故障注入 | 401/403/429/超时/模型返回非法 JSON | 错误码表 4.6 | 每类错误有预期降级行为 |
| 手工验证 | 飞书卡片显示、草稿编辑、团队汇总 | 需求澄清 Q-04/Q-07 | 演示路径可复现 |

## 9. 风险与备选方案

| 风险 | 触发条件 | 影响 | 应对 / 备选方案 |
|---|---|---|---|
| 飞书权限审核延迟 | scope 未批 | 采集不可用 | 使用测试企业 + mock 采集器；接口契约不变，仅切换实现 |
| 模型输出不稳定 | 返回非 JSON 或事实漂移 | 日报不可用 | Schema 校验 + 无来源剔除 + 降级模板 |
| SQLite 写锁 | 并发写入高峰 | 任务失败 | WAL + `busy_timeout` + Worker 串行写；必要时切 PostgreSQL |
| 采集量超配额 | 仓库或成员过多 | 限流失败 | 增量游标、白名单仓库、令牌桶、错峰调度 |
| 协作归属误判 | 多人共同编辑 | 成果算错人 | 置信度分级 + 人工确认，低置信度不自动写入 |
| Redis 单点 | 容器异常 | 调度中断 | 任务幂等，恢复后重跑 `pipeline_run` |

## 10. 变更记录

| 日期 | 版本 | 变更内容 | 作者 |
|---|---|---|---|
| 2026-11-10 | v0.1 | 初稿：四层架构、数据模型、接口契约、4 份 ADR、非功能约束 | 架构师 |

## 11. 自查清单

- [x] 每条提案 P0/P1 功能都有模块承接（第 2 节）
- [x] 模块职责边界唯一，无重叠
- [x] 每个接口契约含入参、出参、错误码、行为约束
- [x] ADR 4 份，均记录被否决的备选项与理由
- [x] 非功能约束可度量，覆盖采集限流、密钥管理、异常重试
- [x] UML 附件齐全（用例图、用例模板、数据流图、类图、ER 图、序列图），均为工具绘制
- [ ] 与 `docs/需求澄清报告.md` 的开放问题（邮件推送、飞书 scope）待评审确认
