---
name: smart-charts
description: "Intelligent chart generation and data analysis skill. Reads user-supplied data files (CSV/Excel/JSON), analyzes data characteristics with LLM assistance, auto-recommends and generates interactive ECharts visualizations. Use when the user asks to analyze data, generate charts, create visualizations, or work with tabular data files."
license: MIT
compatibility: "Python 3.11+; requires pandas==3.0.1, numpy==2.4.3, openpyxl==3.1.5, xlrd==2.0.1; no network access needed (ECharts JS bundled offline); install with: pip install -r requirements.txt"
metadata:
  author: smart-charts
  version: 8.0.1
permissions:
  file_read: true
  file_write: true
  network: false
safety:
  sandbox: "LLM-generated transform code runs in a restricted sandbox (keyword blacklist + AST whitelist + safe builtins). No user confirmation required."
input_formats: ["csv", "tsv", "txt", "xlsx", "xls", "json"]
output_format: html
---

# Smart Charts

> 将数据文件（CSV/Excel/JSON）转化为交互式 ECharts HTML。支持 26 种图表类型、3 套主题预设（default/classic/dark）、多文件合并、LLM 数据转换代码（沙箱执行）。
> CLI 全参数、flags 语义、多图/多文件细节、能力边界、错误码表、交付解读完整规范、FAQ 见 [REFERENCE.md](./references/REFERENCE.md)。

***

## Activation Triggers

* 用户提到「分析数据」「生成图表」「数据可视化」「chart」「visualization」，或提供数据文件要求分析/可视化
* 用户要求从表格数据生成图表或报告

***

## 契约（5 条，MUST）

1. 列名解析后会被规范化：转小写、特殊字符→`_`（如 `总学时`→`总_学时`），中文保留；`--x-axis`/`--y-axis`/transform 必须引用规范化后的列名
2. transform 沙箱：可用变量仅 `df`/`pd`/`np`（`np.select`/`np.where` 可用），支持多语句（`;` 或换行分隔），必须产出名为 `result` 的 DataFrame；禁止 import/open/try/类定义（黑名单 + AST 白名单强制校验，违规返回带 `suggestion` 的错误）
3. pie/bar 等按「1 个分类列(name) + 1 个数值列(value)」读数据；分类频次图先用 transform 聚合成 name/value 两列，再指定 `--x-axis name --y-axis value`
4. 成功时 stdout：`success`/`html_path`/`chart_type`/`title`/`data_rows`/`data_preview`（绘图数据前 10 行，口径校对用）+ `plot_stats`（绘图数据完整统计摘要，写解读用；26 类全覆盖）
5. **校对口径直接读 stdout 的 `data_preview` + `data_rows`，不要打开 HTML 去搜数据**——预览取自 transform 之后、渲染所用的同一份数据，即被绘制内容的真值

***

## 黄金示例（模板，复制改列名）

**1 分类频次 → pie/bar**（最高频场景）：

```bash
python {skill_base}/scripts/cli.py data.xlsx bar --title "标题" \
  --x-axis name --y-axis value \
  --transform-code "result = df['类别列'].fillna('未标注').value_counts().rename_axis('name').reset_index(name='value')"
```

**2 多图批量 + 防转义坑**（≥2 张图 MUST 批量；transform 含中文/引号时不要直接在 shell 传 `--charts`，写进 JSON 文件用 `--charts-file`）：

```bash
python {skill_base}/scripts/cli.py data.xlsx --sheet "Sheet1" \
  --charts-file charts.json --output-dir ./out
```

`charts.json` 每项：`type`（必填）+ `title`/`x_axis`/`y_axis`（字符串或数组）/`transform_code`（单图级）/`label_col`/`color_by`/`annotation`。

**3 分组聚合 → bar**：

```bash
--transform-code "result = df.groupby('分组列')['数值列'].sum().rename_axis('name').reset_index(name='value')"
```

**口径陷阱**：聚合前想清楚「按数据行 vs 按去重实体」——统计实体属性（如每门课程的学时结构）先 `drop_duplicates`；生成后对照 `data_preview` 检查（若各行 value 之和等于原始行数而非实体数，就是忘了去重）。

***

## Hard Constraints (MUST follow)

1. **MUST 走 CLI 工作流**（`data_parser.py` → `cli.py`），不要自写脚本替代。
2. **脏表头 MUST 用 CLI flags**（`--skiprows N` / `--header-row N` / `--sheet`，语义见 REFERENCE.md），N 由实际数据决定（先无 flags 跑一次看原始布局），不得拍脑袋固定。
3. **列重命名/重塑/聚合 MUST 用 `--transform-code`**。解析层只解决"哪行是表头"，其余清洗归 transform。
4. **MUST report unsupported scenarios**: CLI 确实不支持的（如嵌套 JSON 超过 1 层），先向用户说明并给建议，不得静默绕过。
5. **MUST NOT** 在生成代码中硬编码绝对路径；运行时解析路径。
6. **不要主动传 `--lang`**；CLI 自动跟随数据语言。仅当用户明确要求某种语言时才传。
7. **MUST 附解读交付**：交付图表时必须附由 LLM 写的文字解读，并通过 `--annotation` 注入 HTML（见下方「交付解读规范」），不得只交付裸图。

***

## 默认策略（不向用户确认）

生成图表是廉价可逆动作（重生成 1-10s，零外部副作用）。图表类型（按选型表匹配数据形态）、多文件合并策略（按列重叠率）、取值口径（按列名/单位/数值范围推断）均由 agent 内部决定，不打断用户。

**事后审阅代替事前确认**：交付语中显式列出本次关键假设（如"选了 line，因 month 是时间序列列""多文件按列名完全相同走纵向拼接，已注入 source_file 列""销量按金额口径"）。用户不同意任一假设，可一句话要求换口径/换类型/换合并方式重生成。

**唯一必须的用户介入点**：见 Exit Criteria 的"仍失败"分支。

***

## Exit Criteria（机械可判定）

* ✅ **成功**: stdout 为 `{"chart": {"success": true, ...}}`（多图模式为 `{"charts": [...], "summary": ...}`），且 `html_path` 指向的文件存在且非空 → 用同一 stdout 的 `data_preview`/`data_rows` 校对聚合口径（按行 vs 按去重实体），确认无误后附文字解读交付。
* ℹ️ `--dry-run` 不算交付：仅用于取 `plot_stats` 写解读，之后必须不带 `--dry-run` 正式生成一次并按成功标准验收。
* ❌ **失败**: `success: false` 或 exit code 1 → 读 `error.details.suggestion`，修正后重试；**同一环节最多重试 2 次**。
* 🛑 **仍失败（唯一必须的用户介入点）**: 把 `code_name`、`suggestion`、已尝试的修复如实报告用户并给出建议，等待用户决策。**不得**静默改用自写脚本兜底（违反约束 1/4）。

***

## Chart Types 选型表

选型前核对 Required Format；不匹配则用 transform 代码适配。

> **量纲提示**：heatmap / boxplot / radar 等多列图表，若各列量纲差异大（如满分 10 与满分 100 混合），需先用 transform 代码归一化，否则小量纲列会被大量纲列主导。

| ID | Best For | Trigger Keywords | y_axis | Required DataFrame Format |
|----|----------|------------------|:------:|---------------------------|
| `line` | Time-series trends | trend, change, over time, 趋势, 变化, 走势 | 1~N | 1 category/time + 1~N numeric |
| `bar` | Category comparison | compare, rank, difference, 对比, 比较, 排名, 差异 | 1~N | 1 category + 1~N numeric |
| `area` | Cumulative change | cumulative, change, 累计, 变化 | 1~N | 1 category/time + 1~N numeric |
| `pie` | Composition/share | share, composition, proportion, 占比, 构成, 比例 | 1 | 1 name + 1 value |
| `scatter` | Correlation | correlation, relationship, scatter, 相关, 关系, 散点 | 1 | 2 numeric, or 1 category + 1 numeric |
| `radar` | Multi-dimension comparison | multi-dimension, comprehensive, radar, 多维, 综合, 雷达 | N | 1 indicator + N numeric |
| `heatmap` | Density/cross-tab | density, cross, matrix, heatmap, 密度, 交叉, 矩阵, 热力 | N | 2 category + 1 numeric |
| `treemap` | Hierarchical proportion | hierarchy, proportion, nested, 层级, 占比, 嵌套 | 1 | 1 name + 1 value |
| `graph` | Entity relationships | relationship, network, topology, 关系, 网络, 拓扑 | special | source + target (+ value) |
| `boxplot` | Distribution/outliers | distribution, outlier, quartile, 分布, 离群, 四分位 | N | N numeric |
| `waterfall` | Incremental change | increment, change, waterfall, 增量, 变化, 瀑布 | 1 | 1 category + 1 numeric (increments) |
| `gauge` | KPI progress | progress, kpi, achievement, 进度, KPI, 达成 | 1 | 1 numeric (mean used) |
| `sankey` | Flow transfer | flow, transfer, sankey, 流向, 流量, 转移 | special | source + target + value |
| `funnel` | Conversion rate | conversion, funnel, churn, 转化, 漏斗, 流失 | 1 | 1 name + 1 value |
| `sunburst` | Single-level proportion | proportion, sunburst, 占比, 比例 | 1 | 1 name + 1 value |
| `wordcloud` | Frequency/keywords | word frequency, keywords, text, 词频, 关键词, 词云 | 1 | 1 name + 1 value |
| `histogram` | Distribution shape | distribution, histogram, 分布, 直方图 | 1 | 1 numeric column（`--x-axis` 或 `--y-axis` 均可，数值型 `--x-axis` 优先） |
| `stacked_bar` | Composition over categories | composition, stacked, 堆叠, 构成 | 1~N | 1 category + 1~N numeric |
| `bubble` | 3-variable correlation | bubble, 3-variable, 气泡, 三变量 | 2 | 2 numeric + 1 size |
| `pareto` | 80/20 analysis | pareto, 80/20, 帕累托, 二八 | 1 | 1 category + 1 numeric |
| `combo` | Dual-axis comparison | dual-axis, combo, 双轴, 组合 | 1~N | 1 category + 1 bar + 1~N line |
| `venn` | Set overlap (2~3 sets) | overlap, intersection, venn, 交集, 重叠, 韦恩 | 1 | 1 name + 1 value；交集行命名为 `A∩B`（分隔符：∩ & + × 与） |
| `mindmap` | Hierarchical ideas | mind map, outline, 思维导图, 脑图, 大纲 | 1 | 1 parent + 1 child（分类列） |
| `orgchart` | Organization structure | org chart, hierarchy, 组织架构, 汇报关系, 层级 | 1 | 1 parent + 1 child（分类列） |
| `liquid` | Percentage/progress | liquid, progress, percent, 水波, 进度, 百分比, 完成率 | 1 | 1 numeric (mean used) |
| `spreadsheet` | Raw table / pivot display | table, detail, spreadsheet, 表格, 明细, 清单 | N | 任意列（x/y 可选地筛选显示列；聚合用 transform） |

**y_axis cardinality key**: `1` = only first column used; `1~N` = each column becomes a series; `N` = multiple columns expected; `2` = exactly 2 numeric columns required; `special` = auto-detects source/target/value columns. scatter/bubble/boxplot 中未被 x/y 占用的字符串列不会浪费——自动作为身份列进 tooltip（见 `--label-col`）。

***

## Transform Code Contract

契约（由沙箱强制，违反会收到带 `suggestion` 的错误，按提示修正即可）：

* 可用变量只有 `df`, `pd`, `np`；必须产出名为 `result` 的 `pd.DataFrame`
* 不要原地修改 `df`（用 `df.copy()` 或链式操作）
* 原始数据已匹配目标格式时，不传 `--transform-code`

**Common transform patterns:**

* Long→multi-series: `result = df.pivot_table(index='<time>', columns='<category>', values='<value>', aggfunc='sum').reset_index()`
* Long→pie (filter): `result = df[df['metric']=='revenue'][['category','value']].rename(columns={'category':'name'})`
* Wide→long: `result = df.melt(id_vars=['date'], var_name='name', value_name='value')`
* Aggregate→bar: `result = df.groupby('<category>')['<value>'].sum().reset_index()`
* Rename columns: `result = df.rename(columns={'来源':'source','去向':'target','金额':'value'})`
* Compute delta→waterfall: `tmp = df.copy(); tmp['delta'] = tmp['profit'].diff().fillna(tmp['profit'].iloc[0]); result = tmp[['month','delta']]`
* Rename messy/uninformative column names (after `--header-row` leaves columns like `score_a`, `unnamed_3`): `result = df.rename(columns={'unnamed_0':'student_id','unnamed_1':'name','score_a':'homework_score','score_b':'exam_score'})`
* Forward-fill merged cells (when only the first row of a group is populated): `result = df.ffill()`
* Combine sub-headers into a single column name (when `--header-row N` flattens one row but loses context): `result = df.rename(columns={c: f'{c}_score' for c in df.columns if c not in ['student_id','name']})`

***

## 交付解读规范（Delivery Annotation）

交付每张图表时，必须附一段**由 LLM 写的文字解读**（不是模板文字），作为用户写报告的佐证。技能只负责算事实（`plot_stats`），解读由 agent 读 `plot_stats` 后自己写，再用 `--annotation` 注入 HTML（图表下方「图表说明」区块）。

**标准流程（两步）**：

1. 先带 `--dry-run` 调用（只算 `plot_stats`/`data_preview`，不渲染不落盘）。
2. agent 读 `plot_stats` 写 2~4 句解读（① 图是什么：类型+标题+覆盖范围；② 最显著事实：挑 1~2 个点给具体数值与标签；③ 口径说明一句话），然后去掉 `--dry-run`、带 `--annotation "解读文字"` 正式生成。

**硬边界**：解读的每个数字都必须能在 `plot_stats`/`data_preview` 里找到出处——不得凭印象编造；`x_cardinality` 是去重个数，按 x 列语义表述（x 是「姓名」则说「59 名学生」而非「59 个类别」）。完整规范与示例见 REFERENCE.md。
