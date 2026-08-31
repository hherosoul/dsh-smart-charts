# Changelog

本文件记录 `dsh-smart-charts` 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [8.0.1] - 2026-09-01

### Added
- 图表类型从 21 种扩展到 26 种：新增 `venn`（集合交叠）、`mindmap`（思维导图）、`orgchart`（组织架构）、`liquid`（水波球进度）、`spreadsheet`（原表/透视展示）。
- 主题系统：3 套主题预设（`default` / `classic` / `dark`）。
- `plot_stats` 统计摘要：成功时 stdout 输出绘图数据完整统计描述（26 类全覆盖），供 agent 撰写解读。
- 交付解读规范：`--dry-run`（只算统计不渲染）+ `--annotation`（将 LLM 文字解读注入 HTML「图表说明」区块）两步标准流程。
- 多图批量模式：`--charts-file`（JSON 声明多张图，支持图级 transform），含中文/引号的 transform 防转义。
- `--label-col` / `--color-by`：散点/气泡等图表的身份列与着色维度。

### Changed
- 依赖声明去哈希化：`requirements.txt` 仅保留直接依赖的 `==` 精确版本锁，移除 `--require-hashes` 与平台哈希，安装命令简化为 `pip install -r requirements.txt`，Windows 等平台不再出现哈希不匹配错误。
- 新增脚本模块：`_bootstrap.py`（环境自举）、`plot_stats.py` / `stats_kernels.py`（统计摘要）、`texts.py`（文案）、`themes.py`（主题）；新增 `echarts-liquidfill.min.js` 离线资源。
- SKILL.md 重构：frontmatter 补充 license/compatibility/permissions/safety 元信息，契约精简为 5 条 MUST，新增黄金示例与口径陷阱说明。

### Removed
- 移除 `generate_hashes.py` 与 `ux_regression_check.py`（依赖去哈希化后不再需要）。

## [6.0.1] - 2026-08-19

### Changed
- 将 `@deepseek-ai/dsh-skill-filesystem` 从 `dependencies` 移至 `peerDependencies`，符合 awesome-dsh-plugin 收录推荐规范。

### Docs
- 完善 README：补充 npm 安装方式、功能特性说明、腾讯 SkillHub 生态信息。
- README 补充 SkillHub 成就（累计下载 6.8 万次、数据分析分类排名第一）。

## [6.0.0] - 2026-08-19

### Added
- 首次将 smart-charts 发布为 DeepSeek Harness（DSH）skill 插件。
- 薄 Cordis 插件壳，挂载 `@deepseek-ai/dsh-skill-filesystem`，注册 `smart-charts` skill。
- 完整保留 Python 图表生成能力：21 种 ECharts 交互式图表类型。
- 数据解析：CSV / TSV / JSON / XLSX，支持多文件合并与编码检测。
- 三层安全机制：黑名单过滤 + AST 白名单校验 + 沙箱执行。
- 通过 npm 与 GitHub 双渠道分发。
