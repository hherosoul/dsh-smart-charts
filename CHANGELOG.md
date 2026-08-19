# Changelog

本文件记录 `dsh-smart-charts` 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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
