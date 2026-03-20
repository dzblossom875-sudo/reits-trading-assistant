"""
工具函数模块
"""
import os
import re
import glob
from datetime import datetime
import pandas as pd
import numpy as np


def get_latest_daily_report(data_raw_dir: str, pattern: str = "日报表_*.xlsx") -> str:
    """
    从data/raw目录获取日期最新的日报表文件
    文件名格式：日报表_中诚信托-明珠76号集合资金信托计划_YYYYMMDD.xlsx
    """
    search_path = os.path.join(data_raw_dir, pattern)
    files = glob.glob(search_path)
    if not files:
        return None
    # 按文件名中的日期排序（提取最后的8位数字）
    def extract_date(filepath):
        basename = os.path.basename(filepath)
        # 查找最后的8位数字（YYYYMMDD格式）
        matches = re.findall(r'(\d{8})', basename)
        if matches:
            return matches[-1]
        return "00000000"
    sorted_files = sorted(files, key=extract_date, reverse=True)
    return sorted_files[0] if sorted_files else None


def check_and_convert_file(filepath: str, target_ext: str = ".xlsx") -> str:
    """
    检查文件格式，如果格式不正确尝试转换
    返回最终可用的文件路径
    """
    if not os.path.exists(filepath):
        return None
    ext = os.path.splitext(filepath)[1].lower()
    target_ext = target_ext.lower()
    if ext == target_ext:
        return filepath
    # 尝试用pandas转换
    try:
        import pandas as pd
        if ext == ".xls":
            # 尝试用xlrd读取
            try:
                import xlrd
                book = xlrd.open_workbook(filepath)
                df_dict = {}
                for sheet_name in book.sheet_names():
                    sheet = book.sheet_by_name(sheet_name)
                    data = [sheet.row_values(i) for i in range(sheet.nrows)]
                    df_dict[sheet_name] = pd.DataFrame(data[1:], columns=data[0] if data else None)
                # 保存为xlsx
                new_path = filepath.replace(".xls", ".xlsx")
                with pd.ExcelWriter(new_path, engine='openpyxl') as writer:
                    for sheet_name, df in df_dict.items():
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                return new_path
            except Exception as e:
                print(f"警告：无法转换 {filepath}: {e}")
                return None
        elif ext == ".csv":
            # 读取CSV并转换为xlsx
            df = pd.read_csv(filepath, encoding="utf-8")
            new_path = filepath.replace(".csv", ".xlsx")
            df.to_excel(new_path, index=False, engine='openpyxl')
            return new_path
    except Exception as e:
        print(f"警告：文件格式转换失败 {filepath}: {e}")
        return None
    return filepath


def clean_number(val):
    """清洗数字格式：去除="..."包裹，替换全角逗号等"""
    if pd.isna(val):
        return np.nan
    s = re.sub(r'^="?|"?$', "", str(val).strip())
    s = s.replace("，", "").replace(",", "").strip()
    s = s.replace("%", "").strip()  # 去除百分号
    try:
        return float(re.sub(r"\s+", "", s))
    except:
        return np.nan


def clean_code(code):
    """清洗证券代码：去除.SH/.SZ，提取数字，补零到6位"""
    s = str(code).strip().split(".")[0]
    s = re.sub(r"[^0-9]", "", s)
    return s.zfill(6) if s else None


def parse_date(val, formats=None):
    """解析日期字符串"""
    default_formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y%m%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ]
    formats = formats or default_formats
    if pd.isna(val) or str(val).strip() in ("--", "", "nan"):
        return pd.NaT
    if isinstance(val, pd.Timestamp):
        return val
    s = str(val).strip()
    for fmt in formats:
        try:
            return pd.to_datetime(s, format=fmt)
        except:
            pass
    try:
        return pd.to_datetime(s)
    except:
        return pd.NaT


def normalize_series(series: pd.Series, base_date, method="first"):
    """
    对时间序列进行归一化处理
    method: "first" - 以base_date当天值为基准
            "last" - 以2025年最后一个交易日为基准
    """
    if series.empty:
        return series
    if isinstance(base_date, str):
        base_date = pd.to_datetime(base_date)
    # 找到基准日或之前最近的值
    valid_data = series.dropna()
    if valid_data.empty:
        return series
    if method == "first":
        # 找小于等于base_date的最新值
        base_values = valid_data[valid_data.index <= base_date]
        if base_values.empty:
            base_val = valid_data.iloc[0]
        else:
            base_val = base_values.iloc[-1]
    else:
        base_val = valid_data.iloc[0]
    if pd.isna(base_val) or base_val == 0:
        return series
    return series / base_val
