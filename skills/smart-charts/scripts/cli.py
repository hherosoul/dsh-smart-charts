"""Chart generation CLI entry point."""

import sys
import json
from pathlib import Path

if __name__ == '__main__' and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.data_parser import DataParser
    from scripts.chart_generator import ChartGenerator
    from scripts.exceptions import SmartChartsError
else:
    from .data_parser import DataParser
    from .chart_generator import ChartGenerator
    from .exceptions import SmartChartsError


def main():
    if len(sys.argv) < 3:
        print("用法: python cli.py <file_path> <chart_type> [--title 标题] [--x-axis 列名] [--y-axis 列1 列2] [--transform-code 代码] [--output-dir 目录] [--skiprows N] [--header-row N] [--sheet <name|index>] [--lang zh|en] [--label-col 列名] [--color-by 列名]")
        sys.exit(1)

    args = sys.argv[1:]
    file_path = args[0]
    chart_type = args[1]

    title = None
    x_axis = None
    y_axis = None
    transform_code = None
    output_dir = './smart_charts_output'
    skiprows = None
    header_row = None
    sheet_name = 0
    lang = None
    label_col = None
    color_by = None

    i = 2
    while i < len(args):
        if args[i] == '--title' and i + 1 < len(args):
            title = args[i + 1]; i += 2
        elif args[i] == '--x-axis' and i + 1 < len(args):
            x_axis = args[i + 1]; i += 2
        elif args[i] == '--y-axis':
            y_list = []
            i += 1
            while i < len(args) and not args[i].startswith('--'):
                y_list.extend(args[i].split())
                i += 1
            y_axis = y_list if y_list else None
        elif args[i] == '--transform-code' and i + 1 < len(args):
            transform_code = args[i + 1]; i += 2
        elif args[i] == '--output-dir' and i + 1 < len(args):
            output_dir = args[i + 1]; i += 2
        elif args[i] == '--skiprows' and i + 1 < len(args):
            skiprows = int(args[i + 1]); i += 2
        elif args[i] == '--header-row' and i + 1 < len(args):
            header_row = int(args[i + 1]); i += 2
        elif args[i] == '--sheet' and i + 1 < len(args):
            v = args[i + 1]
            sheet_name = int(v) if v.lstrip('-').isdigit() else v
            i += 2
        elif args[i] == '--lang' and i + 1 < len(args):
            lang = args[i + 1]; i += 2
        elif args[i] == '--label-col' and i + 1 < len(args):
            label_col = args[i + 1]; i += 2
        elif args[i] == '--color-by' and i + 1 < len(args):
            color_by = args[i + 1]; i += 2
        else:
            i += 1

    try:
        dp = DataParser()
        df = dp.parse_file(file_path, skiprows=skiprows, header_row=header_row, sheet_name=sheet_name)
        gen = ChartGenerator(output_dir=output_dir)
        result = gen.generate_chart(df, chart_type, title=title, x_axis=x_axis, y_axis=y_axis,
                                    transform_code=transform_code, lang=lang,
                                    label_col=label_col, color_by=color_by)
        print(json.dumps(result, ensure_ascii=False))
        if not result['chart']['success']:
            sys.exit(1)
    except SmartChartsError as e:
        print(json.dumps(e.to_dict(), ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
