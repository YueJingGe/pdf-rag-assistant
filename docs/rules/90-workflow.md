# 90 工作流（Workflow：改动留痕完整流程）

## 流程总览（每个 P 任务 / 每轮改动都走）

```
① 需求文档 ──▶ ② 用户确认 ──▶ ③ 基线 commit ──▶ ④ 实施 ──▶ ⑤ changelog ──▶ ⑥ ADR(视情况) ──▶ ⑦ 收尾 commit
```

| 步骤 | 动作 | 产物 |
|---|---|---|
| ① | 在 `docs/requirements/` 写 `Px-y-slug.md`：背景 / 目标 / 任务分解 / 验收标准 / 边界决策（含默认决策待确认） | 需求文档 |
| ② | **等用户确认后才能动代码**；用户反馈的补充要求记回需求文档 | 确认记录 |
| ③ | `git commit` 当前工作区为基线（无未提交改动可跳过）；涉及 RAG 禁区文件的，此处是最后确认点 | 基线 commit |
| ④ | 实施；可 `@` 引用 `.claude/skills/*`（操作手册）与 `.claude/agents/*`（子代理角色模板）；改动逐文件说明 diff | 代码变更 |
| ⑤ | 在 `docs/changelog/Px-y-slug.md` **追加**本轮记录（规则见下） | 改动日志 |
| ⑥ | 架构级决策 → `docs/decisions/NNN-slug.md`，写/不写边界见 `docs/decisions/README.md` | ADR |
| ⑦ | 收尾 commit，message：`[Px-y] 任务名 - 本轮摘要`；同时完成 README/依赖/文档同步等收尾动作（见下） | 收尾 commit |

## Changelog 多轮追加规则（硬性）

1. **每个任务一个文件**（`docs/changelog/P0-1-auth.md`），修补同一任务时**追加在原文件内**，不新建文件
2. 文件内**按时间倒序**排列：最新一轮在最上面
3. 每轮记录必含四要素：**时间戳 + 改动摘要 + diff 摘要（文件×行数级别）+ 验收结果**

```markdown
## 2026-10-13 14:30 · 第 2 轮：xxx 修复
- 改动摘要：…
- diff 摘要：api.ts (+6/-1)…
- 验收结果：…（命令 + 实际输出结论）
```

## 命名与提交规范

- 任务编号：`Px-y`（阶段-序号），slug 用英文短横线（`P0-1-auth`、`P0-2-service-layer`）
- commit message：`[P0-2] service 层抽取 - 新增 kb_service`（前缀任务号 + 主题 - 摘要）
- **commit 前必须经用户确认 message**（交互式确认，不得自动提交）

## 每次功能开发的收尾动作（沿用项目原有约定）

1. 更新 `README.md`（核心亮点/相关章节体现新功能）
2. 检查 `requirements.txt` / `package.json` 依赖同步
3. 改了数据模型 → 执行迁移脚本或提供脚本
4. 改了后端 Python → 重启后端服务
5. 同步更新 `重难点以及遇到的问题.md`（bug 修复/优化都记）、涉及模型时更新 `汇总项目用到的模型.md`

## 验证纪律

- 每轮改动的验证命令与**实际输出结论**写入 changelog"验收结果"，不接受"应该没问题"
- 涉及鉴权/归属的改动，回归清单见 `.claude/skills/verify-change.md`
