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


def load_reits_prices_with_fallback(codes: list) -> pd.DataFrame:
    """
    加载REITs个股价格，优先从Wind获取，失败时返回None（需要用户提供数据）
    """
    if config.USE_WIND_API:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = "2024-01-01"
        df = get_reits_price_from_wind(codes, start_date, end_date)
        if df is not None and not df.empty:
            return df
    print("无法从Wind获取个股行情，请提供板块行情数据文件")
    return None
