# 智能日报生成器

基于飞书开放平台与大语言模型的智能日报生成器：自动采集当天的工作痕迹（日历、文档、任务、Git 提交等），生成结构化日报草稿，员工确认后一键推送，并自动汇总团队进展。

## 技术栈

| 层次 | 选型 |
|---|---|
| 后端 | Python 3.12+ + FastAPI |
| 数据 | SQLite 3（文件数据库）+ Redis 7 |
| 任务 | Celery（Worker + Beat） |
| 大模型 | 统一 LLMProvider 接口，默认国内模型 |
| 前端 | Vue 3 + TypeScript（管理端）、飞书消息卡片 + H5（员工端） |
| 部署 | Docker Compose |

详细对比见 [docs/架构与技术栈选型.md](docs/架构与技术栈选型.md)。

## 目录结构

```
.
├── docs/                 # 课程设计文档与调研资料
├── specs/                # SDD 规格：proposal / design / tasks
│   └── 000-template/     # 模板
├── docker-compose.yml    # 本地开发环境（Redis）
├── data/                 # SQLite 数据库文件（不入库）
├── proposal.md           # 项目提案
├── README.md
└── CONTRIBUTING.md       # 分支、提交与 PR 规范
```

## 本地启动

前置：Docker Desktop。

```bash
docker compose up -d
docker compose ps
```

默认服务：

| 服务 | 地址 | 账号 |
|---|---|---|
| Redis | `localhost:6379` | 无密码 |

数据库使用 SQLite，文件位于 `data/daily_report.db`，首次启动自动创建，无需额外容器。

连接数据库：

```bash
sqlite3 data/daily_report.db
```

## 文档索引

| 文档 | 说明 |
|---|---|
| [proposal.md](proposal.md) | 项目提案、目标与范围 |
| [docs/业务调研报告.md](docs/业务调研报告.md) | 市场、用户、竞品与可行性 |
| [docs/架构与技术栈选型.md](docs/架构与技术栈选型.md) | 架构方案与技术栈对比 |
| [specs/README.md](specs/README.md) | 规格目录与 SDD 流程说明 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 协作规范 |

## 协作

- 分支、提交与 PR 规范见 [CONTRIBUTING.md](CONTRIBUTING.md)
- 功能开发前先在 `specs/` 下建立对应的规格目录
