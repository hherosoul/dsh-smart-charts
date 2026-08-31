"""数据解析器。将 CSV、TSV、Excel、JSON、TXT 等文件解析为 DataFrame。

P0/P2/P3 重构要点：
- CSV/TSV 合并为单一分隔符解析器（同一编码回退、同一错误结构）
- 编码回退列表收敛为模块级常量 ENCODING_FALLBACKS，所有格式共用
- 横向合并的 _dup 后缀处理修复：只回收 pandas 追加的后缀列，并用
  combine_first 保留第二份数据中的非空值（不再丢数据、不再误伤真实
  以 _dup 结尾的列名）
- ID 类列保护：列名命中 id/编号/学号/工号/邮编/电话 等，或值含前导零
  （如 007）时，跳过"字符串转数值"，避免标识符信息被破坏
- Excel sheet 语义：显式指定的 sheet 不存在 → 结构化错误（附可用列表）；
  默认第 0 个 sheet 为空 → 自动回退到第一个非空 sheet
- __main__ 入口统一走 argparse（含未知 flag 在内，参数错误一律结构化 JSON）
"""

import sys
import json
import re
import pandas as pd
import numpy as np
from functools import partial
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

if __name__ == '__main__' and __package__ is None:
    import _bootstrap  # noqa: F401 — 单点 sys.path 引导，见 _bootstrap.py
    from scripts.exceptions import FileError, DataError, SmartChartsError, ErrorCode, JSONArgumentParser
else:
    from .exceptions import FileError, DataError, SmartChartsError, ErrorCode, JSONArgumentParser


# 所有文本格式共用的编码回退列表（按命中率排序，latin1 兜底从不抛 UnicodeDecodeError）
ENCODING_FALLBACKS: Tuple[str, ...] = ('utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'utf-16', 'latin1')

# ID 类列名提示词（命中则跳过数值转换，保护 007/000123 之类的前导零标识符）
_ID_NAME_RE = re.compile(r'(id$|^id|编号|学号|工号|考号|邮编|code|phone|电话|手机|证件)', re.IGNORECASE)

# 前导零数值字符串（如 007、000123）：转数值会丢失信息，视为标识符
_LEADING_ZERO_RE = re.compile(r'^0\d+$')


class DataParser:

    MAX_FILE_SIZE_MB = 100  # 单文件最大允许大小（MB）

    def __init__(self):
        self._parsers = {
            '.csv': partial(DataParser._parse_delimited, sep=','),
            '.tsv': partial(DataParser._parse_delimited, sep='\t'),
            '.xlsx': DataParser._parse_excel,
            '.xls': DataParser._parse_excel,
            '.json': DataParser._parse_json,
            '.txt': DataParser._parse_text,
        }

    def parse_file(
        self,
        file_path: str,
        skiprows: Optional[int] = None,
        header_row: Optional[int] = None,
        sheet_name: Union[int, str] = 0,
        **kwargs,
    ) -> pd.DataFrame:
        """解析单个文件。

        多行表头/前导冗余行处理（参数互斥，按需传一个即可）：
        - skiprows: 跳过前 N 行后再读取（pandas read_csv/read_excel 的 skiprows 语义）
        - header_row: 指定第 N 行作为列名（0-based），其上方行被丢弃，下方作为数据
        - sheet_name: Excel 工作表索引或名称（默认第 0 个；第 0 个为空时自动回退到
          第一个非空 sheet；显式指定的 sheet 不存在时报错并列出可用 sheet）
        参数值由调用方根据实际数据决定，本技能不预设任何固定行数。
        """
        path = Path(file_path)
        if not path.exists():
            raise FileError(
                f"文件不存在: {file_path}",
                ErrorCode.FILE_NOT_FOUND,
                details={'path': file_path, 'suggestion': '检查路径是否正确，或使用绝对路径'},
            )
        if not path.is_file():
            raise FileError(
                f"不是文件: {file_path}",
                ErrorCode.FILE_NOT_REGULAR,
                details={'path': file_path, 'suggestion': '路径指向的不是常规文件（可能是目录）'},
            )
        size_mb = path.stat().st_size / 1024 / 1024
        if size_mb > self.MAX_FILE_SIZE_MB:
            raise FileError(
                f"文件超过{self.MAX_FILE_SIZE_MB}MB限制",
                ErrorCode.FILE_SIZE_EXCEEDED,
                details={
                    'path': file_path,
                    'size_mb': round(size_mb, 2),
                    'limit_mb': self.MAX_FILE_SIZE_MB,
                    'suggestion': f'拆分文件或筛选行/列后重试，单文件上限 {self.MAX_FILE_SIZE_MB}MB',
                },
            )

        ext = path.suffix.lower()
        if ext not in self._parsers:
            # 有明确但不受支持的扩展名直接走下方 1003 报错，不做内容嗅探；
            # 仅无扩展名文件才按内容识别真实格式
            if not ext:
                ext = self._detect_type(path)
        if ext not in self._parsers:
            supported = list(self._parsers.keys())
            raise FileError(
                f"不支持的格式: {ext}，支持: {supported}",
                ErrorCode.FILE_FORMAT_INVALID,
                details={
                    'path': file_path,
                    'given_ext': ext,
                    'supported': supported,
                    'suggestion': '将文件转为支持的格式（CSV/Excel/JSON）后重试',
                },
            )

        # 统一把表头清洗参数塞进 kwargs，每个 _parse_* 按需读取
        if skiprows is not None:
            kwargs['skiprows'] = skiprows
        if header_row is not None:
            kwargs['header_row'] = header_row
        # 显式传 None 视同未指定：回退到第 0 个 sheet（None 会让 read_excel 返回 dict）
        kwargs.setdefault('sheet_name', 0 if sheet_name is None else sheet_name)

        df = self._parsers[ext](self, path, **kwargs)
        if df.empty:
            raise DataError(
                "文件内容为空",
                ErrorCode.DATA_EMPTY,
                details={'path': file_path, 'suggestion': '检查文件是否只有表头无数据行，或用 --sheet 指定其他工作表'},
            )

        df = self._clean(df)
        self._validate(df)
        return df

    def parse_files(self, file_paths: List[str], merge: bool = False) -> Dict[str, Any]:
        """解析多个文件，返回统一结构 {'merged': bool, 'data': ..., 'merge_type': Optional[str]}。

        - merge=False: data 为 List[Dict[str, pd.DataFrame]]，每项含 {'file', 'data'}
        - merge=True:  data 为合并后的 pd.DataFrame，merge_type 描述合并方式
        """
        results = []
        for fp in file_paths:
            df = self.parse_file(fp)
            results.append({'file': Path(fp).name, 'data': df})

        if not merge:
            return {'merged': False, 'data': results, 'merge_type': None}

        merged_df, merge_type = self._merge(results)
        return {'merged': True, 'data': merged_df, 'merge_type': merge_type}

    def get_data_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            'shape': list(df.shape),
            'columns': list(df.columns),
            'dtypes': {col: str(dtype) for col, dtype in df.dtypes.items()},
            'missing': {k: int(v) for k, v in df.isnull().sum().to_dict().items()},
            'sample': df.head(5).to_dict('records'),
        }
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 0:
            summary['stats'] = df[numeric_cols].describe().to_dict()
        return summary

    def _merge(self, results: List[Dict]) -> Tuple[pd.DataFrame, str]:
        """尝试合并多个 DataFrame。返回 (merged_df, merge_type)。"""
        dfs = [r['data'] for r in results]
        col_sets = [set(df.columns) for df in dfs]

        # 纵向拼接：所有文件列名完全相同
        if all(len(cs) > 0 for cs in col_sets) and all(cs == col_sets[0] for cs in col_sets):
            merged = pd.concat(dfs, ignore_index=True)
            merged['source_file'] = [r['file'] for r in results for _ in range(len(r['data']))]
            cols = list(merged.columns)
            cols.remove('source_file')
            merged = merged[cols + ['source_file']]
            return merged, '纵向拼接'

        # 横向关联：公共列占比 >= 50%
        if len(dfs) >= 2 and all(len(cs) > 0 for cs in col_sets):
            intersection = col_sets[0]
            for cs in col_sets[1:]:
                intersection = intersection & cs
            avg_col_count = sum(len(cs) for cs in col_sets) / len(col_sets)
            if len(intersection) >= avg_col_count * 0.5:
                # 记录原始列名集合：只有 pandas 追加的 _dup 后缀列才允许回收，
                # 真实以 _dup 结尾的列名保持原样（修复旧实现 replace('_dup','') 的误伤）
                original_cols = set()
                for df in dfs:
                    original_cols.update(str(c) for c in df.columns)
                merged = dfs[0]
                for df in dfs[1:]:
                    merged = pd.merge(merged, df, on=list(intersection), how='outer', suffixes=('', '_dup'))
                merged = self._collapse_merge_suffixes(merged, original_cols)
                return merged, '横向关联'

        # 无法自动合并
        summary_parts = []
        for r in results:
            summary_parts.append(f"{r['file']}: {r['data'].shape[0]}行 {r['data'].shape[1]}列, 列={list(r['data'].columns)}")
        raise DataError(
            f"文件结构差异大，无法自动合并。各文件信息：\n" + "\n".join(summary_parts) +
            "\n请指定关联方式，或分别分析。",
            ErrorCode.DATA_MERGE_ERROR,
            details={
                'files': [{'file': r['file'], 'shape': list(r['data'].shape), 'columns': list(r['data'].columns)} for r in results],
                'suggestion': '请指定关联方式（如 merge_files 时提供 on 列），或对每个文件分别分析',
            },
        )

    @staticmethod
    def _collapse_merge_suffixes(merged: pd.DataFrame, original_cols: set) -> pd.DataFrame:
        """回收 pandas 横向合并追加的 _dup 后缀列。

        语义：base（第一份数据）与 base_dup（第二份数据）是同一业务列的两份来源，
        用 combine_first 保留两份中的非空值后再去掉 _dup 列；真实名为 xxx_dup 的
        原始列不在回收范围内，原样保留。

        回收后若仍存在重名列（如第一份数据本身有 v 与 v_dup 两列、第二份数据又
        含 v 列，pandas 加后缀后与真实 v_dup 撞名），显式报 DATA_MERGE_ERROR，
        不再静默丢弃任一列——静默丢列等于丢数据。
        """
        dup_cols = [
            c for c in merged.columns
            if c.endswith('_dup') and c not in original_cols and c[:-4] in merged.columns
        ]
        for dc in dup_cols:
            base = dc[:-4]
            merged[base] = merged[base].combine_first(merged[dc])
        merged = merged.drop(columns=dup_cols)
        duplicated = merged.columns[merged.columns.duplicated()].tolist()
        if duplicated:
            raise DataError(
                f"横向合并后出现重名列，无法自动处理: {duplicated}",
                ErrorCode.DATA_MERGE_ERROR,
                details={
                    'duplicated_columns': duplicated,
                    'suggestion': '先重命名撞名列（如 xxx_dup）后再合并，或显式指定关联列',
                },
            )
        return merged

    # ---- 解析实现 ----

    def _parse_delimited(self, path: Path, sep: str, **kw) -> pd.DataFrame:
        """解析 CSV/TSV 等单字符分隔文本（同一套编码回退与错误结构）。"""
        label = 'CSV' if sep == ',' else 'TSV'
        read_kwargs = self._build_header_kwargs(kw)
        for _enc in ENCODING_FALLBACKS:
            try:
                return pd.read_csv(path, sep=sep, encoding=_enc, dtype=str, **read_kwargs)
            except pd.errors.EmptyDataError:
                raise DataError(
                    "文件内容为空",
                    ErrorCode.DATA_EMPTY,
                    details={'path': str(path), 'suggestion': '检查文件是否只有表头无数据行'},
                )
            except pd.errors.ParserError as e:
                raise DataError(
                    f"{label} 解析失败: {e}",
                    ErrorCode.DATA_PARSE_ERROR,
                    details={
                        'path': str(path),
                        'error': str(e),
                        'suggestion': '文件可能含前导说明行或列数不一致，先不加参数运行查看原始布局，再用 --skiprows N 或 --header-row N 跳过冗余行',
                    },
                )
            except UnicodeDecodeError:
                continue
        raise DataError(
            "无法解码文件",
            ErrorCode.DATA_PARSE_ERROR,
            details={'path': str(path), 'tried_encodings': list(ENCODING_FALLBACKS),
                     'suggestion': '用文本编辑器另存为 UTF-8 后重试'},
        )

    def _parse_excel(self, path: Path, **kw) -> pd.DataFrame:
        sheet = kw.get('sheet_name', 0)
        # 根据扩展名选择引擎：.xlsx 用 openpyxl，.xls 用 xlrd
        ext = path.suffix.lower()
        engine = 'xlrd' if ext == '.xls' else 'openpyxl'
        read_kwargs = self._build_header_kwargs(kw)
        try:
            xl = pd.ExcelFile(path, engine=engine)
        except Exception as e:
            raise DataError(
                f"Excel读取失败: {e}",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'engine': engine, 'error': str(e),
                         'suggestion': '检查文件是否损坏、是否为真正的 Excel 文件（非改扩展名的 CSV）'},
            )
        sheets = list(xl.sheet_names)
        # 显式指定的 sheet 不存在 → 报错并列出可用 sheet（不再静默回退）
        if isinstance(sheet, str) and sheet not in sheets:
            raise DataError(
                f"工作表不存在: {sheet}",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'given_sheet': sheet, 'available_sheets': sheets,
                         'suggestion': f'从 available_sheets 中选择，或用 --sheet <索引> 指定（共 {len(sheets)} 个）'},
            )
        if isinstance(sheet, int) and not (-len(sheets) <= sheet < len(sheets)):
            raise DataError(
                f"工作表索引越界: {sheet}",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'given_index': sheet, 'available_sheets': sheets,
                         'suggestion': f'索引范围 0~{len(sheets) - 1}，或直接用 --sheet <名称>'},
            )
        try:
            df = pd.read_excel(path, sheet_name=sheet, engine=engine, **read_kwargs)
            # 仅默认第 0 个 sheet 为空时自动回退到第一个非空 sheet；
            # 用户显式指定的 sheet 为空则原样返回（由 parse_file 统一报 DATA_EMPTY）
            if df.empty and sheet == 0:
                for s in sheets[1:]:
                    df2 = pd.read_excel(path, sheet_name=s, engine=engine, **read_kwargs)
                    if not df2.empty:
                        return df2
            return df
        except DataError:
            raise
        except Exception as e:
            raise DataError(
                f"Excel读取失败: {e}",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'engine': engine, 'error': str(e),
                         'available_sheets': sheets,
                         'suggestion': '检查文件是否损坏、是否为真正的 Excel 文件（非改扩展名的 CSV）'},
            )

    @staticmethod
    def _build_header_kwargs(kw: Dict[str, Any]) -> Dict[str, Any]:
        """从调用 kwargs 中提取表头清洗参数，转为 pandas read_csv/read_excel 接受的形式。

        - skiprows: 整数 N，跳过前 N 行
        - header_row: 整数 N（0-based），将第 N 行作为列名，丢弃其上方行
        两者互斥；同时给出时以 header_row 优先（更精确）。
        """
        out: Dict[str, Any] = {}
        skiprows = kw.get('skiprows')
        header_row = kw.get('header_row')
        if header_row is not None:
            # header=N 等价于：第 N 行作为列名，前面行被 pandas 自动跳过
            out['header'] = int(header_row)
        elif skiprows is not None:
            out['skiprows'] = int(skiprows)
        return out

    def _parse_json(self, path: Path, **kw) -> pd.DataFrame:
        """解析 JSON 文件，支持多编码回退。"""
        data = None
        last_error = None
        for enc in ENCODING_FALLBACKS:
            try:
                with open(path, 'r', encoding=enc) as f:
                    data = json.load(f)
                break
            except UnicodeDecodeError:
                continue
            except json.JSONDecodeError as e:
                last_error = e
                continue
        if data is None:
            if last_error:
                raise DataError(
                    f"JSON 解析失败: {last_error}",
                    ErrorCode.DATA_PARSE_ERROR,
                    details={'path': str(path), 'error': str(last_error), 'suggestion': '用 JSON 校验工具检查格式（如 jsonlint.com）'},
                )
            raise DataError(
                "无法解码 JSON 文件",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'tried_encodings': list(ENCODING_FALLBACKS), 'suggestion': '用文本编辑器另存为 UTF-8 后重试'},
            )

        # 提取待转表的记录集，并检测字段值是否含 dict/list（即嵌套超过 1 层）
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            list_value = next((v for v in data.values() if isinstance(v, list)), None)
            records = list_value if list_value is not None else [data]
        else:
            raise DataError(
                "不支持的JSON结构",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'top_level_type': type(data).__name__,
                         'suggestion': 'JSON 顶层必须是数组、或含数组值的对象'},
            )

        # 校验嵌套深度：允许 1 层嵌套对象（展开为 "父.子" 点分列，与文档声明一致），
        # 深度 ≥2 的 dict 与任何 list 值仍不支持
        for r in records:
            if not isinstance(r, dict):
                continue
            for k, v in r.items():
                if isinstance(v, list):
                    raise DataError(
                        f"JSON 字段 '{k}' 的值为数组，暂不支持",
                        ErrorCode.DATA_PARSE_ERROR,
                        details={'path': str(path), 'field': k,
                                 'suggestion': '请将数组字段转为标量（如取首元素、求和），或用工具先转为 CSV 再生成图表'},
                    )
                if isinstance(v, dict):
                    if any(isinstance(x, (dict, list)) for x in v.values()):
                        raise DataError(
                            "JSON 嵌套超过 1 层，暂不支持",
                            ErrorCode.DATA_PARSE_ERROR,
                            details={'path': str(path), 'field': k,
                                     'suggestion': '每条记录最多嵌套 1 层对象（展开为 "父.子" 列），更深的结构请先展平或转为 CSV'},
                        )
                    # 展开名 "父.子" 与记录内已有键撞名时，json_normalize 会静默用
                    # 嵌套值覆盖原始标量值（丢数据）——这里前置拦截，显式报错
                    clash = [f'{k}.{sk}' for sk in v if f'{k}.{sk}' in r]
                    if clash:
                        raise DataError(
                            f"JSON 嵌套字段展开后与已有列重名: {clash}",
                            ErrorCode.DATA_PARSE_ERROR,
                            details={'path': str(path), 'duplicated_columns': clash,
                                     'suggestion': '展开产生的 "父.子" 列名与现有字段撞名，请重命名字段后再试'},
                        )

        # 含 1 层嵌套对象 → json_normalize 展平为点分列；扁平数据维持原有路径（行为不变）
        has_nested = any(
            isinstance(v, dict)
            for r in records if isinstance(r, dict) for v in r.values()
        )
        if has_nested:
            if not all(isinstance(r, dict) for r in records):
                raise DataError(
                    "JSON 记录结构不一致（对象与标量混排），暂不支持",
                    ErrorCode.DATA_PARSE_ERROR,
                    details={'path': str(path),
                             'suggestion': '数组元素须全部为对象，请清理数据或先转为 CSV'},
                )
            df = pd.json_normalize(records, max_level=1)
            dup = df.columns[df.columns.duplicated()].tolist()
            if dup:
                raise DataError(
                    f"JSON 嵌套字段展开后与已有列重名: {dup}",
                    ErrorCode.DATA_PARSE_ERROR,
                    details={'path': str(path), 'duplicated_columns': dup,
                             'suggestion': '展开产生的 "父.子" 列名与现有字段撞名，请重命名字段后再试'},
                )
            return df
        if isinstance(data, list):
            return pd.DataFrame(data)
        if list_value is not None:
            return pd.DataFrame(list_value)
        return pd.json_normalize(data)

    def _parse_text(self, path: Path, **kw) -> pd.DataFrame:
        """解析文本文件，支持多编码回退与分隔符探测。"""
        lines = None
        detected_enc = ENCODING_FALLBACKS[0]
        for enc in ENCODING_FALLBACKS:
            try:
                with open(path, 'r', encoding=enc) as f:
                    lines = [l.strip() for l in f if l.strip()]
                detected_enc = enc
                break
            except UnicodeDecodeError:
                continue
        if not lines:
            raise DataError(
                "文件为空",
                ErrorCode.DATA_EMPTY,
                details={'path': str(path), 'suggestion': '检查文件是否有内容'},
            )
        read_kwargs = self._build_header_kwargs(kw)
        for delim in (',', '\t', ';', '|'):
            if delim in lines[0] and len(lines[0].split(delim)) > 1:
                return pd.read_csv(path, sep=delim, encoding=detected_enc, dtype=str, **read_kwargs)
        return pd.DataFrame({'content': lines})

    def _detect_type(self, path: Path) -> str:
        try:
            header = path.read_bytes()[:1024]
            text = header.decode('utf-8', errors='ignore')
            if text.strip().startswith(('{', '[')):
                return '.json'
            if header.startswith(b'\x50\x4B\x03\x04'):
                return '.xlsx'
            for delim in (',', '\t', ';'):
                if delim in text:
                    return '.csv'
        except Exception:
            pass
        return path.suffix.lower()

    def _clean(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.dropna(axis=1, how='all').dropna(axis=0, how='all').reset_index(drop=True)
        df.columns = [self._normalize_col(c) for c in df.columns]
        for col in df.columns:
            if df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col]):
                # ID 类列保护：标识符列（学号 007 之类）保持字符串，
                # 前导零一旦转数值就永久丢失
                if not self._is_id_like(col, df[col]):
                    df[col] = self._to_numeric_if_possible(df[col])
        return df

    @staticmethod
    def _is_id_like(col: str, series: pd.Series) -> bool:
        """判断列是否为标识符列：列名命中提示词，或存在前导零值。"""
        if _ID_NAME_RE.search(str(col)):
            return True
        try:
            s = series.dropna().astype(str).str.strip()
            return bool(s.str.match(_LEADING_ZERO_RE).any())
        except Exception:
            return False

    @staticmethod
    def _to_numeric_if_possible(series: pd.Series) -> pd.Series:
        """尝试将字符串列转换为数值列。

        先清理常见数值格式（货币符号/千分位逗号/百分号），
        再尝试整体转换（等价于已弃用的 errors='ignore' 语义：全列可转才转），
        百分号整体转为小数。避免使用 errors='ignore'，消除 FutureWarning。
        """
        # 先把缺失值归一为空串再转 str：否则 NaN 经 astype(str) 变成字符串 'nan'，
        # 导致 to_numeric 整列失败、列静默回退 object（下游聚合退化为字符串拼接）
        s = series.fillna('').astype(str).str.strip()
        if s.eq('').all():
            return series
        cleaned = s.str.replace(r'[¥$€£￥]', '', regex=True).str.replace(',', '', regex=False)
        cleaned = cleaned.mask(cleaned == '')  # 空串视为缺失（dtype=str 读入后不再由 pandas 代劳）
        has_pct = cleaned.str.endswith('%')
        cleaned = cleaned.str.rstrip('%')
        try:
            converted = pd.to_numeric(cleaned, errors='raise')
        except (ValueError, TypeError):
            return series
        if has_pct.any():
            converted = converted.where(~has_pct, converted / 100.0)
        return converted

    @staticmethod
    def _normalize_col(name: Any) -> str:
        if pd.isna(name):
            return 'unnamed'
        s = re.sub(r'[^\w\s]', '_', str(name).strip())
        s = re.sub(r'[\s_]+', '_', s).strip('_').lower()
        return s or 'unnamed'

    @staticmethod
    def _validate(df: pd.DataFrame):
        if df.empty:
            raise DataError(
                "数据为空",
                ErrorCode.DATA_EMPTY,
                details={'suggestion': '清洗后数据为空，检查原始数据是否全为空行/空列'},
            )


def _build_arg_parser() -> JSONArgumentParser:
    p = JSONArgumentParser(
        prog='data_parser.py',
        description='Smart Charts 数据解析器：数据文件 → DataFrame（预览/JSON 摘要）',
    )
    p.add_argument('files', nargs='+', help='数据文件路径（单个或多个）')
    p.add_argument('--summary', action='store_true', help='输出 JSON 数据摘要（shape/列/类型/缺失/样本/统计）')
    p.add_argument('--merge', action='store_true', help='多文件自动合并（列相同纵向拼接，公共列>=50%横向关联）')
    p.add_argument('--skiprows', type=int, default=None, metavar='N', help='跳过前 N 行再读取（单文件模式）')
    p.add_argument('--header-row', dest='header_row', type=int, default=None, metavar='N',
                   help='第 N 行（0-based）作为列名，其上方行丢弃（单文件模式）')
    p.add_argument('--sheet', default=None, metavar='NAME|INDEX',
                   help='Excel 工作表名称或索引（单文件模式，默认第 0 个）')
    return p


def _run_cli() -> int:
    try:
        ns = _build_arg_parser().parse_args()
    except SmartChartsError as e:
        print(json.dumps(e.to_dict(), ensure_ascii=False), file=sys.stderr)
        return 1

    sheet_name = 0
    if ns.sheet is not None:
        v = ns.sheet
        sheet_name = int(v) if v.lstrip('-').isdigit() else v

    # 单文件清洗参数（仅对单文件模式生效；多文件场景请在 transform_code 阶段处理）
    single = len(ns.files) == 1 and not ns.merge
    parser = DataParser()
    try:
        if single:
            df = parser.parse_file(
                ns.files[0], skiprows=ns.skiprows, header_row=ns.header_row, sheet_name=sheet_name,
            )
            if ns.summary:
                print(json.dumps(parser.get_data_summary(df), ensure_ascii=False, indent=2, default=str))
            else:
                print(f"解析成功: {df.shape[0]} 行, {df.shape[1]} 列")
                print(f"列名: {list(df.columns)}")
                print(df.head(5).to_string())
        else:
            result = parser.parse_files(ns.files, merge=ns.merge)
            if result['merged']:
                merged_df, merge_type = result['data'], result['merge_type']
                if ns.summary:
                    # summary 模式 stdout 必须是纯 JSON（agent 机器可读），merge_type 放入 JSON 内
                    summary = parser.get_data_summary(merged_df)
                    summary['merge_type'] = merge_type
                    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
                else:
                    print(f"合并方式: {merge_type}")
                    print(f"合并后: {merged_df.shape[0]} 行, {merged_df.shape[1]} 列")
                    print(f"列名: {list(merged_df.columns)}")
                    print(merged_df.head(5).to_string())
            else:
                items = result['data']
                if ns.summary:
                    summaries = [{'file': it['file'], **parser.get_data_summary(it['data'])} for it in items]
                    print(json.dumps(summaries, ensure_ascii=False, indent=2, default=str))
                else:
                    for it in items:
                        df = it['data']
                        print(f"\n--- {it['file']}: {df.shape[0]} 行, {df.shape[1]} 列 ---")
                        print(f"列名: {list(df.columns)}")
                        print(df.head(3).to_string())
        return 0
    except SmartChartsError as e:
        print(json.dumps(e.to_dict(), ensure_ascii=False), file=sys.stderr)
        return 1
    except Exception as e:
        err = SmartChartsError(
            f"未知错误: {e}", ErrorCode.UNKNOWN_ERROR,
            details={'error': str(e), 'type': type(e).__name__},
        )
        print(json.dumps(err.to_dict(), ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(_run_cli())
