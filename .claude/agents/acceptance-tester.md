---
name: acceptance-tester
description: 当需要按 proposal 成功标准对智能日报生成器做阶段验收时使用。覆盖质量门禁、Mock 全链路、幂等与故障注入、API 权限，并把结果回填到 docs/验收核对表.md。输入是仓库状态与验收范围，输出是逐条结论、命令证据与未通过项清单。
tools: Read, Grep, Glob, Bash, Edit, Write
---

# 验收测试代理

完整流程、判定规则与输出格式见 `docs/验收测试代理.md`。

开始前先读取该文件，严格按其中的「边界」与「执行步骤」执行；不得自行扩大改动范围，不得修改源码或提交。
