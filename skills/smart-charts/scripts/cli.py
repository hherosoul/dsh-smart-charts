"""Chart generation CLI entry point.

参数解析统一走 argparse（未知 flag / 缺参 / 类型错误均以结构化 JSON 报错，
不再静默跳过）；所有错误路径输出 SmartChartsError.to_dict() 结构。
"""

import sys
import json
import argparse
from pathlib import Path

if __name__ == '__main__' and __package__ is None:
    import _bootstrap  # noqa: F401 — 单点 sys.path 引导，见 _bootstrap.py
    from scripts.data_parser import DataParser
    from scripts.chart_generator import ChartGenerator
    from scripts.data_transformer import DataTransformer
    from scripts.exceptions import SmartChartsError, ChartError, ErrorCode, JSONArgumentParser
else:
    from .data_parser import DataParser
    from .chart_generator import ChartGenerator
    from .data_transformer import DataTransformer
    from .exceptions import SmartChartsError, ChartError, ErrorCode, JSONArgumentParser


def _emit_error(err: SmartChartsError) -> None:
    print(json.dumps(err.to_dict(), ensure_ascii=False), file=sys.stderr)


def _positive_int(value: str) -> int:
    try:
        v = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"需要整数，实际为: {value!r}")
    if v <= 0:
        raise argparse.ArgumentTypeError(f"需要正整数，实际为: {v}")
    return v


def _non_negative_int(value: str) -> int:
    try:
        v = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"需要整数，实际为: {value!r}")
    if v < 0:
        raise argparse.ArgumentTypeError(f"需要非负整数，实际为: {v}")
    return v


def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(
        prog='cli.py',
        description='Smart Charts：数据文件 → 独立交互式 ECharts HTML',
    )
    parser.add_argument('file_path', help='数据文件路径（CSV/TSV/Excel/JSON/TXT）')
    parser.add_argument('chart_type', nargs='?', default=None,
                        help='图表类型（单图模式）；多图模式用 --charts / --charts-file 代替')
    parser.add_argument('--title', default=None, help='图表标题')
    parser.add_argument('--x-axis', dest='x_axis', default=None, help='X 轴 / 类别列名')
    parser.add_argument('--y-axis', dest='y_axis', nargs='+', default=None,
                        help='Y 轴数值列（可多个；bubble 依次为 y 值列、size 列）')
    parser.add_argument('--transform-code', dest='transform_code', default=None,
                        help='pandas 转换代码（须产出 result DataFrame）')
    parser.add_argument('--output-dir', dest='output_dir', default='./smart_charts_output',
                        help='HTML 输出目录（默认 ./smart_charts_output）')
    parser.add_argument('--theme', default='default', help='主题: default / classic / dark')
    parser.add_argument('--skiprows', type=_positive_int, default=None,
                        help='跳过文件前 N 行再读取')
    parser.add_argument('--header-row', dest='header_row', type=_non_negative_int, default=None,
                        help='第 N 行（0-based）作为列名，其上方行丢弃')
    parser.add_argument('--sheet', dest='sheet', default=None,
                        help='Excel 工作表名称或索引（默认第 0 个）')
    parser.add_argument('--lang', choices=['zh', 'en'], default=None,
                        help='图表文本语言（默认按数据自动检测）')
    parser.add_argument('--label-col', dest='label_col', default=None,
                        help='身份列（如姓名），进散点/气泡/箱线离群点的 tooltip')
    parser.add_argument('--color-by', dest='color_by', default=None,
                        help='着色列（scatter/bubble；数值列→连续着色，类别列→拆系列）')
    parser.add_argument('--annotation', default=None, help='图表说明文字（默认自动生成）')
    parser.add_argument('--width', type=_positive_int, default=900, help='HTML 画布宽度 px（默认 900）')
    parser.add_argument('--height', type=_positive_int, default=560, help='HTML 画布高度 px（默认 560）')
    parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                        help='只校验并计算 plot_stats，不写 HTML')
    parser.add_argument('--charts', default=None,
                        help="多图模式：JSON 数组，如 '[{\"type\":\"bar\",\"x_axis\":\"city\",\"y_axis\":[\"revenue\"]}]'")
    parser.add_argument('--charts-file', dest='charts_file', default=None,
                        help='从 JSON 文件读取 --charts 配置（推荐，避免 shell 转义问题）')
    return parser


def _parse_charts_json(charts_json: str):
    """校验 --charts 参数：必须是 JSON 数组，每项为含 type 字段的对象。

    每项可用字段：type(必填), title, x_axis, y_axis(字符串或数组),
    transform_code(单图级), label_col, color_by, width, height。
    校验失败抛 ChartError（结构化错误，含 suggestion）。
    """
    try:
        charts_cfg = json.loads(charts_json)
    except json.JSONDecodeError as e:
        raise ChartError(
            f"--charts 不是合法 JSON: {e}",
            ErrorCode.CHART_CONFIG_ERROR,
            details={
                'given': charts_json[:200],
                'error': str(e),
                'suggestion': '传入 JSON 数组，如: \'[{"type":"bar","x_axis":"city","y_axis":["revenue"]}]\'',
            },
        )
    if not isinstance(charts_cfg, list) or not charts_cfg:
        raise ChartError(
            "--charts 必须是非空 JSON 数组",
            ErrorCode.CHART_CONFIG_ERROR,
            details={
                'given_type': type(charts_cfg).__name__,
                'suggestion': '传入非空数组，每项形如 {"type":"line","title":"趋势","x_axis":"date","y_axis":["revenue"]}',
            },
        )
    for idx, cfg in enumerate(charts_cfg):
        if not isinstance(cfg, dict) or 'type' not in cfg:
            raise ChartError(
                f"--charts 第 {idx} 项必须是含 type 字段的对象",
                ErrorCode.CHART_CONFIG_ERROR,
                details={
                    'index': idx,
                    'given': str(cfg)[:200],
                    'suggestion': '每项形如 {"type":"bar","title":"标题","x_axis":"列名","y_axis":["列1","列2"]}',
                },
            )
    return charts_cfg


def main(argv=None):
    parser = build_parser()
    try:
        ns = parser.parse_args(argv)
    except SmartChartsError as e:
        # argparse 的未知 flag / 非法取值 / 类型错误经 JSONArgumentParser.error
        # 抛出 ChartError，这里统一转结构化 JSON 输出
        _emit_error(e)
        sys.exit(1)

    charts_json = ns.charts
    if ns.charts_file:
        try:
            charts_json = Path(ns.charts_file).read_text(encoding='utf-8')
        except OSError as e:
            _emit_error(FileNotFoundError_e(ns.charts_file, e))
            sys.exit(1)

    sheet_name = ns.sheet
    if sheet_name is not None and sheet_name.lstrip('-').isdigit():
        sheet_name = int(sheet_name)

    # 兼容 --y-axis "revenue profit"（引号内空格分隔）与 --y-axis revenue profit（独立参数）两种传参；
    # 规范化后的列名不含空格，按空白拆分是安全的
    y_axis_cols = None
    if ns.y_axis:
        y_axis_cols = [c for item in ns.y_axis for c in item.split()]

    try:
        if ns.chart_type is None and charts_json is None:
            raise ChartError(
                "缺少图表类型参数（单图模式需 <chart_type>，多图模式需 --charts 或 --charts-file）",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'suggestion': '如 python cli.py data.csv bar --x-axis city --y-axis revenue'},
            )

        dp = DataParser()
        df = dp.parse_file(ns.file_path, skiprows=ns.skiprows, header_row=ns.header_row,
                           sheet_name=sheet_name)
        gen = ChartGenerator(output_dir=ns.output_dir, theme=ns.theme)

        if charts_json is not None:
            # 多图模式：一次解析，批量生成；全局 transform 先应用，再执行各图配置
            charts_cfg = _parse_charts_json(charts_json)
            if ns.transform_code:
                df = DataTransformer().transform(df, ns.transform_code)
            result = gen.generate_multi_charts(df, charts_cfg, width=ns.width, height=ns.height,
                                               lang=ns.lang, dry_run=ns.dry_run)
            items = result['charts']
            succeeded = sum(1 for c in items if c.get('success'))
            summary = {'total': len(items), 'succeeded': succeeded, 'failed': len(items) - succeeded}
            print(json.dumps({'charts': items, 'summary': summary}, ensure_ascii=False))
            if succeeded == 0:
                sys.exit(1)
        else:
            result = gen.generate_chart(
                df, ns.chart_type, title=ns.title, x_axis=ns.x_axis, y_axis=y_axis_cols,
                transform_code=ns.transform_code, width=ns.width, height=ns.height,
                lang=ns.lang, label_col=ns.label_col, color_by=ns.color_by,
                annotation=ns.annotation, dry_run=ns.dry_run,
            )
            print(json.dumps(result, ensure_ascii=False))
            if not result['chart']['success']:
                sys.exit(1)
    except SmartChartsError as e:
        _emit_error(e)
        sys.exit(1)
    except Exception as e:
        _emit_error(ChartError(f"未知错误: {e}", ErrorCode.UNKNOWN_ERROR,
                               details={'error': str(e), 'type': type(e).__name__}))
        sys.exit(1)


def FileNotFoundError_e(path: str, e: OSError) -> ChartError:
    return ChartError(
        f"无法读取 --charts-file: {e}",
        ErrorCode.FILE_NOT_FOUND,
        details={'given': path, 'suggestion': '确认 JSON 配置文件路径正确且可读'},
    )


if __name__ == '__main__':
    main()
