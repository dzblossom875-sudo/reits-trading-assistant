"""
数据加载与清洗模块
"""
import os, re, sys
import glob
import pandas as pd
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src.utils import clean_code, clean_number, parse_date, get_latest_daily_report, normalize_series


def load_reits_info():
    """加载REITs基础信息（代码、名称、板块）"""
    filepath = os.path.join(config.DATA_RAW_DIR, config.FILE_REITS_INFO)
    xl = pd.ExcelFile(filepath)
    df = pd.read_excel(filepath, sheet_name=xl.sheet_names[0])
    col_map = {}
    for col in df.columns:
        if "代码" in str(col): col_map["code"] = col
        elif "名称" in str(col) and "name" not in col_map: col_map["name"] = col
        elif "项目类型" in str(col) or "板块" in str(col): col_map["sector"] = col
    df = df.rename(columns={v:k for k,v in col_map.items()})
    keep = [c for c in ["code","name","sector"] if c in df.columns]
    df = df[keep].copy()
    df["code"] = df["code"].apply(clean_code)
    df = df[df["code"].notna() & (df["code"]!="000000")]
    if "sector" in df.columns:
        df["sector"] = df["sector"].apply(lambda x: config.SECTOR_SYNONYMS.get(str(x).strip(), str(x).strip()))
    return df.drop_duplicates(subset=["code"]).reset_index(drop=True)


def load_index():
    """加载指数数据（本地Excel）"""
    filepath = os.path.join(config.DATA_RAW_DIR, config.FILE_INDEX)
    df_raw = pd.read_excel(filepath, sheet_name="Sheet2", header=None)
    col_names = df_raw.iloc[3].tolist()
    df_data = df_raw.iloc[5:].copy().reset_index(drop=True)
    df_data.columns = range(len(df_data.columns))
    df_data = df_data.rename(columns={0:"date"})
    df_data["date"] = df_data["date"].apply(parse_date)
    df_data = df_data[df_data["date"].notna()].copy()
    rename_map = {}
    for i,name in enumerate(col_names):
        n = str(name).strip()
        if "REITs" in n and "全收" in n: rename_map[i] = "reits_index"
        elif "10Y" in n or "国债" in n: rename_map[i] = "tb10y"
        elif "沪深300" in n or ("300" in n and "红利" not in n): rename_map[i] = "hs300"
        elif "红利" in n: rename_map[i] = "csi_dividend"
    df_data = df_data.rename(columns=rename_map)
    keep = ["date"] + [c for c in ["reits_index","tb10y","hs300","csi_dividend"] if c in df_data.columns]
    df_data = df_data[keep]
    for col in keep[1:]: df_data[col] = pd.to_numeric(df_data[col], errors="coerce")
    return df_data.sort_values("date").set_index("date")


def load_nav_from_daily_report():
    """
    从日报表读取净值时间序列
    返回DataFrame: index=date, column=nav
    """
    daily_report_path = get_latest_daily_report(config.DATA_RAW_DIR, config.DAILY_REPORT_PATTERN)
    if daily_report_path is None:
        print("错误：未找到日报表文件")
        return None
    print(f"读取日报表: {os.path.basename(daily_report_path)}")
    df_raw = pd.read_excel(daily_report_path, sheet_name=config.SHEET_NAV, header=None)
    col_names = df_raw.iloc[3].tolist()
    df_data = df_raw.iloc[4:].copy().reset_index(drop=True)
    df_data.columns = col_names
    df_data = df_data.rename(columns={col_names[0]:"date"})
    df_data["date"] = df_data["date"].apply(parse_date)
    df_data = df_data[df_data["date"].notna()]
    nav_col = next((c for c in df_data.columns if "累计" in str(c) and "净值" in str(c)), None)
    if nav_col is None:
        nav_col = next((c for c in df_data.columns if "净值" in str(c)), None)
    df_data = df_data[["date", nav_col]].rename(columns={nav_col:"nav"})
    df_data["nav"] = pd.to_numeric(df_data["nav"], errors="coerce")
    return df_data[df_data["nav"].notna()].sort_values("date").drop_duplicates("date").set_index("date")


def load_trades_from_daily_report():
    """
    从日报表读取交易明细（sheet "交易明细表"）
    处理交易类别：基金买卖、基金红利到账
    """
    daily_report_path = get_latest_daily_report(config.DATA_RAW_DIR, config.DAILY_REPORT_PATTERN)
    if daily_report_path is None:
        print("错误：未找到日报表文件")
        return None
    # 读取交易明细表，header=3表示第4行为列名（从0开始）
    df = pd.read_excel(daily_report_path, sheet_name=config.SHEET_TRADES, header=3, dtype=str)
    # 列名映射
    col_map = {}
    for col in df.columns:
        col_str = str(col).strip()
        if "业务日期" in col_str or "日期" in col_str: col_map["date"] = col
        elif "证券代码" in col_str or "代码" == col_str: col_map["code"] = col
        elif "证券名称" in col_str or "简称" in col_str or "名称" == col_str: col_map["name"] = col
        elif "交易数量" in col_str or "数量" == col_str: col_map["quantity"] = col
        elif "交易竞价" in col_str or "价格" == col_str: col_map["price"] = col
        elif "交割金额" in col_str or "金额" == col_str: col_map["amount"] = col
        elif "交易类别" in col_str or "类别" in col_str: col_map["trade_type"] = col
        elif "委托方向" in col_str or "方向" in col_str: col_map["direction"] = col
    df = df.rename(columns={v:k for k,v in col_map.items()})
    # 清洗日期
    if "date" in df.columns:
        df["date"] = df["date"].apply(parse_date)
        df = df[df["date"].notna()]
    # 清洗代码
    if "code" in df.columns:
        df["code"] = df["code"].apply(clean_code)
        df = df[df["code"].notna()]
    # 清洗数量、金额、价格
    for col in ["quantity", "amount", "price"]:
        if col in df.columns:
            df[col] = df[col].apply(clean_number)
    # 处理交易类别 - 原始值包含乱码，需要按原始字节判断
    # 基金买卖 = b'\xc1\xf5\xc9\xf0\xc2%\xf2%\xc9\xf0\xc2%\xa1\xa3' (GBK: 基金买卖)
    # 基金红利到账 = b'\xc1\xf5\xc9\xf0\xc2%\xf2%\xc9\xf0\xc1\xf7\xb6\xf7%\xcb\xb0%\xb5\xc0\xd5\xc9' (GBK: 基金红利到账)
    def decode_trade_type(val):
        if pd.isna(val):
            return ""
        try:
            # 尝试用latin1编码获取原始字节，然后用gbk解码
            raw_bytes = str(val).encode('latin1')
            decoded = raw_bytes.decode('gbk', errors='ignore')
            return decoded
        except:
            return str(val)

    df["trade_type_decoded"] = df["trade_type"].apply(decode_trade_type)

    # 处理方向
    def determine_direction(row):
        trade_type = str(row.get("trade_type_decoded", ""))
        if "红利" in trade_type or "分红" in trade_type:
            return "dividend"
        elif "买卖" in trade_type:
            # 根据交割金额符号判断买入/卖出
            amount = row.get("amount", 0)
            if pd.notna(amount):
                # 交割金额为正=卖出（资金流入），为负=买入（资金流出）
                return "sell" if amount > 0 else "buy"
        return "other"

    df["direction"] = df.apply(determine_direction, axis=1)
    # 红利到账记录为正值（收益）
    df.loc[df["direction"] == "dividend", "amount"] = df.loc[df["direction"] == "dividend", "amount"].abs()
    # 筛选有效记录
    df["trade_type"] = df["trade_type_decoded"]  # 使用解码后的值
    keep_cols = [c for c in ["date","code","name","direction","quantity","price","amount","trade_type"] if c in df.columns]
    df = df[keep_cols].copy()
    return df.sort_values("date").reset_index(drop=True)


def load_holdings():
    """
    读取持仓查询文件
    返回DataFrame，包含：日期、代码、名称、持仓数量、市值、成本等
    """
    filepath = os.path.join(config.DATA_RAW_DIR, config.FILE_HOLDINGS)
    if not os.path.exists(filepath):
        print(f"警告：持仓文件不存在 {filepath}")
        return None
    # 读取持仓数据 - 第一行是日期，第二行是列名
    df = pd.read_excel(filepath, sheet_name=config.SHEET_HOLDINGS, header=None, skiprows=1, dtype=str)
    # 列名映射（基于实际文件结构）
    # 列0:日期 列11:证券代码 列12:证券名称 列13:资产类别 列25:参考成本 列40:持仓市值
    col_map = {
        0: "date",
        11: "code",
        12: "name",
        13: "asset_type",
        25: "cost_price",
        40: "market_value",
    }
    df = df.rename(columns=col_map)
    # 清洗
    if "date" in df.columns:
        df["date"] = df["date"].apply(parse_date)
    if "code" in df.columns:
        df["code"] = df["code"].apply(clean_code)
    for col in ["market_value", "cost_price"]:
        if col in df.columns:
            df[col] = df[col].apply(clean_number)
    # 过滤有效持仓（只保留REITs）
    if "asset_type" in df.columns:
        df = df[df["asset_type"].astype(str).str.contains("REITs|基金", na=False, case=False)]
    # 过滤有效代码
    df = df[df["code"].notna() & (df["code"] != "000000")]
    keep_cols = [c for c in ["date","code","name","market_value","cost_price"] if c in df.columns]
    return df[keep_cols].dropna(subset=["code"]).reset_index(drop=True)


def load_index_weight_932006():
    """
    读取932006指数权重文件
    返回DataFrame: columns=[code, name, weight]
    """
    filepath = os.path.join(config.DATA_RAW_DIR, config.FILE_WEIGHT_932006)
    if not os.path.exists(filepath):
        print(f"警告：932006权重文件不存在 {filepath}")
        return None
    df = pd.read_excel(filepath)
    # 列名映射
    col_map = {}
    for col in df.columns:
        col_str = str(col).strip()
        if "成分券代码" in col_str or "Constituent Code" in col_str: col_map["code"] = col
        elif "成分券名称" in col_str or "Constituent Name" in col_str: col_map["name"] = col
        elif "权重" in col_str or "weight" in col_str.lower(): col_map["weight"] = col
    df = df.rename(columns={v:k for k,v in col_map.items()})
    if "code" in df.columns:
        df["code"] = df["code"].apply(clean_code)
    if "weight" in df.columns:
        df["weight"] = df["weight"].apply(clean_number) / 100  # 转为小数
    keep_cols = [c for c in ["code","name","weight"] if c in df.columns]
    return df[keep_cols].dropna(subset=["code"]).reset_index(drop=True)


def align_and_save():
    """
    主数据对齐函数
    """
    # 加载REITs基础信息
    reits_info = load_reits_info()
    print(f"REITs信息: {len(reits_info)} 条")
    # 加载指数数据
    index_df = load_index()
    print(f"指数数据: {len(index_df)} 条")
    # 加载净值数据
    nav_df = load_nav_from_daily_report()
    print(f"净值数据: {len(nav_df)} 条" if nav_df is not None else "净值数据: 无")
    # 加载交易数据
    trades_df = load_trades_from_daily_report()
    print(f"交易数据: {len(trades_df)} 条" if trades_df is not None else "交易数据: 无")
    # 加载持仓数据
    holdings_df = load_holdings()
    print(f"持仓数据: {len(holdings_df)} 条" if holdings_df is not None else "持仓数据: 无")
    # 加载指数权重
    weight_df = load_index_weight_932006()
    print(f"指数权重: {len(weight_df)} 条" if weight_df is not None else "指数权重: 无")
    # 保存原始数据
    reits_info.to_csv(os.path.join(config.DATA_PROCESSED_DIR,"reits_info.csv"), index=False, encoding="utf-8-sig")
    if nav_df is not None:
        nav_df.to_csv(os.path.join(config.DATA_PROCESSED_DIR,"nav_daily.csv"), encoding="utf-8-sig")
    if trades_df is not None:
        trades_df.to_csv(os.path.join(config.DATA_PROCESSED_DIR,"trades_clean.csv"), index=False, encoding="utf-8-sig")
    if holdings_df is not None:
        holdings_df.to_csv(os.path.join(config.DATA_PROCESSED_DIR,"holdings.csv"), index=False, encoding="utf-8-sig")
    if weight_df is not None:
        weight_df.to_csv(os.path.join(config.DATA_PROCESSED_DIR,"index_weight_932006.csv"), index=False, encoding="utf-8-sig")
    # 合并日频数据
    daily = pd.merge(index_df.reset_index(), nav_df.reset_index(), on="date", how="outer").sort_values("date").set_index("date")
    # 按配置的基准日进行归一化
    base_date = pd.to_datetime(config.BASE_DATE)
    if base_date is not None:
        # 找基准日或之前最近的值
        ib = None
        nb = None
        if "reits_index" in index_df.columns:
            idx_before = index_df.loc[index_df.index <= base_date, "reits_index"]
            if not idx_before.empty:
                ib = idx_before.iloc[-1]
        if nav_df is not None and "nav" in nav_df.columns:
            nav_before = nav_df.loc[nav_df.index <= base_date, "nav"]
            if not nav_before.empty:
                nb = nav_before.iloc[-1]
        if ib is not None and not pd.isna(ib) and "reits_index" in daily.columns:
            daily["reits_index_norm"] = daily["reits_index"] / ib
        if nb is not None and not pd.isna(nb) and "nav" in daily.columns:
            daily["nav_norm"] = daily["nav"] / nb
        # 计算超额收益
        if "nav_norm" in daily.columns and "reits_index_norm" in daily.columns:
            daily["excess"] = daily["nav_norm"] - daily["reits_index_norm"]
            daily["excess_pct"] = daily["excess"] * 100
    daily.to_csv(os.path.join(config.DATA_PROCESSED_DIR,"daily.csv"), encoding="utf-8-sig")
    # 给交易数据添加板块信息
    if trades_df is not None and "sector" in reits_info.columns:
        trades_df["sector"] = trades_df["code"].map(reits_info.set_index("code")["sector"].to_dict())
    return reits_info, daily, nav_df, trades_df, holdings_df, weight_df


if __name__ == "__main__":
    reits_info, daily, nav_df, trades_df, holdings_df, weight_df = align_and_save()
    print(f"\nREITs信息: {len(reits_info)} 条")
    if "sector" in reits_info.columns:
        print(f"  板块: {sorted(reits_info['sector'].dropna().unique().tolist())}")
    print(f"日频数据: {daily.shape}, 日期: {daily.index.min().date()} ~ {daily.index.max().date()}")
    if nav_df is not None:
        print(f"净值数据: {nav_df.shape}, 日期: {nav_df.index.min().date()} ~ {nav_df.index.max().date()}")
    if trades_df is not None:
        print(f"交易数据: {trades_df.shape}, 日期: {trades_df['date'].min().date()} ~ {trades_df['date'].max().date()}")
        print(f"  交易类型分布:\n{trades_df['direction'].value_counts()}")
    if holdings_df is not None:
        print(f"持仓数据: {holdings_df.shape}")
    if weight_df is not None:
        print(f"指数权重: {weight_df['weight'].sum():.2%}")
