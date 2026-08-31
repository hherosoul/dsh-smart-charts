# Reference

Detailed reference for installation, capability boundaries, CLI usage, programmatic API, and delivery annotation. For the contract, hard constraints, chart type table, and transform templates, see [SKILL.md](../SKILL.md).

---

## Installation

```bash
pip install -r requirements.txt
```

Dependencies (pinned with `==`): `pandas==3.0.1`, `numpy==2.4.3`, `openpyxl==3.1.5`, `xlrd==2.0.1`. ECharts JS is bundled in `assets/` (no CDN, fully offline).

Self-test (developer): `python {skill_base}/scripts/ux_regression_check.py` checks chart UX invariants (identity labels, color coding, tooltips, true waterfall) plus the v8 refactor guarantees (shared stats kernels, RenderContext, gauge ratio scale, ID-column protection, merge `_dup` fix, error code 2002).

---

## Capability Boundaries

**Supported:** CSV (.csv=comma / .tsv=tab / .txt=auto-detect delimiter), Excel (.xlsx/.xls), JSON (.json，支持 1 层嵌套对象，自动展开为「父.子」点分列，列名规范化后为「父_子」); 26 chart types (see SKILL.md); 3 themes (`--theme default|classic|dark`); multi-file auto-merge (recommended ≤ 10 files); single file ≤ 100 MB (≤ 50 MB recommended); auto-detects UTF-8/GBK/GB2312/UTF-16/Latin-1.

**Not supported:** Databases (export to CSV first), real-time/streaming data, geo maps, >100 MB files, nested JSON >1 level, non-tabular data (images/audio/video). Auto-merge requires ≥50% column overlap.

**Network requirement:** None. ECharts JS is bundled in `assets/` and inlined into each HTML output; charts render fully offline with no external dependencies.

**Security:** transform 代码由沙箱强制校验（黑名单 + AST 白名单 + 安全 builtins），违规会返回带 `suggestion` 的结构化错误，按提示修正重试即可，无需用户确认。机制细节见下方 Transform Code Generation。

---

## Data Parsing — CLI Reference

> `{skill_base}` = root directory of this skill (contains `SKILL.md`).

```bash
# Single file
python {skill_base}/scripts/data_parser.py <file_path> [--summary] [--skiprows N] [--header-row N] [--sheet <name|index>]

# Multiple files
python {skill_base}/scripts/data_parser.py <file1> <file2> ... [--summary]

# Multiple files with auto-merge
python {skill_base}/scripts/data_parser.py <file1> <file2> ... [--merge] [--summary]
```

**Flags:**
- `--summary` — output a JSON data summary (shape, columns, dtypes, missing, sample, stats) instead of a text preview.
- `--merge` — attempt to merge multiple files into one DataFrame.
- `--skiprows N` *(single-file only)* — skip the first N rows, then read the next row as the header. Use when the file has leading junk rows (notes, blanks) before any header.
- `--header-row N` *(single-file only)* — treat the 0-indexed row N as the header; rows above N are dropped. Use when the file has multi-row headers (merged cells, sub-headers) and you want one specific row as the column name.
- `--sheet <name|index>` *(single-file only)* — pick an Excel sheet by name or 0-indexed position (default: 0). An explicitly named/numbered sheet that does not exist returns a structured `DATA_PARSE_ERROR` listing `available_sheets`; only the default sheet 0 falls back automatically (first non-empty sheet is used when sheet 0 is empty).
- N must be determined by inspecting the actual data (run `data_parser.py` once without flags to see the raw layout). Never assume a fixed N.

**Merge behavior:**
- Identical columns → vertical concat (adds a `source_file` column to indicate each row's origin file — 下游 transform 代码必须考虑这个额外列).
- ≥50% overlap → horizontal join on shared key. Overlapping non-key columns from later files are merged back with `combine_first` (non-null values from both files survive); genuinely `_dup`-suffixed source column names are preserved untouched.
- No common structure → error (advise analyzing separately).
- `--merge --summary` 模式下 stdout 为纯 JSON，合并方式体现在 JSON 的 `merge_type` 字段（不打印额外文本行，保证机器可读）。

**ID-column protection:** columns named id/编号/学号/工号/邮编/电话/... or containing leading-zero values (e.g. `007`) are kept as strings — never silently coerced to numbers (which would destroy the leading zeros). All other numeric-looking string columns are still auto-converted.

**Delimited files are read as strings** (`dtype=str`) and numerified in one cleaning pass — this is what makes leading-zero protection possible; missing-value tokens (`NA`, empty, etc.) are still normalized to NaN by pandas.

**Argparse CLI:** both `data_parser.py` and `cli.py` parse arguments with argparse; unknown flags / missing values / bad types return the same structured JSON error (`code_name` + `details.suggestion`) instead of bare usage text.

**Formats:** .csv (comma) / .tsv (tab) / .txt (auto-detect delimiter: `,`/`\t`/`;`/`|`) + auto-detect encoding (UTF-8/UTF-8-BOM/GBK/GB2312/UTF-16/Latin-1, single shared fallback list), .xlsx/.xls (first non-empty sheet), .json (array format; 1-level nested objects are flattened into `parent.child` columns, which become `parent_child` after column-name normalization — reference the normalized names in `--x-axis`/`--y-axis`/transform code. Nested depth ≥2 or array-valued fields are rejected with a structured error).

**Column name normalization:** Parsed column names are normalized by `_normalize_col`:
1. Non-word characters (anything except letters, digits, `_`, and whitespace) are replaced with `_`. CJK characters count as word characters and are preserved.
2. Consecutive spaces/underscores collapse into a single `_`.
3. Leading/trailing `_` are stripped, then the name is lowercased.
4. Empty or NaN names become `unnamed`.

| Input | Normalized |
|-------|-----------|
| `Sales Amount` | `sales_amount` |
| `Revenue($)` | `revenue` |
| `销售-额%` | `销售_额` |
| `A/B` | `a_b` |
| `  Total  ` | `total` |
| (blank / NaN) | `unnamed` |

`--x-axis`, `--y-axis`, and transform code must use the **normalized** column names, not the raw header text.

**Error output:** When a `SmartChartsError` occurs, the CLI prints a JSON object to stderr:
```json
{"error": "<message>", "code": <int>, "code_name": "<NAME>", "details": {...}}
```
The `details` field always includes a `suggestion` for recovery. Any other exception is wrapped as `UNKNOWN_ERROR` (9999) JSON on stderr — in both `cli.py` and `data_parser.py`.

**Error codes:**

| Code | Name | Meaning |
|------|------|---------|
| 1001 | FILE_NOT_FOUND | File path does not exist |
| 1002 | FILE_NOT_REGULAR | Path is not a regular file |
| 1003 | FILE_FORMAT_INVALID | Unsupported file extension |
| 1004 | FILE_SIZE_EXCEEDED | File exceeds 100 MB limit |
| 2001 | DATA_PARSE_ERROR | Parsing failed (encoding, structure, sheet missing, etc.) |
| 2002 | DATA_MERGE_ERROR | Auto-merge impossible (no common structure between files) |
| 2003 | DATA_EMPTY | File or cleaned data is empty |
| 3001 | TRANSFORM_EXEC_ERROR | Transform code execution failed (blacklist/AST/timeout) |
| 3002 | TRANSFORM_NO_RESULT | Transform code did not produce `result` variable |
| 3003 | TRANSFORM_INVALID_RESULT | `result` is not a DataFrame |
| 3004 | TRANSFORM_EMPTY_RESULT | `result` DataFrame is empty |
| 4001 | CHART_GENERATION_ERROR | Chart generation failed |
| 4002 | CHART_TYPE_UNSUPPORTED | Unsupported chart type |
| 4003 | CHART_CONFIG_ERROR | Axis field does not exist in DataFrame |
| 9999 | UNKNOWN_ERROR | Unclassified error |

---

## Chart Generation — CLI Reference

```bash
python {skill_base}/scripts/cli.py \
  <file_path> <chart_type> \
  --title "Chart Title" \
  --x-axis "date" \
  --y-axis "revenue profit" \
  --transform-code "<pandas code>" \
  --annotation "<delivery text>" \
  --skiprows N --header-row N --sheet <name|index> \
  --lang zh|en \
  --theme default|classic|dark \
  --output-dir "./output" \
  --width 900 --height 560
```

**Parameters:**
- `file_path` (required) — path to the data file.
- `chart_type` (required) — one of the 26 types listed in SKILL.md.
- `--title` (default follows `--lang` / data language) — chart title.
- `--x-axis` (auto-detected if omitted) — column name for x-axis.
- `--y-axis` (space-separated; defaults to first 5 numeric columns, or first 3 other columns if none numeric) — column name(s) for y-axis.
- `--transform-code` (optional) — LLM-generated pandas code, validated + executed before rendering.
- `--annotation "<text>"` (optional) — delivery annotation text injected into the HTML below the chart（「图表说明」区块）. Final step of the two-step annotation flow (see 交付解读规范 below).
- `--skiprows` / `--header-row` / `--sheet` (optional) — same semantics as `data_parser.py`; passed through to the parsing step so chart generation works directly on messy-header files.
- `--lang zh|en` (optional) — force the chart text language. If omitted, the CLI auto-detects from the data: CJK character ratio > 5% in column names + string cells → `zh`, otherwise `en`. Pass `--lang` only when the user explicitly requests a specific language.
- `--label-col` (optional) — identity column (e.g. name/title). Its values become each point's `name` and appear as the tooltip title. Applies to scatter/bubble/boxplot (boxplot uses it for outlier points). If omitted, an unused string column is auto-detected (columns named 姓名/name/id/... preferred) and the choice is reported in the `assumptions` field of the success output.
- `--color-by` (optional) — color-encoding column for scatter/bubble. Numeric column → continuous coloring via `visualMap`; categorical column → one series per category with legend. Off by default — 无分析意义的着色只是视觉噪音.
- `--output-dir` (default: `./smart_charts_output`) — output directory for HTML files.
- `--width` / `--height` (default: 900 / 560) — HTML canvas size in px.
- `--theme` (default: `default`) — theme preset unifying the series palette and page colors: `default` (Okabe-Ito color-blind-safe palette), `classic` (ECharts native palette, blue accents), `dark` (dark background, light text; ECharts text/labels switch to light colors automatically). Applies to all 26 chart types including venn/mindmap/orgchart/liquid/spreadsheet. Pass the same theme across a batch for visual consistency.
- `--dry-run` (optional) — stats-only mode: outputs `plot_stats`/`data_preview` with `dry_run: true` and `html_path: null`, without rendering or writing HTML. Step 1 of the two-step annotation flow; then generate for real with `--annotation`. Works in both single- and multi-chart mode.
- `--charts-file <path>` (multi-chart mode, recommended) — read the `--charts` JSON array from a UTF-8 file instead of a shell argument; avoids shell-escaping corruption when transform code contains CJK text or quotes. Missing/unreadable file returns a structured `FILE_NOT_FOUND` error on stderr (exit 1).
- `spreadsheet` file naming — hash covers full table content (columns + values), so two same-schema tables with different data never overwrite each other.

**Output:** On success, prints a JSON object to stdout and exits with code 0:
```json
{"chart": {"success": true, "html_path": "./output/Title_abc123.html", "chart_type": "bar", "title": "Title", "data_rows": 34, "data_preview": [{"name": "兼职", "value": 20}, {"name": "专职", "value": 12}]}}
```
`data_rows` is the number of rows fed into plotting (after transform); `data_preview` is the first 10 rows of the final plotting data (the same data the renderer consumed, with NaN → null). Use it to sanity-check aggregation grain in-band — no need to open the HTML to verify values.
On failure, prints a structured JSON and exits with code 1:
- **File-level errors** (file not found, parse error, etc.): error JSON printed to **stderr**.
- **Chart-level errors** (unsupported type, transform failure, axis field missing, etc.): result JSON with `"success": false` printed to **stdout**.

Both include a `details.suggestion` field for recovery. Other exceptions are printed as plain text to stderr.

**Multi-chart mode:** when generating **2+ charts**, pass `--charts` instead of a positional `chart_type`. The file is parsed once and all charts are generated in a single process (several times faster than repeated single-chart calls):

```bash
python {skill_base}/scripts/cli.py data.csv \
  --charts '[{"type":"bar","title":"Revenue","x_axis":"city","y_axis":["revenue"]},
             {"type":"line","title":"Trend","x_axis":"date","y_axis":["revenue","profit"]}]' \
  --output-dir "./output"
```

- Each item requires `type`; optional per-chart keys: `title`, `x_axis`, `y_axis` (string or array), `transform_code` (per-chart), `label_col`, `color_by`, `annotation` (per-chart delivery text), `width`, `height`.
- A global `--transform-code` (optional) is applied to the DataFrame once before all charts; each chart may also carry its own `transform_code`.
- Output shape: `{"charts": [{...}, ...], "summary": {"total": N, "succeeded": M, "failed": K}}` — each item has the same structure as the single-chart `chart` object (including `success`, `html_path`, and `error.details.suggestion` on failure).
- Exit code 1 only when **all** charts fail; partial failure exits 0 with per-chart errors in the `charts` array.
- Invalid `--charts` JSON (malformed, empty array, or an item missing `type`) prints a `CHART_CONFIG_ERROR` JSON with a `suggestion` to stderr and exits 1.
- `--dry-run` 同样适用于多图模式：输出各图 `plot_stats`/`data_preview`（`dry_run: true`、`html_path` 为 null），不渲染不落盘。

**多文件并行**: 各文件配置已确定且互不依赖时，用 shell 后台并行（墙钟时间 ≈ 最慢一个文件）：

```bash
for f in data/*.xlsx; do
  python {skill_base}/scripts/cli.py "$f" --charts-file "cfg_$(basename "$f" .xlsx).json" --output-dir ./out &
done; wait
```

**Language behavior:** every piece of chart text — title, series names, tooltip labels, action buttons, scroll hint, footer, and the HTML `lang` attribute — is rendered in a single consistent language. By default that language follows the data; pass `--lang zh` or `--lang en` to override (e.g. when the user explicitly asks for an English chart on Chinese data).

**Overflow behavior:** when data points exceed the zoom threshold (default 15), the HTML enables ECharts `dataZoom` (slider + inside-drag) and a horizontal scrollbar on the chart container. Users can drag the slider, scroll horizontally, or click the fullscreen button to inspect all data points. No agent action needed.

**Inline title editing:** every generated HTML title is `contenteditable`. Users can double-click the title in the browser, type a new name, and press Enter — the ECharts chart title and the saved image filename update immediately. No backend round-trip needed.

---

## Programmatic API

```python
from scripts.chart_generator import ChartGenerator

# Single chart — returns {'chart': {'success', 'html_path'/'error', ...}}
# lang=None auto-detects from data; pass 'zh'/'en' to override (only when user asks).
# theme: 'default' | 'classic' | 'dark'（默认 default）
result = ChartGenerator(output_dir="./output", theme="default").generate_chart(
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

## 交付解读规范（完整）

技能只负责算事实（`plot_stats`），解读文字由 agent 读 `plot_stats` 后自己写，再用 `--annotation` 注入 HTML（图表下方「图表说明」区块）。流程见 SKILL.md（先 `--dry-run` 取 `plot_stats`，再带 `--annotation` 正式生成）。

**事实锚点**：解读的每个数字都必须能在 `plot_stats` 或 `data_preview` 里找到出处——不得凭印象编造。注意 `plot_stats` 里的 `x_cardinality` 是 x 轴去重后的个数，写解读时要结合 x 列语义说清（如 x 是「姓名」则说「59 名学生」，而不是笼统的「59 个类别」）。

**最小结构**（2~4 句）：

1. 这张图是什么：图表类型 + 标题 + 覆盖范围（结合 x 列语义，如「59 名学生」「5 个分数段」）。
2. 最显著的事实：基于 `plot_stats` 挑 1~2 个能支持结论的点（最大/最小/趋势方向/占比/离群/累计），给出具体数值与对应标签。
3. 口径说明：一句话交代取值口径，与 `assumptions` 字段呼应。

**硬边界**：

* 只陈述 `plot_stats`/`data_preview` 能支撑的事实，不夸大、不推测数据之外的原因。
* 深度业务解读（为什么/怎么办）不是硬性要求，属结合上下文的额外发挥。

**示例**（agent 读 `plot_stats` 后写，再用 `--annotation` 注入）：

```bash
python {skill_base}/scripts/cli.py data.csv bar --title "学生总成绩对比" \
  --x-axis 姓名 --y-axis 总成绩 \
  --annotation "本图展示 59 名学生的总成绩分布。韩家芯以 98.84 分居首，马云飞 59.96 分垫底，全班平均 76.91 分。"
```

---

## Transform Code Generation

When raw data doesn't match the target chart's input format, the LLM should generate pandas code following the template in [SKILL.md](../SKILL.md). The code is validated (keyword blacklist + AST whitelist) and executed in a sandbox before chart rendering.

**Safety rules enforced:**
- Only allowed variables: `df`, `pd`, `np`
- Must produce a `result` variable (pd.DataFrame)
- Do not modify `df` in-place
- No `import`, `open`, `exec`, `eval`, `os`, `sys`, `subprocess`, file I/O, or network calls
- Only safe builtins exposed (`len`, `range`, `sorted`, etc.); `open`/`exec`/`eval`/`__import__` removed
- Execution timeout: 10 seconds
- Max recursion depth: 500

On violation, a `CodeValidationError` is raised with `details.violations` listing the offending keywords or AST nodes, and `details.reason` explaining why.

---

## FAQ — Common Data Issues

**Q: The Excel file has multi-row headers (merged cells, sub-headers). How do I parse it?**

First run `data_parser.py` without flags to inspect the raw layout:
```bash
python {skill_base}/scripts/data_parser.py data.xls
```
Look at the printed `head(5)` to count how many rows are headers. Then re-run with `--header-row N` (0-indexed) where row N is the one you want as column names:
```bash
python {skill_base}/scripts/data_parser.py data.xls --header-row 2
```
Rows above N are dropped. The value of N depends on the actual file — never assume a fixed number.

**Q: After `--header-row`, the columns are still messy (e.g. `score_a`, `unnamed_3`). What next?**

Use `--transform-code` at chart generation to rename columns:
```bash
python {skill_base}/scripts/cli.py data.xls bar \
  --header-row 2 \
  --transform-code "result = df.rename(columns={'unnamed_0':'student_id','unnamed_1':'name','score_a':'homework','score_b':'exam'})" \
  --x-axis student_id --y-axis homework exam
```

**Q: The Excel file has multiple sheets. How do I pick one?**

```bash
python {skill_base}/scripts/data_parser.py data.xlsx --sheet "Sheet2"
# or by index
python {skill_base}/scripts/data_parser.py data.xlsx --sheet 1
```

**Q: Some cells are blank because of merged cells (only the first row of a group is filled).**

Forward-fill in transform code:
```bash
--transform-code "result = df.ffill()"
```

**Q: The data has leading note rows / blank rows before the actual header.**

Use `--skiprows N` to skip the first N rows, then read the next row as the header:
```bash
python {skill_base}/scripts/data_parser.py data.csv --skiprows 2
```

**Q: The chart shows mixed languages (e.g. Chinese data but English buttons, or vice versa).**

The CLI auto-detects the data language and renders all chart text (title, series names, tooltip, buttons, footer, HTML `lang`) in that language. If the auto-detection is wrong (e.g. a Chinese dataset with mostly English column names), force the language explicitly:
```bash
python {skill_base}/scripts/cli.py data.csv bar --lang zh
# or
python {skill_base}/scripts/cli.py data.csv bar --lang en
```
Only pass `--lang` when the user explicitly requests a specific language; otherwise let the data drive the choice.
