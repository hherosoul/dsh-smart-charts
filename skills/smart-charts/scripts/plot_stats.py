"""plot_stats 统计摘要层：基于绘图数据（transform 后、x/y 选列后）计算统计摘要。

覆盖全部 26 类图表，归入 7 个家族：
A 类别×数值: line / bar / area / stacked_bar / combo / pareto
B name×value: pie / treemap / funnel / sunburst / wordcloud / venn
C 关系流:    graph / sankey / mindmap / orgchart
D 分布:      histogram / boxplot
E 相关:      scatter / bubble
F 专项:      radar / heatmap / waterfall / gauge / liquid
G 表格:      spreadsheet

所有共享算法（分箱/IQR/瀑布/帕累托/量程）一律引用 stats_kernels，
与 renderers 渲染侧同源——报告的事实必须与图形呈现的事实一致，任何一侧不得私改公式。
"""

import numpy as np
import pandas as pd
from typing import Any, Dict, List, Optional

from .stats_kernels import (
    pt, box_stats, sturges_bins, bin_labels, waterfall_walk, pareto_stats, gauge_scale,
    safe_str_list, safe_str_series,
)
from .renderers import detect_relation_cols


def compute_plot_stats(
    df: pd.DataFrame,
    chart_type: str,
    x_axis: Optional[str],
    y_axis: Optional[List[str]],
    label_col: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """统计摘要入口。chart_type 不在已知家族时返回 None。"""
    if chart_type == 'spreadsheet':
        return stats_spreadsheet(df)
    try:
        df = df.reset_index(drop=True)
    except Exception:
        pass
    if chart_type in ('line', 'bar', 'area', 'stacked_bar', 'combo', 'pareto'):
        return _stats_family_a(df, chart_type, x_axis, y_axis)
    if chart_type in ('pie', 'treemap', 'funnel', 'sunburst', 'wordcloud', 'venn'):
        return _stats_family_b(df, chart_type, x_axis, y_axis)
    if chart_type in ('graph', 'sankey', 'mindmap', 'orgchart'):
        return _stats_family_c(df, chart_type, x_axis, y_axis)
    if chart_type in ('histogram', 'boxplot'):
        return _stats_family_d(df, chart_type, x_axis, y_axis)
    if chart_type in ('scatter', 'bubble'):
        return _stats_family_e(df, chart_type, x_axis, y_axis, label_col)
    if chart_type in ('radar', 'heatmap', 'waterfall', 'gauge', 'liquid'):
        return _stats_family_f(df, chart_type, x_axis, y_axis)
    return None


# ---- A 家族：类别 × 数值 ----

def _series_stat(df: pd.DataFrame, x_col: str, y_col: str) -> Dict[str, Any]:
    """单个数值系列的基础统计（max/min/mean/sum/top3/bottom3，带 x 标签）。"""
    s = df[y_col]
    x = df[x_col]
    out: Dict[str, Any] = {'name': y_col}
    if not pd.api.types.is_numeric_dtype(s):
        return out
    try:
        out['max'] = {'value': pt(s.max()), 'at': str(x.loc[s.idxmax()])}
        out['min'] = {'value': pt(s.min()), 'at': str(x.loc[s.idxmin()])}
        out['mean'] = pt(s.mean())
        out['sum'] = pt(s.sum())
    except (ValueError, TypeError, KeyError):
        return out
    out['top3'] = [{'x': str(x.loc[i]), 'v': pt(v)} for i, v in s.nlargest(3).items()]
    out['bottom3'] = [{'x': str(x.loc[i]), 'v': pt(v)} for i, v in s.nsmallest(3).items()]
    return out


def _trend_stat(df: pd.DataFrame, y_col: str) -> Optional[Dict[str, Any]]:
    """时间序趋势：首值、末值、方向、涨跌幅。"""
    s = df[y_col]
    if not pd.api.types.is_numeric_dtype(s) or len(s) < 2:
        return None
    first, last = float(s.iloc[0]), float(s.iloc[-1])
    if abs(first) < 1e-9:
        return {'first': round(first, 2), 'last': round(last, 2), 'direction': 'flat', 'delta_pct': 0.0}
    delta = (last - first) / abs(first) * 100
    direction = 'up' if delta > 0.5 else ('down' if delta < -0.5 else 'flat')
    return {'first': round(first, 2), 'last': round(last, 2), 'direction': direction, 'delta_pct': round(delta, 2)}


def _stats_family_a(df: pd.DataFrame, chart_type: str, x_axis: str, y_axis: List[str]) -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        'family': 'A',
        'x_col': x_axis,
        'x_cardinality': int(df[x_axis].nunique()),
        'series': [],
    }
    for idx, col in enumerate(y_axis):
        if col not in df.columns:
            continue
        s = _series_stat(df, x_axis, col)
        if chart_type == 'combo':
            s['role'] = 'bar' if idx == 0 else 'line'
        if chart_type in ('line', 'area'):
            s['trend'] = _trend_stat(df, col)
        if chart_type == 'combo' and idx > 0:
            s['trend'] = _trend_stat(df, col)
        stats['series'].append(s)
    if chart_type == 'stacked_bar':
        sums = {}
        for c in y_axis:
            if c in df.columns and pd.api.types.is_numeric_dtype(df[c]):
                sums[c] = float(df[c].sum())
        total = sum(sums.values()) or 1.0
        for s in stats['series']:
            if s['name'] in sums:
                s['share'] = round(sums[s['name']] / total, 4)
    if chart_type == 'pareto' and y_axis and y_axis[0] in df.columns:
        # 与 _pareto 渲染同源：同一 pareto_stats 累计算法
        sub = df[[x_axis, y_axis[0]]].dropna().sort_values(y_axis[0], ascending=False)
        ps = pareto_stats(sub[y_axis[0]].tolist())
        stats['extra'] = {
            'total': ps['total'],
            'n_items': ps['n_items'],
            'top3_share': ps['top3_share'],
            'items_to_80pct': ps['items_to_80pct'],
        }
    return stats


# ---- B 家族：name × value ----

def _stats_family_b(df: pd.DataFrame, chart_type: str, x_axis: str, y_axis: List[str]) -> Dict[str, Any]:
    y_col = y_axis[0] if (y_axis and y_axis[0] in df.columns) else df.columns[-1]
    x_col = x_axis if x_axis in df.columns else df.columns[0]
    items: List[Dict[str, Any]] = []
    total = 0.0
    if pd.api.types.is_numeric_dtype(df[y_col]):
        for n, v in zip(safe_str_list(df[x_col]), df[y_col].tolist()):
            fv = pt(v)
            if fv is None:
                continue
            items.append({'name': n, 'value': fv})
            total += fv
    else:
        for n, v in safe_str_series(df[x_col]).value_counts().items():
            items.append({'name': n, 'value': int(v)})
            total += int(v)
    for it in items:
        it['share'] = round(it['value'] / total, 4) if total else 0.0
    truncated = len(items) > 50
    if truncated:
        items = sorted(items, key=lambda x: -x['value'])[:20]
    stats: Dict[str, Any] = {
        'family': 'B',
        'x_col': x_col,
        'x_cardinality': int(df[x_col].nunique()),
        'extra': {'total': round(total, 2), 'items': items},
    }
    if truncated:
        stats['extra']['truncated'] = True
    if chart_type == 'funnel' and len(items) >= 2:
        ordered = sorted(items, key=lambda x: -x['value'])
        conv = []
        for i in range(1, len(ordered)):
            prev, cur = ordered[i - 1], ordered[i]
            conv.append({'from': prev['name'], 'to': cur['name'],
                         'rate': round(cur['value'] / prev['value'], 4) if prev['value'] else None})
        stats['extra']['conversion'] = conv
    return stats


# ---- C 家族：关系流 ----

def _stats_tree(df: pd.DataFrame, x_axis: str, y_axis: List[str]) -> Dict[str, Any]:
    """层级图（mindmap/orgchart）统计：节点/边/根数量与最大深度。"""
    child_col = y_axis[0] if y_axis and y_axis[0] in df.columns else None
    if child_col is None or x_axis not in df.columns:
        return {'family': 'C', 'x_col': x_axis, 'extra': {}}
    # 与 renderers._build_tree 同口径：safe_str_list（NaN→''），空名端点的边剔除
    edges = [(p, c) for p, c in zip(safe_str_list(df[x_axis]), safe_str_list(df[child_col]))
             if p and c]
    child_map: Dict[str, List[str]] = {}
    for p, c in edges:
        child_map.setdefault(p, []).append(c)
    nodes = set(child_map)
    for _, c in edges:
        nodes.add(c)
    children = {c for _, c in edges}
    roots = [n for n in nodes if n not in children]
    # BFS 求最大深度（seen 防御环状脏数据导致死循环）
    depth, seen = 0, set(roots)
    queue = [(r, 1) for r in roots]
    while queue:
        n, d = queue.pop(0)
        depth = max(depth, d)
        for c in child_map.get(n, []):
            if c not in seen:
                seen.add(c)
                queue.append((c, d + 1))
    return {'family': 'C', 'x_col': x_axis, 'extra': {
        'node_count': len(nodes),
        'edge_count': len(edges),
        'root_count': len(roots),
        'max_depth': depth,
    }}


def _stats_family_c(df: pd.DataFrame, chart_type: str, x_axis: str, y_axis: List[str]) -> Dict[str, Any]:
    if chart_type in ('mindmap', 'orgchart'):
        return _stats_tree(df, x_axis, y_axis)
    source_col, target_col, value_col = detect_relation_cols(df)
    if source_col and target_col:
        src = safe_str_list(df[source_col])
        tgt = safe_str_list(df[target_col])
        nodes = set(src) | set(tgt)
        edges = list(zip(src, tgt))
        if value_col and value_col in df.columns and pd.api.types.is_numeric_dtype(df[value_col]):
            vals = [pt(v) for v in df[value_col].tolist()]
        else:
            vals = [1.0] * len(edges)
    else:
        # 链式降级（与 _graph/_sankey 无 source/target 时的行为一致）
        xc = x_axis if x_axis in df.columns else df.columns[0]
        names = safe_str_list(df[xc])
        nodes = set(names)
        edges = [(names[i - 1], names[i]) for i in range(1, len(names))]
        if chart_type == 'sankey':
            y_col = y_axis[0] if (y_axis and y_axis[0] in df.columns) else df.columns[-1]
            if pd.api.types.is_numeric_dtype(df[y_col]):
                vals = [pt(v) if pt(v) is not None else 1.0 for v in df[y_col].tolist()[1:]]
            else:
                vals = [1.0] * len(edges)
        else:
            vals = [1.0] * len(edges)
    num_vals = [v if v is not None else 0.0 for v in vals]
    total_weight = sum(num_vals)
    extra: Dict[str, Any] = {
        'node_count': len(nodes),
        'edge_count': len(edges),
        'total_weight': round(total_weight, 2),
    }
    if edges:
        max_i = int(np.argmax(num_vals))
        extra['max_edge'] = {'source': edges[max_i][0], 'target': edges[max_i][1], 'value': pt(num_vals[max_i])}
        top = sorted(range(len(edges)), key=lambda i: -num_vals[i])[:5]
        extra['top_edges'] = [{'source': edges[i][0], 'target': edges[i][1], 'value': pt(num_vals[i])} for i in top]
    if chart_type == 'sankey' and edges:
        inflow: Dict[str, float] = {}
        outflow: Dict[str, float] = {}
        for (s, t), v in zip(edges, num_vals):
            inflow[t] = inflow.get(t, 0.0) + v
            outflow[s] = outflow.get(s, 0.0) + v
        ti = max(inflow, key=inflow.get)
        to = max(outflow, key=outflow.get)
        extra['top_in'] = {'node': ti, 'value': round(inflow[ti], 2)}
        extra['top_out'] = {'node': to, 'value': round(outflow[to], 2)}
    return {'family': 'C', 'x_col': x_axis, 'extra': extra}


# ---- D 家族：分布 ----

def _stats_family_d(df: pd.DataFrame, chart_type: str, x_axis: str, y_axis: List[str]) -> Dict[str, Any]:
    if chart_type == 'histogram':
        y_col = y_axis[0] if (y_axis and y_axis[0] in df.columns) else df.columns[-1]
        s = df[y_col].dropna() if y_col in df.columns else pd.Series(dtype='float64')
        if s.empty or not pd.api.types.is_numeric_dtype(s):
            return {'family': 'D', 'x_col': x_axis, 'extra': {}}
        # 与 _histogram 渲染同源：同一 sturges_bins 分箱
        counts, edges = sturges_bins(s)
        labels = bin_labels(edges, counts)
        bin_counts = [{'range': labels[i], 'count': int(counts[i])} for i in range(len(counts))]
        peak_i = int(np.argmax(counts))
        return {'family': 'D', 'x_col': x_axis, 'extra': {
            'bins': len(counts),
            'bin_range': [round(float(edges[0]), 1), round(float(edges[-1]), 1)],
            'bin_counts': bin_counts,
            'peak_bin': {'range': labels[peak_i], 'count': int(counts[peak_i])},
        }}
    # boxplot：与 _boxplot 渲染同源：同一 box_stats IQR 算法
    cols = [c for c in y_axis if c in df.columns] if y_axis else df.select_dtypes(include=[np.number]).columns[:5].tolist()
    columns = []
    for col in cols:
        s = df[col].dropna()
        if s.empty or not pd.api.types.is_numeric_dtype(s):
            continue
        st = box_stats(s)
        columns.append({'name': col, 'min': round(st['min'], 2), 'q1': round(st['q1'], 2),
                        'median': round(st['median'], 2), 'q3': round(st['q3'], 2),
                        'max': round(st['max'], 2),
                        'outliers': [pt(v) for v in st['outliers']]})
    return {'family': 'D', 'x_col': x_axis, 'extra': {'columns': columns}}


# ---- E 家族：相关 ----

def _stats_family_e(df: pd.DataFrame, chart_type: str, x_axis: str, y_axis: List[str],
                    label_col: Optional[str] = None) -> Dict[str, Any]:
    y_col = y_axis[0] if (y_axis and y_axis[0] in df.columns) else df.columns[-1]
    x_col = x_axis if x_axis in df.columns else df.columns[0]
    dims = [x_col, y_col]
    if chart_type == 'bubble' and len(y_axis) >= 2 and y_axis[1] in df.columns:
        dims.append(y_axis[1])
    series = []
    for c in dims:
        if c in df.columns and pd.api.types.is_numeric_dtype(df[c]):
            s = df[c]
            series.append({'name': c, 'min': pt(s.min()), 'max': pt(s.max()), 'mean': pt(s.mean())})
    extra: Dict[str, Any] = {'n_points': int(len(df))}
    if pd.api.types.is_numeric_dtype(df[x_col]) and pd.api.types.is_numeric_dtype(df[y_col]):
        try:
            corr = float(df[x_col].corr(df[y_col]))
            if not np.isnan(corr):
                extra['correlation'] = round(corr, 4)
        except Exception:
            pass
    if chart_type == 'bubble' and len(dims) == 3 and pd.api.types.is_numeric_dtype(df[dims[2]]):
        size_col = dims[2]
        idx = df[size_col].idxmax()
        extra['max_bubble'] = {'value': pt(df[size_col].max()),
                               'at': str(df.loc[idx, label_col]) if label_col and label_col in df.columns else str(df.loc[idx, x_col])}
    return {'family': 'E', 'x_col': x_col, 'series': series, 'extra': extra}


# ---- F 家族：专项 ----

def _stats_family_f(df: pd.DataFrame, chart_type: str, x_axis: str, y_axis: List[str]) -> Dict[str, Any]:
    if chart_type in ('gauge', 'liquid'):
        num_cols = df.select_dtypes(include=[np.number]).columns
        y_col = y_axis[0] if (y_axis and y_axis[0] in df.columns) else (num_cols[0] if len(num_cols) else None)
        if y_col is None or not pd.api.types.is_numeric_dtype(df[y_col]):
            return {'family': 'F', 'x_col': x_axis, 'extra': {}}
        mean = float(df[y_col].mean())
        data_max = float(df[y_col].max())
        # 与 _gauge/_liquid 渲染同源：同一 gauge_scale 三段量程（≤1→1.0，≤100→100，其余 ×1.05）
        max_val = gauge_scale(data_max)
        return {'family': 'F', 'x_col': x_axis, 'extra': {
            'mean': round(mean, 2), 'max': round(data_max, 2),
            'achievement': round(mean / max_val, 4) if max_val else None,
        }}
    if chart_type == 'waterfall':
        y_col = y_axis[0] if (y_axis and y_axis[0] in df.columns) else df.columns[-1]
        xc = x_axis if x_axis in df.columns else df.columns[0]
        # 与 _waterfall 渲染同源：同一 waterfall_walk 单遍累计
        _base, _heights, _signeds, wstats = waterfall_walk(df[y_col].tolist())
        extra: Dict[str, Any] = {'total_delta': wstats['total_delta'], 'first': wstats['first']}
        if wstats['max_pos_i'] is not None:
            extra['max_positive'] = {'x': str(df[xc].iloc[wstats['max_pos_i']]),
                                     'value': round(wstats['max_positive'], 2)}
        if wstats['max_neg_i'] is not None:
            extra['max_negative'] = {'x': str(df[xc].iloc[wstats['max_neg_i']]),
                                     'value': round(wstats['max_negative'], 2)}
        return {'family': 'F', 'x_col': xc, 'extra': extra}
    if chart_type == 'radar':
        indicators = safe_str_list(df[x_axis]) if x_axis in df.columns else []
        series = []
        for c in y_axis:
            if c not in df.columns:
                continue
            vals = [pt(v) for v in df[c].tolist()]
            entry: Dict[str, Any] = {'name': c, 'values': dict(zip(indicators, vals))}
            nz = [(ind, v) for ind, v in zip(indicators, vals) if v is not None]
            if nz:
                mx = max(nz, key=lambda x: x[1])
                mn = min(nz, key=lambda x: x[1])
                entry['max_dim'] = {'indicator': mx[0], 'value': mx[1]}
                entry['min_dim'] = {'indicator': mn[0], 'value': mn[1]}
            series.append(entry)
        return {'family': 'F', 'x_col': x_axis, 'extra': {'indicators': indicators, 'series': series}}
    # heatmap
    rows = safe_str_list(df[x_axis]) if x_axis in df.columns else []
    cols = [c for c in y_axis if c in df.columns]
    extra: Dict[str, Any] = {'rows': len(rows), 'cols': len(cols)}
    if rows and cols:
        arr = df[cols].to_numpy(dtype='float64')
        finite = arr[np.isfinite(arr)]
        if finite.size:
            vmin = float(finite.min())
            vmax = float(finite.max())
            extra['vmin'] = round(vmin, 2)
            extra['vmax'] = round(vmax, 2)
            max_i, max_j = np.unravel_index(np.nanargmax(arr), arr.shape)
            min_i, min_j = np.unravel_index(np.nanargmin(arr), arr.shape)
            extra['max_cell'] = {'row': rows[max_i], 'col': cols[max_j], 'value': round(float(arr[max_i, max_j]), 2)}
            extra['min_cell'] = {'row': rows[min_i], 'col': cols[min_j], 'value': round(float(arr[min_i, min_j]), 2)}
            flat = [(i, j, arr[i, j]) for i in range(arr.shape[0]) for j in range(arr.shape[1]) if np.isfinite(arr[i, j])]
            top = sorted(flat, key=lambda x: -x[2])[:5]
            extra['top_cells'] = [{'row': rows[i], 'col': cols[j], 'value': round(float(v), 2)} for i, j, v in top]
    return {'family': 'F', 'x_col': x_axis, 'extra': extra}


# ---- G 家族：表格 ----

def stats_spreadsheet(df: pd.DataFrame) -> Dict[str, Any]:
    """表格（spreadsheet）统计：行列数 + 各数值列基础统计，供解读引用。"""
    numeric = {}
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            s = df[col].dropna()
            if s.empty:
                continue
            numeric[str(col)] = {
                'min': pt(s.min()), 'max': pt(s.max()),
                'mean': pt(s.mean()), 'sum': pt(s.sum()),
            }
    return {'family': 'G', 'x_col': None, 'extra': {
        'rows': int(len(df)),
        'cols': [str(c) for c in df.columns],
        'numeric': numeric,
    }}
