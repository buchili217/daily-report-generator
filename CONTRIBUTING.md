# 协作规范

## 分支规范

| 分支 | 用途 | 规则 |
|---|---|---|
| `main` | 稳定分支，可演示、可交付 | 受保护，禁止直接 push，只接受 PR 合并 |
| `feature/<issue>-<slug>` | 新功能 | 从 `main` 切出，完成后提 PR |
| `fix/<issue>-<slug>` | 缺陷修复 | 同上 |
| `docs/<slug>` | 文档变更 | 同上 |
| `chore/<slug>` | 依赖、配置、脚手架 | 同上 |

命名规则：

- 全小写，用中划线分隔，不使用中文与空格；
- `<issue>` 为 GitHub Issue 编号，没有 Issue 时可省略；
- 示例：`feature/12-feishu-calendar-sync`、`fix/18-empty-report`、`docs/api-guide`。

分支生命周期：

1. 从最新的 `main` 切出；
2. 小步提交，保持单个 PR 聚焦一件事；
3. PR 合并后删除远端分支。

## 提交规范

采用 [Conventional Commits](https://www.conventionalcommits.org/)，格式：

```
<type>(<scope>): <subject>
```

常用 type：

| type | 含义 |
|---|---|
| `feat` | 新功能 |
| `fix` | 缺陷修复 |
| `docs` | 文档 |
| `refactor` | 重构（不改变外部行为） |
| `test` | 测试 |
| `chore` | 构建、依赖、配置 |

示例：

```
feat(report): 支持按日历事件生成日报草稿
fix(auth): 修复飞书 token 过期后未刷新
docs(spec): 补充日报生成验收标准
```

要求：

- subject 使用中文或英文均可，不加句号，不超过 50 字；
- 一个提交只做一件事；
- 不提交调试代码、注释掉的代码和大文件。

## Pull Request 规范

1. 标题格式与提交规范一致，例如 `feat(report): 日报生成 MVP`；
2. 描述按 `.github/pull_request_template.md` 填写；
3. 必须关联对应 Issue（`Closes #12`）；
4. 至少 1 名组员 review 通过后才能合并；
5. 合并方式统一使用 **Squash and merge**，保持 `main` 历史线性；
6. 合并后删除源分支；
7. 不在 PR 中混入无关改动（格式化、重命名请单独提）。

## 代码规范

- Python：`ruff` 做 lint 与格式化，`mypy` 做类型检查；
- 测试：`pytest`，新增功能必须附带测试；
- 提交前本地自检：

```bash
ruff check .
ruff format --check .
mypy .
pytest
```

## 规格驱动开发（SDD）流程

1. 在 `specs/` 下新建 `NNN-<slug>/` 目录，从 `000-template/` 复制模板；
2. 先写 `spec.md`（做什么、验收标准），评审通过；
3. 再写 `plan.md`（怎么做、数据模型、接口）；
4. 拆 `tasks.md`（任务清单与依赖）；
5. 按任务实现，PR 中引用对应 spec 目录。

## 分支保护

`main` 分支已配置保护规则：需要 PR、至少 1 个 approve、禁止强推与删除。管理员可在紧急情况下绕过，但需在 PR 中说明原因。
