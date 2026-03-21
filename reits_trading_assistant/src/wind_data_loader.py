"""
Wind API 数据获取模块
优先从Wind获取行情数据，失败时回退到本地Excel
"""
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Wind API 连接句柄
_wind_api = None


def get_wind_api():
    """获取Wind API连接，缓存连接句柄"""
    global _wind_api
    if _wind_api is not None:
        return _wind_api
    try:
        from WindPy import w
        w.start()
        if w.isconnected():
            _wind_api = w
            print("Wind API 连接成功")
            return w
        else:
            print("Wind API 连接失败")
            return None
    except ImportError:
        print("未安装WindPy，跳过Wind API")
        return None
    except Exception as e:
        print(f"Wind API 连接错误: {e}")
        return None


def get_reits_price_from_wind(codes: list, start_date: str, end_date: str = None) -> pd.DataFrame:
    """
    从Wind获取REITs个股行情数据
    返回DataFrame: index=date, columns=codes, values=close
    """
    w = get_wind_api()
    if w is None:
        return None
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    # 转换代码格式
    wind_codes = []
    for code in codes:
        code = str(code).zfill(6)
        # 判断交易所
        if code.startswith("5") or code.startswith("6"):
            wind_codes.append(f"{code}.SH")
        else:
            wind_codes.append(f"{code}.SZ")
    codes_str = ",".join(wind_codes)
    try:
        print(f"从Wind获取 {len(wind_codes)} 只个股行情 {start_date} ~ {end_date}")
        result = w.wsd(codes_str, "close", start_date, end_date, "PriceAdj=B")
        if result.ErrorCode != 0:
            print(f"Wind API 错误: {result.ErrorCode}")
            return None
        # 解析结果
        dates = result.Times
        data = result.Data
        cols = [c.replace(".SH", "").replace(".SZ", "") for c in result.Codes]
        df = pd.DataFrame(dict(zip(cols, data)), index=dates)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        print(f"获取Wind行情失败: {e}")
        return None


def get_index_data_from_wind(index_code: str, start_date: str, end_date: str = None) -> pd.DataFrame:
    """
    从Wind获取指数数据
    index_code: 如 "932006.CSI" 或 "H11017.CSI"
    返回DataFrame: index=date, columns=['close']
    """
    w = get_wind_api()
    if w is None:
        return None
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    try:
        print(f"从Wind获取指数 {index_code} 数据 {start_date} ~ {end_date}")
        result = w.wsd(index_code, "close", start_date, end_date, "PriceAdj=B")
        if result.ErrorCode != 0:
            print(f"Wind API 错误: {result.ErrorCode}")
            return None
        dates = result.Times
        data = result.Data[0] if result.Data else []
        df = pd.DataFrame({"close": data}, index=dates)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        print(f"获取Wind指数数据失败: {e}")
        return None


def get_sector_index_from_wind(sector_mapping: dict, start_date: str, end_date: str = None) -> pd.DataFrame:
    """
    获取板块指数数据
    sector_mapping: {板块名: 指数代码}
    返回DataFrame: index=date, columns=板块名
    """
    w = get_wind_api()
    if w is None:
        return None
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    result_dict = {}
    for sector, code in sector_mapping.items():
        try:
            result = w.wsd(code, "close", start_date, end_date, "PriceAdj=B")
            if result.ErrorCode == 0 and result.Data:
                dates = result.Times
                data = result.Data[0]
                df = pd.DataFrame({sector: data}, index=dates)
                df.index = pd.to_datetime(df.index)
                result_dict[sector] = df[sector]
        except Exception as e:
            print(f"获取板块 {sector} 数据失败: {e}")
    if not result_dict:
        return None
    return pd.DataFrame(result_dict)


def load_index_data_with_fallback() -> pd.DataFrame:
    """
    加载指数数据，优先从Wind获取，失败时回退到本地Excel
    """
    # 尝试从Wind获取
    if config.USE_WIND_API:
        # 获取932006收盘价指数
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = "2024-01-01"  # 足够早的日期
        df = get_index_data_from_wind("932006.CSI", start_date, end_date)
        if df is not None and not df.empty:
            df.columns = ["reits_index"]
            # 尝试获取10Y国债、沪深300等
            try:
                tb_df = get_index_data_from_wind("H11017.CSI", start_date, end_date)
                if tb_df is not None:
                    df["tb10y"] = tb_df["close"]
            except:
                pass
            try:
                hs300_df = get_index_data_from_wind("000300.SH", start_date, end_date)
                if hs300_df is not None:
                    df["hs300"] = hs300_df["close"]
            except:
                pass
            return df.sort_index()
    # 回退到本地Excel
    print("使用本地指数文件...")
    from src.data_loader import load_index
    return load_index()


def _load_local_prices(codes: list) -> pd.DataFrame:
    """从本地行情文件读取个股收盘价"""
    filepath = os.path.join(config.DATA_RAW_DIR, config.FILE_LOCAL_PRICES)
    if not os.path.exists(filepath):
        return None
    df_raw = pd.read_excel(filepath, sheet_name="Sheet1", header=None)
    # row 4 = 代码行（含 .SH/.SZ），row 5+ = 数据
    code_row = df_raw.iloc[4].astype(str).str.strip()
    clean_cols = code_row.str.replace(r"\.(SH|SZ)$", "", regex=True)
    df_data = df_raw.iloc[5:].copy().reset_index(drop=True)
    df_data.columns = clean_cols
    df_data = df_data.rename(columns={clean_cols.iloc[0]: "date"})
    df_data["date"] = pd.to_datetime(df_data["date"], errors="coerce")
    df_data = df_data[df_data["date"].notna()].set_index("date")
    for col in df_data.columns:
        df_data[col] = pd.to_numeric(df_data[col], errors="coerce")
    # 只保留请求的代码
    available = [c for c in codes if c in df_data.columns]
    missing = [c for c in codes if c not in df_data.columns]
    if missing:
        print(f"  本地文件缺少以下代码：{missing}")
    return df_data[available].sort_index() if available else None


_PRICES_CACHE_PATH = os.path.join(config.DATA_PROCESSED_DIR, "wind_prices_cache.csv")


def _load_prices_cache() -> pd.DataFrame:
    """读取本地行情缓存，返回 DataFrame(index=date, columns=codes)，无缓存则返回 None"""
    if not os.path.exists(_PRICES_CACHE_PATH):
        return None
    try:
        df = pd.read_csv(_PRICES_CACHE_PATH, index_col=0, parse_dates=True, encoding="utf-8-sig")
        df.index = pd.to_datetime(df.index)
        return df.sort_index()
    except Exception as e:
        print(f"  读取行情缓存失败: {e}")
        return None


def _save_prices_cache(df: pd.DataFrame):
    """保存行情数据到本地缓存"""
    try:
        df.sort_index().to_csv(_PRICES_CACHE_PATH, encoding="utf-8-sig")
    except Exception as e:
        print(f"  保存行情缓存失败: {e}")


def load_reits_prices_with_fallback(codes: list) -> pd.DataFrame:
    """
    加载REITs个股价格，优先从Wind获取，数据异常时回退本地文件。
    增量缓存：已拉取的历史数据保存在 wind_prices_cache.csv，
    下次运行只拉取缓存最新日期之后的新增数据，减少API消耗。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    cache = _load_prices_cache()

    if config.USE_WIND_API:
        # 确定需要拉取的起始日期
        if cache is not None and not cache.empty:
            cached_max = cache.index.max()
            fetch_start = (cached_max + timedelta(days=1)).strftime("%Y-%m-%d")
            if fetch_start > today:
                print(f"  行情缓存已是最新（{cached_max.date()}），跳过Wind请求")
                return cache
            print(f"  行情缓存最新至 {cached_max.date()}，增量拉取 {fetch_start} ~ {today}")
        else:
            fetch_start = "2024-01-01"
            print(f"  无行情缓存，全量拉取 {fetch_start} ~ {today}")

        new_df = get_reits_price_from_wind(codes, fetch_start, today)

        if new_df is not None and not new_df.empty:
            nan_rate = new_df.isna().values.mean()
            if nan_rate >= 0.5:
                print(f"  Wind增量数据异常（NaN率={nan_rate:.0%}），回退本地文件")
            else:
                # 合并缓存与新数据
                if cache is not None and not cache.empty:
                    # 新代码补全历史列（填NaN），旧代码追加新行
                    combined = pd.concat([cache, new_df])
                    # 去重（保留最新值）
                    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
                else:
                    combined = new_df.sort_index()

                _save_prices_cache(combined)
                print(f"  行情缓存已更新：共 {len(combined)} 天 × {len(combined.columns)} 只")
                return combined
        else:
            print("  Wind增量拉取失败，使用现有缓存")
            if cache is not None:
                return cache

    # 最终回退：本地缓存 → 本地Excel文件
    if cache is not None and not cache.empty:
        print("  使用现有行情缓存（Wind未启用或获取失败）")
        return cache
    print("  读取本地行情文件...")
    return _load_local_prices(codes)
