# dsh-smart-charts

DeepSeek Harness 的 **Smart Charts** skill 插件。

> 把数据文件（CSV / Excel / JSON）一键转换为**交互式 ECharts HTML**：自动识别数据形态、推荐并生成图表，支持多文件合并、LLM 数据转换代码（沙箱安全执行）、完全离线渲染。

## 功能特性

- **21 种图表类型**：`line` `bar` `area` `pie` `scatter` `radar` `heatmap` `treemap` `graph` `boxplot` `waterfall` `gauge` `sankey` `funnel` `sunburst` `wordcloud` `histogram` `stacked_bar` `bubble` `pareto` `combo`，覆盖趋势、对比、占比、分布、相关、流向、转化、词频等场景。
- **多格式解析**：CSV（逗号）/ TSV（制表）/ TXT（自动探测分隔符 `,`/`\t`/`;`/`|`）、Excel（`.xlsx`/`.xls`）、JSON（数组 + 单层嵌套）；自动检测 UTF-8 / GBK / GB2312 编码。
- **多文件自动合并**：最多约 10 个文件；列完全相同 → 纵向拼接（注入 `source_file` 来源列），≥50% 列重叠 → 横向关联，无共同结构 → 明确报错建议分开分析。
- **LLM 数据转换**：`--transform-code` 用 pandas 代码完成列重命名 / 重塑 / 聚合等清洗，由模型按数据语义生成。
- **三层安全沙箱**：transform 代码经过「黑名单 + AST 白名单 + 安全 builtins」三重校验；违规返回带 `suggestion` 的结构化错误，模型可机械修正重试，无需用户介入。
- **完全离线**：ECharts JS 打包在 `assets/` 并内联进每个 HTML，无 CDN、无外部依赖。
- **交互式输出**：悬停查数、`dataZoom` 缩放、超阈值自动横向滚动、标题双击内联编辑、图表可保存为图片。
- **结构化错误**：`SmartChartsError` 统一输出 JSON（`code` / `code_name` / `suggestion`），失败可被 agent 稳定解析并重试。

## 支持的数据格式

| 格式 | 说明 |
|------|------|
| `.csv` | 逗号分隔 |
| `.tsv` | 制表符分隔 |
| `.txt` | 自动探测分隔符 |
| `.xlsx` / `.xls` | 首个非空 sheet（可用 `--sheet` 指定） |
| `.json` | 数组格式 + 单层嵌套对象 |

约束：单文件 ≤ 100 MB（推荐 ≤ 50 MB）；不支持数据库（先导出 CSV）、实时流、地理地图、嵌套 JSON > 1 层、非表格数据（图片/音视频）。

## 安装

### 渠道 A：npm（推荐，预编译免 allowBuilds）

npm 包地址：<https://www.npmjs.com/package/dsh-smart-charts>

```bash
dsh plugin --profile web add dsh-smart-charts
```

装的是预编译产物，无需任何构建权限。

### 渠道 B：GitHub 直装（纯 TS 源码）

```bash
dsh plugin --profile web add github:hherosoul/dsh-smart-charts
```

首次安装会因 pnpm≥10 拒绝运行 git 依赖的 `prepare` 构建脚本而失败。按 pnpm 打印的提示，把**精确包名**写进 profile 的 `pnpm-workspace.yaml`（默认 `~/.dsh/profiles/web/pnpm-workspace.yaml`）：

```yaml
allowBuilds:
  dsh-smart-charts: true
```

然后重新安装：

```bash
dsh plugin --profile web add github:hherosoul/dsh-smart-charts
```

> 放行 `allowBuilds` 等于授权该包在安装阶段执行代码，请只对你信任的源码放行，并建议固定 commit：`github:hherosoul/dsh-smart-charts#<sha>`。

### 渠道 C：本地 tarball

```bash
dsh plugin --profile web add ./dsh-smart-charts-6.0.0.tgz
```

## 验证

```bash
dsh --profile web --dump-config
```

看到 `# == dsh-smart-charts` 一层即加载成功。

## 使用

1. 把数据文件放进 workspace 目录，启动 DSH 会话。
2. 对 agent 说「分析 `sales.csv` 并生成柱状图」，或输入 `/smart-charts` 直接触发。
3. agent 会按 `SKILL.md` 流程：解析数据 → 推荐图表类型 → 生成 ECharts HTML 到 workspace 的 `output/`。
4. 首次运行前，agent 会先安装 Python 依赖（已做 SHA256 校验）：

```bash
pip install -r requirements.txt --require-hashes
```

依赖（`==` 锁定 + SHA256）：`pandas` `numpy` `openpyxl` `xlrd`。

## 相关平台 / 生态

本 skill 同时发布在**腾讯 SkillHub**（WorkBuddy 生态）：

- 腾讯 SkillHub：<https://skillhub.cn/skills>（搜索 `smart-charts`）
- 在 SkillHub 上的使用方式：上传 CSV / Excel / JSON 数据文件 → 生成交互式图表 HTML，可保存为图片。

## 目录结构

```
dsh/
├── package.json         # dsh.bundle.patch 声明
├── cordis.patch.yml     # insert 插件行
├── tsconfig.json
├── src/index.ts         # 唯一入口：mount dsh-skill-filesystem
└── skills/smart-charts/ # skill 本体（SKILL.md + scripts + references + assets）
    ├── SKILL.md         # skill 指令（frontmatter + 工作流 + 图表类型表）
    ├── references/      # CLI flags 语义、错误码表、FAQ
    ├── scripts/         # Python 实现（解析/转换/渲染/沙箱）
    └── assets/          # 内联 ECharts JS
```

## License

MIT
