"""图表生成器（纯编排层）。基于 DataFrame 生成独立的 ECharts 交互式 HTML 文件。

架构契约（P1 重构后）：
- 本类只做编排：参数校验 → 轴/身份列准备 → 构建 RenderContext → 调渲染器 →
  落盘 HTML / 计算 plot_stats。不承载统计实现（plot_stats.py）、
  文案（texts.py）、算法（stats_kernels.py）、模板细节（template.py）。
- 渲染所需状态全部显式放入 RenderContext 传递，不读写生成器实例属性
  （output_dir/_theme/_dir_ready 是生成器自身合法状态，除外）。
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum

from .exceptions import ChartError, ErrorCode, SmartChartsError
from .renderers import ChartRenderersMixin, RenderContext, detect_relation_cols
from .template import HTMLTemplateMixin
from .texts import get_texts
from .plot_stats import compute_plot_stats, stats_spreadsheet
from .themes import THEMES
from .data_transformer import DataTransformer


class ChartType(Enum):
    LINE = 'line'
    BAR = 'bar'
    PIE = 'pie'
    SCATTER = 'scatter'
    AREA = 'area'
    RADAR = 'radar'
    HEATMAP = 'heatmap'
    TREEMAP = 'treemap'
    GRAPH = 'graph'
    BOXPLOT = 'boxplot'
    WATERFALL = 'waterfall'
    GAUGE = 'gauge'
    SANKEY = 'sankey'
    FUNNEL = 'funnel'
    SUNBURST = 'sunburst'
    WORDCLOUD = 'wordcloud'
    HISTOGRAM = 'histogram'
    STACKED_BAR = 'stacked_bar'
    BUBBLE = 'bubble'
    PARETO = 'pareto'
    COMBO = 'combo'
    VENN = 'venn'
    MINDMAP = 'mindmap'
    ORGCHART = 'orgchart'
    LIQUID = 'liquid'
    SPREADSHEET = 'spreadsheet'


class ChartGenerator(ChartRenderersMixin, HTMLTemplateMixin):
    """26 种图表的编排入口；HTML 落盘方法来自 HTMLTemplateMixin。"""

    # 身份列自动探测的列名提示词（小写匹配，命中者优先）
    _LABEL_HINTS = ('姓名', '名称', '名字', 'name', 'label', 'title', 'id')

    def __init__(self, output_dir: str = './smart_charts_output', theme: str = 'default'):
        if theme not in THEMES:
            raise ChartError(
                f"不支持的主题: {theme}",
                ErrorCode.CHART_CONFIG_ERROR,
                details={
                    'given': theme,
                    'supported': list(THEMES.keys()),
                    'suggestion': f"从 available 主题中选择: {', '.join(THEMES.keys())}",
                },
            )
        self.output_dir = Path(output_dir)
        self._theme = THEMES[theme]
        self._dir_ready = False

    def _ensure_output_dir(self):
        if not self._dir_ready:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._dir_ready = True

    def generate_chart(
        self,
        df: pd.DataFrame,
        chart_type: str,
        title: Optional[str] = None,
        x_axis: Optional[str] = None,
        y_axis: Optional[List[str]] = None,
        transform_code: Optional[str] = None,
        width: int = 900,
        height: int = 560,
        lang: Optional[str] = None,
        label_col: Optional[str] = None,
        color_by: Optional[str] = None,
        annotation: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """生成单个图表，返回统一结构 {'chart': {'success', 'html_path'/'error', ...}}。

        lang: 'zh' / 'en' 强制指定图表文本语言；None 时按数据自动检测。
        title: None 时使用 lang 对应的默认标题。
        label_col: 身份列（如姓名），其值进数据点 name 和 tooltip（scatter/bubble/boxplot）。
            None 时按列名启发式自动探测（命中时记入返回值的 assumptions 字段）。
        color_by: 着色列（scatter/bubble）。数值列 → visualMap 连续着色；类别列 → 拆 series 分色。
        dry_run: True 时只算 plot_stats/data_preview 并校验渲染配置，不写 HTML（html_path 为 null）。
        失败时不抛异常，返回 success=False + error 结构，便于智能体程序化处理。
        """
        try:
            if df.empty:
                raise ChartError("数据为空", ErrorCode.DATA_EMPTY)
            if lang is not None and lang not in ('zh', 'en'):
                raise ChartError(
                    f"不支持的 lang: {lang}，支持: zh / en",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={'given': lang, 'supported': ['zh', 'en'],
                             'suggestion': '省略 --lang 让语言跟随数据自动检测，或显式传 zh / en'},
                )
            try:
                ct = ChartType(chart_type)
            except ValueError:
                supported = [t.value for t in ChartType]
                raise ChartError(
                    f"不支持的图表类型: {chart_type}，支持: {supported}",
                    ErrorCode.CHART_TYPE_UNSUPPORTED,
                    details={
                        'given': chart_type,
                        'supported': supported,
                        'suggestion': '参考 SKILL.md 图表类型表',
                    },
                )

            if transform_code:
                df = DataTransformer().transform(df, transform_code)

            texts, lang_resolved = get_texts(lang, df)
            if title is None:
                title = texts['default_title']
            # annotation 必选：未显式提供时生成默认说明，保证每张图都有「图表说明」区块
            if annotation is None or not str(annotation).strip():
                annotation = texts['default_annotation'].format(n=len(df))

            if ct is ChartType.SPREADSHEET:
                return self._generate_spreadsheet(
                    df, title, x_axis, y_axis, width, height, texts, lang_resolved,
                    annotation, dry_run,
                )

            gen = getattr(self, f'_{ct.value}', None)
            if gen is None:
                # 只可能因新增 ChartType 枚举尚未实现渲染器
                raise ChartError(
                    f"暂不支持该图表类型: {chart_type}",
                    ErrorCode.CHART_TYPE_UNSUPPORTED,
                    details={'given': chart_type},
                )

            x_axis, y_axis = self._prepare_axes(df, chart_type, x_axis, y_axis)

            # label_col / color_by 校验与自动探测
            assumptions = []
            for param, col in (('label_col', label_col), ('color_by', color_by)):
                if col is not None and col not in df.columns:
                    raise ChartError(
                        f"{param} 字段不存在: {col}",
                        ErrorCode.CHART_CONFIG_ERROR,
                        details={
                            'given': col,
                            'available': list(df.columns),
                            'suggestion': '从 available 列中选择一个已存在的列',
                        },
                    )
            if label_col is None and chart_type in ('scatter', 'bubble', 'boxplot'):
                label_col = self._detect_label_col(df, x_axis, y_axis)
                if label_col is not None:
                    assumptions.append(f'label 列自动选择: {label_col}（可用 --label-col 覆盖或置空）')
            if chart_type in ('graph', 'sankey'):
                _src, _tgt, _ = detect_relation_cols(df)
                if not (_src and _tgt):
                    assumptions.append('未识别到 source/target 关系列，已按链式连接降级（可将列重命名为 源/目标，或使用含 来源/去向 的列名）')

            ctx = RenderContext(
                df=df, x=x_axis, y=y_axis, title=title, texts=texts, theme=self._theme,
                lang=lang_resolved, label_col=label_col, color_by=color_by,
                width=width, height=height,
            )
            option = gen(ctx)
            data_points = self._estimate_data_points(df, chart_type, x_axis, y_axis)
            plot_stats = compute_plot_stats(df, chart_type, x_axis, y_axis, label_col=label_col)
            if dry_run:
                html_path = None
            else:
                html_path = self._save_html(ctx, option, width, height, chart_type, data_points, annotation)
            # A3: 绘图数据内联回显——让调用方在生成当轮即可校对聚合口径，无需打开 HTML
            preview, data_rows = self._data_preview(df, x_axis, y_axis)
            chart_result = {
                'success': True,
                'dry_run': dry_run,
                'html_path': str(html_path) if html_path is not None else None,
                'chart_type': chart_type,
                'title': title,
                'data_rows': data_rows,
                'data_preview': preview,
            }
            if plot_stats is not None:
                chart_result['plot_stats'] = plot_stats
            if assumptions:
                chart_result['assumptions'] = assumptions
            return {'chart': chart_result}
        except SmartChartsError as e:
            return {
                'chart': {
                    'success': False,
                    'error': e.to_dict(),
                    'chart_type': chart_type,
                    'title': title or '',
                }
            }
        except Exception as e:
            return {
                'chart': {
                    'success': False,
                    'error': {'error': str(e), 'code': ErrorCode.CHART_GENERATION_ERROR.value, 'code_name': ErrorCode.CHART_GENERATION_ERROR.name},
                    'chart_type': chart_type,
                    'title': title or '',
                }
            }

    def _generate_spreadsheet(
        self, df: pd.DataFrame, title: str, x_axis: Optional[str], y_axis: Optional[List[str]],
        width: int, height: int, texts: Dict[str, str], lang: str,
        annotation: str, dry_run: bool,
    ) -> Dict[str, Any]:
        # 表格无轴/系列概念：x/y 仅用于筛选显示列（x 在前），都不传则显示全部列。
        # 聚合/透视由 transform_code 完成（与图表管线口径一致），表格只负责呈现。
        if isinstance(y_axis, str):
            y_axis = [y_axis]
        shown = ([x_axis] if x_axis is not None else []) + [c for c in (y_axis or []) if c != x_axis]
        for col in shown:
            if col not in df.columns:
                raise ChartError(
                    f"列不存在: {col}",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={
                        'given': col,
                        'available': list(df.columns),
                        'suggestion': '从 available 列中选择一个已存在的列',
                    },
                )
        df_table = df[shown] if shown else df
        plot_stats = stats_spreadsheet(df_table)
        if dry_run:
            html_path = None
        else:
            ctx = RenderContext(df=df_table, x=None, y=[], title=title, texts=texts,
                                theme=self._theme, lang=lang)
            html_path = self._save_table_html(ctx, df_table, title, width, height, annotation)
        preview, data_rows = self._data_preview(df, None, None)
        chart_result = {
            'success': True,
            'dry_run': dry_run,
            'html_path': str(html_path) if html_path is not None else None,
            'chart_type': 'spreadsheet',
            'title': title,
            'data_rows': data_rows,
            'data_preview': preview,
        }
        if plot_stats is not None:
            chart_result['plot_stats'] = plot_stats
        return {'chart': chart_result}

    def generate_multi_charts(
        self,
        df: pd.DataFrame,
        chart_configs: List[Dict[str, Any]],
        width: int = 900,
        height: int = 560,
        lang: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """批量生成多个图表，返回 {'charts': [{'success', 'html_path'/'error', ...}]}。

        每项结构与 generate_chart 的 {'chart': {...}} 内部一致，便于智能体统一解析。
        """
        results = []
        for cfg in chart_configs:
            r = self.generate_chart(
                df=df,
                chart_type=cfg.get('type', 'bar'),
                title=cfg.get('title') or None,
                x_axis=cfg.get('x_axis'),
                y_axis=cfg.get('y_axis'),
                transform_code=cfg.get('transform_code'),
                width=cfg.get('width', width),
                height=cfg.get('height', height),
                lang=lang,
                label_col=cfg.get('label_col'),
                color_by=cfg.get('color_by'),
                annotation=cfg.get('annotation'),
                dry_run=dry_run,
            )
            chart_result = r['chart']
            chart_result['config'] = cfg
            results.append(chart_result)
        return {'charts': results}

    # ---- 轴自动检测 ----

    def _prepare_axes(self, df, chart_type, x_axis, y_axis) -> Tuple[str, List[str]]:
        # 直方图无类别轴，只有一个分布数值列：用户显式传入的数值 x 就是分布列，
        # 锁定为 y，防止下方 y 自动补全换成其他数值列
        # （如 df=[学号,总成绩] + --x-axis 总成绩 时 y 被自动补成学号，画出错误分布）
        if (chart_type == 'histogram'
                and x_axis is not None and x_axis in df.columns
                and pd.api.types.is_numeric_dtype(df[x_axis])):
            y_axis = [x_axis]

        # 层级图（mindmap/orgchart）：x=父节点列，y[0]=子节点列（均为分类列）。
        # 未显式指定时先识别 source/target 关系列，再退到前两个分类列。
        if chart_type in ('mindmap', 'orgchart'):
            if not (x_axis is not None and y_axis):
                src, tgt, _ = detect_relation_cols(df)
                if src and tgt:
                    x_axis, y_axis = src, [tgt]
                else:
                    cat_cols = df.select_dtypes(include=['object', 'string', 'category']).columns.tolist()
                    if x_axis is None:
                        if len(cat_cols) >= 2:
                            x_axis, y_axis = cat_cols[0], [cat_cols[1]]
                    else:
                        cands = [c for c in cat_cols if c != x_axis]
                        if cands:
                            y_axis = [cands[0]]
            if y_axis is None or x_axis is None:
                raise ChartError(
                    f"{chart_type} 需要 父节点列(x) + 子节点列(y) 两个分类列",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={
                        'available': list(df.columns),
                        'suggestion': '用 --x-axis <父列> --y-axis <子列> 指定层级关系，或将列命名为 来源/去向',
                    },
                )

        if x_axis is None:
            date_cols = df.select_dtypes(include=['datetime', 'datetime64']).columns
            cat_cols = df.select_dtypes(include=['object', 'string', 'category']).columns
            x_axis = date_cols[0] if len(date_cols) > 0 else (cat_cols[0] if len(cat_cols) > 0 else df.columns[0])

        if y_axis is None:
            avail = [c for c in df.columns if c != x_axis]
            nums = df[avail].select_dtypes(include=[np.number]).columns.tolist()
            y_axis = nums[:5] if nums else avail[:3]
        elif isinstance(y_axis, str):
            y_axis = [y_axis]

        if x_axis not in df.columns:
            raise ChartError(
                f"X轴字段不存在: {x_axis}",
                ErrorCode.CHART_CONFIG_ERROR,
                details={
                    'given': x_axis,
                    'available': list(df.columns),
                    'suggestion': '从 available 列中选择一个已存在的列，或提供 transform_code 生成所需列',
                },
            )
        for y in y_axis:
            if y not in df.columns:
                raise ChartError(
                    f"Y轴字段不存在: {y}",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={
                        'given': y,
                        'available': list(df.columns),
                        'suggestion': '从 available 列中选择一个已存在的列，或提供 transform_code 生成所需列',
                    },
                )
        return x_axis, y_axis

    def _detect_label_col(self, df: pd.DataFrame, x_axis: str, y_axis: List[str]) -> Optional[str]:
        """身份列自动探测：在未被 x/y 占用的字符串列中，按列名提示词（姓名/name/id 等）选最可能的一列。

        无提示词命中时取第一个候选列；无候选返回 None（图表退化为无身份标识）。
        """
        used = {x_axis, *y_axis}
        cands = [
            c for c in df.columns if c not in used
            and (df[c].dtype == 'object' or pd.api.types.is_string_dtype(df[c]))
        ]
        if not cands:
            return None
        for c in cands:
            cl = str(c).lower()
            if any(h in cl for h in self._LABEL_HINTS):
                return c
        return cands[0]

    def _data_preview(self, df: pd.DataFrame, x_axis: Optional[str], y_axis: Optional[List[str]], limit: int = 10) -> Tuple[List[Dict[str, Any]], int]:
        """生成最终绘图数据的紧凑预览（stdout 的 data_preview / data_rows 字段）。

        取 transform 之后、渲染所用的同一份 DataFrame 中 [x_axis] + y_axis 列的前 limit 行：
        NaN/NaT → None；数值统一转 JSON 可序列化的 int/float；其余转 str。
        x_axis/y_axis 均为 None 时（spreadsheet 全列模式）取全部列。
        供调用方在生成当轮校对聚合口径（按行 vs 按去重实体），无需打开 HTML 文件。
        """
        cols = list(dict.fromkeys(
            ([x_axis] if x_axis is not None else []) + list(y_axis or []))) or list(df.columns)
        records: List[Dict[str, Any]] = []
        for _, row in df[cols].head(limit).iterrows():
            rec: Dict[str, Any] = {}
            for c in cols:
                v = row[c]
                try:
                    if v is None or pd.isna(v):
                        rec[c] = None
                        continue
                except (TypeError, ValueError):
                    pass
                if isinstance(v, str):
                    rec[c] = v
                elif isinstance(v, (bool, np.bool_)):
                    rec[c] = bool(v)
                else:
                    try:
                        f = float(v)
                        rec[c] = int(f) if f.is_integer() and abs(f) < 2 ** 53 else f
                    except (TypeError, ValueError):
                        rec[c] = str(v)
            records.append(rec)
        return records, len(df)

    def _estimate_data_points(self, df: pd.DataFrame, chart_type: str, x_axis: str, y_axis: List[str]) -> int:
        """估算图表 X 轴类别数量，用于决定 HTML 容器是否需要横向滚动兜底。

        只有 X 轴为类别轴且数据点可能过多的图表（bar/line/area 等）才返回非零值；
        heatmap 是网格布局，每个单元格远窄于柱状图柱子，不需要横向滚动；
        scatter（数值轴）/boxplot（列名轴）/pie/treemap 等也不需要，返回 0。
        """
        try:
            if chart_type in ('bar', 'line', 'area', 'stacked_bar', 'combo', 'pareto'):
                return len(df)
        except Exception:
            pass
        return 0
