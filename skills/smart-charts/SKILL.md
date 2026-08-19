---
name: smart-charts
description: "Intelligent chart generation and data analysis skill. Reads user-supplied data files (CSV/Excel/JSON), analyzes data characteristics with LLM assistance, auto-recommends and generates interactive ECharts visualizations. Use when the user asks to analyze data, generate charts, create visualizations, or work with tabular data files."
metadata:
  version: 6.0.0
  author: smart-charts
---

# Smart Charts

> 将数据文件（CSV/Excel/JSON）转化为交互式 ECharts HTML。支持 21 种图表类型、多文件合并、LLM 数据转换代码（沙箱执行）。
> CLI 细节、flags 语义、错误码表、FAQ 见 [REFERENCE.md](./references/REFERENCE.md)。

---

## Activation Triggers

Load this skill when **any** of the following is met:

- User mentions: "analyze data", "generate chart", "data visualization", "chart", "visualization"
  / 用户提到：「分析数据」「生成图表」「数据可视化」
- User provides a data file and asks for analysis or visualization
- User asks to generate charts or a report from tabular data

---

## Hard Constraints (MUST follow)

1. **MUST follow the CLI workflow**: `data_parser.py` → `cli.py`，不要自写脚本替代 CLI。
2. **Messy headers MUST use CLI flags**（`--skiprows N` / `--header-row N` / `--sheet`，语义见 REFERENCE.md），N 由实际数据决定，不得拍脑袋固定。
3. **列重命名/重塑/聚合 MUST use `--transform-code`**。解析层只解决"哪行是表头"，其余清洗归 transform。
4. **MUST report unsupported scenarios**: CLI 确实不支持的（如嵌套 JSON 超过 1 层），先向用户说明并给建议，不得静默绕过。
5. **MUST NOT hard-code absolute paths** in generated code; resolve paths at runtime.
6. **不要主动传 `--lang`**；CLI 自动跟随数据语言。仅当用户明确要求某种语言时才传。

---

## Confirmation Policy

生成图表是廉价可逆动作（重生成 1-10s，零外部副作用）。**默认不向用户确认**，直接按数据语义选型生成。

agent 内部完成以下判断，不打断用户：

- **图表类型**：按 21 种图表的 Required Format 匹配数据形态
- **多文件合并策略**：按列重叠率自动决定（见 REFERENCE.md）
- **取值口径**：按列名、单位、数值范围推断最可能语义

**事后审阅代替事前确认**：交付时必须在交付语中显式列出本次关键假设，例如：

- "选了 line 图，因为 month 是时间序列列"
- "多文件按列名完全相同走纵向拼接，已注入 source_file 列"
- "销量按金额口径（列含 ¥/元/amount）"

用户审阅成品后若不同意任一假设，可一句话要求换口径/换类型/换合并方式重生成。

**唯一必须的用户介入点**：见 Exit Criteria 的"仍失败"分支。

---

## Capability Boundaries

**Supported:** CSV (.csv=comma / .tsv=tab / .txt=auto-detect delimiter), Excel (.xlsx/.xls), JSON (.json); 21 chart types (see below); up to ~10 files with auto-merge; single file ≤ 100 MB (≤ 50 MB recommended); auto-detects UTF-8/GBK/GB2312.

**Not supported:** Databases (export to CSV first), real-time/streaming data, geo maps, >100 MB files, nested JSON >1 level, non-tabular data (images/audio/video). Auto-merge requires ≥50% column overlap.

**Network requirement:** None. ECharts JS is bundled in `assets/` and inlined into each HTML output; charts render fully offline with no external dependencies.

**Security:** transform 代码由沙箱强制校验（黑名单 + AST 白名单 + 安全 builtins），违规会返回带 `suggestion` 的结构化错误，按提示修正重试即可，无需用户确认。机制细节见 REFERENCE.md。

---

## Execution Workflow

0. **Ensure Python dependencies** — 首次运行前先执行 `pip install -r requirements.txt --require-hashes`（已装过则跳过）。
1. **Obtain data** — user uploads file(s) or provides path(s).
2. **Parse data** — call `data_parser.py` on all files; for multiple files, assess merge feasibility.
3. **Recommend & generate** — 按数据语义选型后直接生成，无需确认；交付语显式列出关键假设（见 Confirmation Policy）。
4. **Transform (if needed)** — raw data 不匹配目标图表输入格式时，生成 `--transform-code`。
5. **Generate charts** — call `cli.py` → ECharts HTML.
6. **Present results** — 按下方 Exit Criteria 验收后立即展示。

## Exit Criteria (什么算做完，机械可判定)

- ✅ **成功**: `cli.py` stdout 为 `{"chart": {"success": true, ...}}`，且 `html_path` 指向的文件存在且非空 → 立即将图表呈现给用户。
- ❌ **失败**: `success: false` 或 exit code 1 → 读 `error.details.suggestion`，修正后重试；**同一环节最多重试 2 次**。
- 🛑 **仍失败（唯一必须的用户介入点）**: 把 `code_name`、`suggestion`、已尝试的修复如实报告用户并给出建议，等待用户决策。**不得**静默改用自写脚本兜底（违反约束 1/4）。

---

## Data Parsing

```bash
python scripts/data_parser.py <file1> [file2 ...] [--summary] [--merge] [--skiprows N] [--header-row N] [--sheet <name|index>]
```

- 相对路径按 DSH 提供的 skill base directory 解析（即本 skill 目录，含 SKILL.md）。
- flags 的精确语义、多编码回退、sheet 选择细节见 REFERENCE.md。
- **Merge 关键 gotcha**: 纵向拼接会注入 `source_file` 列标识来源文件，下游 transform 代码必须考虑到这个额外列。≥50% 列重叠走横向关联；无共同结构报错（建议分开分析）。

---

## Chart Generation

```bash
python scripts/cli.py \
  <file_path> <chart_type> \
  --title "Chart Title" --x-axis "date" --y-axis "revenue profit" \
  --transform-code "<pandas code>" --skiprows N --header-row N --sheet <name|index> \
  --lang zh|en --output-dir "./output" \
  --label-col "姓名" --color-by "地区"
```

- 成功输出 `{"chart": {"success": true, "html_path": ...}}` 到 stdout；失败输出结构化错误 JSON（`details.suggestion` 给出恢复方法）。完整参数与错误码表见 REFERENCE.md。
- `--label-col`（可选）：身份列（如姓名/名称），其值进数据点的 name 和 tooltip，适用于 scatter/bubble/boxplot。不传时自动探测未被占用的字符串列（列名含 姓名/name/id 等优先），自动选择会记入 stdout 的 `assumptions` 字段，交付语中应声明。
- `--color-by`（可选）：着色列，适用于 scatter/bubble。数值列 → visualMap 连续着色；类别列 → 按类别拆 series 分色并进 legend。默认不传——无分析意义的着色只是视觉噪音。
- 数据点超过阈值（默认 15）时 HTML 自动启用 dataZoom + 横向滚动，无需 agent 处理。
- 生成的 HTML 标题可双击内联编辑（用户可直接在浏览器修改标题，保存图片时使用新标题）。

### Chart Types

选择图表前先核对原始数据是否匹配 Required Format；不匹配则用 transform 代码适配。

> **量纲提示**：heatmap / boxplot / radar 等多列图表，若各列量纲差异大（如满分 10 与满分 100 混合），需先用 transform 代码归一化，否则小量纲列会被大量纲列主导。

| ID | Best For | Trigger Keywords | y_axis Cardinality | Required DataFrame Format | Example Columns |
|----|----------|------------------|:-------------------:|--------------------------|-----------------|
| `line` | Time-series trends | trend, change, over time, 趋势, 变化, 走势 | 1~N | 1 category/time + 1~N numeric | `month, productA, productB` |
| `bar` | Category comparison | compare, rank, difference, 对比, 比较, 排名, 差异 | 1~N | 1 category + 1~N numeric | `city, revenue, profit` |
| `area` | Cumulative change | cumulative, change, 累计, 变化 | 1~N | 1 category/time + 1~N numeric | `date, uv, pv` |
| `pie` | Composition/share | share, composition, proportion, 占比, 构成, 比例 | 1 | 1 name + 1 value | `category, share` |
| `scatter` | Correlation | correlation, relationship, scatter, 相关, 关系, 散点 | 1 | 2 numeric, or 1 category + 1 numeric | `height, weight` |
| `radar` | Multi-dimension comparison | multi-dimension, comprehensive, radar, 多维, 综合, 雷达 | N | 1 indicator + N numeric | `metric, productA, productB` |
| `heatmap` | Density/cross-tab | density, cross, matrix, heatmap, 密度, 交叉, 矩阵, 热力 | N | 2 category + 1 numeric | `row, col, value` |
| `treemap` | Hierarchical proportion | hierarchy, proportion, nested, 层级, 占比, 嵌套 | 1 | 1 name + 1 value | `category, sales` |
| `graph` | Entity relationships | relationship, network, topology, 关系, 网络, 拓扑 | special | source + target (+ value) | `from, to, weight` |
| `boxplot` | Distribution/outliers | distribution, outlier, quartile, 分布, 离群, 四分位 | N | N numeric | `math, chinese, english` |
| `waterfall` | Incremental change | increment, change, waterfall, 增量, 变化, 瀑布 | 1 | 1 category + 1 numeric (increments) | `month, profit_delta` |
| `gauge` | KPI progress | progress, kpi, achievement, 进度, KPI, 达成 | 1 | 1 numeric (mean used) | `completion_rate` |
| `sankey` | Flow transfer | flow, transfer, sankey, 流向, 流量, 转移 | special | source + target + value | `origin, destination, amount` |
| `funnel` | Conversion rate | conversion, funnel, churn, 转化, 漏斗, 流失 | 1 | 1 name + 1 value | `stage, count` |
| `sunburst` | Single-level proportion | proportion, sunburst, 占比, 比例 | 1 | 1 name + 1 value | `category, value` |
| `wordcloud` | Frequency/keywords | word frequency, keywords, text, 词频, 关键词, 词云 | 1 | 1 name + 1 value | `word, frequency` |
| `histogram` | Distribution shape | distribution, histogram, 分布, 直方图 | 1 | 1 numeric column | `score` |
| `stacked_bar` | Composition over categories | composition, stacked, 堆叠, 构成 | 1~N | 1 category + 1~N numeric | `quarter, productA, productB` |
| `bubble` | 3-variable correlation | bubble, 3-variable, 气泡, 三变量 | 2 | 2 numeric + 1 size | `price, rating, sales` |
| `pareto` | 80/20 analysis | pareto, 80/20, 帕累托, 二八 | 1 | 1 category + 1 numeric | `defect_type, count` |
| `combo` | Dual-axis comparison | dual-axis, combo, 双轴, 组合 | 1~N | 1 category + 1 bar + 1~N line | `month, revenue, growth_rate` |

**y_axis cardinality key:** `1` = only first column used; `1~N` = each column becomes a series; `N` = multiple columns expected; `2` = exactly 2 numeric columns required; `special` = auto-detects source/target/value columns. scatter/bubble/boxplot 中未被 x/y 占用的字符串列不会浪费——自动作为身份列进 tooltip（见 `--label-col`）。

### Programmatic API

```python
from scripts.chart_generator import ChartGenerator

# Single chart — returns {'chart': {'success', 'html_path'/'error', ...}}
# lang=None auto-detects from data; pass 'zh'/'en' to override (only when user asks).
result = ChartGenerator(output_dir="./output").generate_chart(
    df=df, chart_type="bar", title="Regional Revenue",
    x_axis="region", y_axis=["revenue"], lang=None,
)

# Batch — returns {'charts': [...]}，每项结构与单图一致
result = ChartGenerator(output_dir="./output").generate_multi_charts(
    df=df,
    chart_configs=[
        {"type": "bar",  "title": "Regional Revenue", "x_axis": "region", "y_axis": ["revenue"]},
        {"type": "line", "title": "Monthly Trend",   "x_axis": "month",  "y_axis": ["revenue", "profit"]},
    ],
    lang=None,
)
```

失败时 `success` 为 `False`、`error` 为结构化错误字典，不抛异常——检查 `success` 决定下一步。

---

## Transform Code Contract

契约（由沙箱强制，违反会收到带 `suggestion` 的错误，按提示修正即可）：

- 可用变量只有 `df`, `pd`, `np`；必须产出名为 `result` 的 `pd.DataFrame`
- 不要原地修改 `df`（用 `df.copy()` 或链式操作）
- 原始数据已匹配目标格式时，不传 `--transform-code`

**Common transform patterns:**
- Long→multi-series: `result = df.pivot_table(index='<time>', columns='<category>', values='<value>', aggfunc='sum').reset_index()`
- Long→pie (filter): `result = df[df['metric']=='revenue'][['category','value']].rename(columns={'category':'name'})`
- Wide→long: `result = df.melt(id_vars=['date'], var_name='name', value_name='value')`
- Aggregate→bar: `result = df.groupby('<category>')['<value>'].sum().reset_index()`
- Rename columns: `result = df.rename(columns={'来源':'source','去向':'target','金额':'value'})`
- Compute delta→waterfall: `tmp = df.copy(); tmp['delta'] = tmp['profit'].diff().fillna(tmp['profit'].iloc[0]); result = tmp[['month','delta']]`
- Rename messy/uninformative column names (after `--header-row` leaves columns like `10分`, `unnamed_3`): `result = df.rename(columns={'unnamed_0':'student_id','unnamed_1':'name','10分':'homework_score','30分':'exam_score'})`
- Forward-fill merged cells (when only the first row of a group is populated): `result = df.ffill()`
- Combine sub-headers into a single column name (when `--header-row N` flattens one row but loses context): `result = df.rename(columns={c: f'{c}_score' for c in df.columns if c not in ['student_id','name']})`
