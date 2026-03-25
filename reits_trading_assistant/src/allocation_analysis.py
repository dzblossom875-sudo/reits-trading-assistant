"""
配置偏移分析模块
计算个券持仓权重偏移和板块配置偏移
"""
import os
import sys
import pandas as pd
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def calc_allocation_bias(holdings_df: pd.DataFrame, weight_df: pd.DataFrame,
                         reits_info: pd.DataFrame, latest_date=None) -> pd.DataFrame:
    """
    计算个券持仓权重偏移：账户持仓权重 - 指数权重
    holdings_df: 持仓数据
    weight_df: 指数权重数据
    reits_info: REITs基础信息（用于补全名称和板块）
    latest_date: 计算日期，默认使用持仓数据最新日期
    """
    if holdings_df is None or weight_df is None:
        return None
    if latest_date is None:
        latest_date = holdings_df["date"].max() if "date" in holdings_df.columns else None
    # 获取最新持仓
    if "date" in holdings_df.columns and latest_date is not None:
        latest_holdings = holdings_df[holdings_df["date"] == latest_date].copy()
    else:
        latest_holdings = holdings_df.copy()
    if latest_holdings.empty:
        return None
    # 计算账户持仓权重
    total_mv = latest_holdings["market_value"].sum() if "market_value" in latest_holdings.columns else None
    if total_mv is None or total_mv == 0:
        # 用数量*成本价估算
        if "cost_price" in latest_holdings.columns:
            latest_holdings["est_mv"] = latest_holdings["holdings"] * latest_holdings["cost_price"]
            total_mv = latest_holdings["est_mv"].sum()
        else:
            total_mv = 1
    if "market_value" in latest_holdings.columns:
        latest_holdings["account_weight"] = latest_holdings["market_value"] / total_mv
    else:
        latest_holdings["account_weight"] = latest_holdings["est_mv"] / total_mv
    # 合并指数权重
    result = latest_holdings.merge(
        weight_df[["code", "weight"]].rename(columns={"weight": "index_weight"}),
        on="code",
        how="outer"
    )
    result["account_weight"] = result["account_weight"].fillna(0)
    result["index_weight"] = result["index_weight"].fillna(0)
    # 计算偏移
    result["weight_bias"] = result["account_weight"] - result["index_weight"]
    # 补充名称和板块
    if reits_info is not None:
        code_to_name = reits_info.set_index("code")["name"].to_dict() if "name" in reits_info.columns else {}
        code_to_sector = reits_info.set_index("code")["sector"].to_dict() if "sector" in reits_info.columns else {}
        result["name"] = result["code"].map(code_to_name)
        result["sector"] = result["code"].map(code_to_sector)
    return result[["code", "name", "sector", "account_weight", "index_weight", "weight_bias"]].sort_values("weight_bias", ascending=False)


def calc_sector_allocation_bias(holdings_df: pd.DataFrame, weight_df: pd.DataFrame,
                                reits_info: pd.DataFrame, latest_date=None) -> pd.DataFrame:
    """
    计算板块配置偏移：账户持仓按板块加总 - 指数权重按板块加总
    """
    if holdings_df is None or weight_df is None or reits_info is None or "sector" not in reits_info.columns:
        return None
    # 先计算个券偏移
    detail = calc_allocation_bias(holdings_df, weight_df, reits_info, latest_date)
    if detail is None:
        return None
    # 按板块汇总
    sector_account = detail.groupby("sector")["account_weight"].sum()
    sector_index = detail.groupby("sector")["index_weight"].sum()
    result = pd.DataFrame({
        "account_weight": sector_account,
        "index_weight": sector_index
    }).fillna(0)
    result["weight_bias"] = result["account_weight"] - result["index_weight"]
    result = result.reset_index()
    return result.sort_values("weight_bias", ascending=False)


def calc_sector_bias_history(
    holdings_raw: pd.DataFrame,
    weight_df: pd.DataFrame,
    reits_info: pd.DataFrame,
) -> pd.DataFrame:
    """
    按日计算板块配置偏移历史时序。
    holdings_raw: load_holdings_from_raw() 输出，含 date/code/market_value 列（每日每只券一行）
    weight_df: 指数权重快照，含 code/weight 列
    返回长表: [date, sector, account_weight, index_weight, weight_bias]
    """
    if holdings_raw is None or holdings_raw.empty or weight_df is None or reits_info is None:
        return None
    if "sector" not in reits_info.columns:
        return None

    code_sector = reits_info.set_index("code")["sector"].to_dict()
    # 指数权重按板块汇总（固定快照）
    idx_merged = weight_df.copy()
    idx_merged["sector"] = idx_merged["code"].map(code_sector)
    idx_sector = idx_merged.groupby("sector")["weight"].sum()

    h = holdings_raw.copy()
    h["sector"] = h["code"].map(code_sector)
    h = h.dropna(subset=["sector"])

    results = []
    for dt, day_df in h.groupby("date"):
        total_mv = day_df["market_value"].sum()
        if total_mv == 0:
            continue
        acc_sector = day_df.groupby("sector")["market_value"].sum() / total_mv
        all_sectors = set(acc_sector.index) | set(idx_sector.index)
        for sector in all_sectors:
            aw = float(acc_sector.get(sector, 0.0))
            iw = float(idx_sector.get(sector, 0.0))
            results.append({
                "date": dt,
                "sector": sector,
                "account_weight": aw,
                "index_weight": iw,
                "weight_bias": aw - iw,
            })

    if not results:
        return None
    df = pd.DataFrame(results)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["date", "sector"]).reset_index(drop=True)


def save_allocation_bias(detail_df: pd.DataFrame, sector_df: pd.DataFrame, output_dir: str,
                         history_df: pd.DataFrame = None):
    """保存配置偏移结果到Excel和固定路径Parquet"""
    if detail_df is None and sector_df is None:
        return None

    # 1. 保存到带时间戳的Excel（原有功能）
    out_path = os.path.join(output_dir, "allocation_bias.xlsx")
    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        if detail_df is not None:
            display_df = detail_df.copy()
            for col in ["account_weight", "index_weight", "weight_bias"]:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(lambda x: f"{x:.2%}")
            display_df = display_df.rename(columns={
                "code": "证券代码", "name": "证券名称", "sector": "板块",
                "account_weight": "账户权重", "index_weight": "指数权重", "weight_bias": "偏移",
            })
            display_df.to_excel(writer, sheet_name="个券配置偏移", index=False)
        if sector_df is not None:
            display_df = sector_df.copy()
            for col in ["account_weight", "index_weight", "weight_bias"]:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(lambda x: f"{x:.2%}")
            display_df = display_df.rename(columns={
                "sector": "板块", "account_weight": "账户权重",
                "index_weight": "指数权重", "weight_bias": "偏移",
            })
            display_df.to_excel(writer, sheet_name="板块配置偏移", index=False)

    # 2. 保存到固定路径Parquet（防腐层）
    # 确保 data/processed 目录存在
    processed_dir = os.path.join(config.DATA_PROCESSED_DIR)
    os.makedirs(processed_dir, exist_ok=True)

    if sector_df is not None:
        # 前向填充保证数据连贯性，保存为Parquet
        sector_parquet = sector_df.copy().ffill()
        sector_parquet_path = os.path.join(processed_dir, "allocation_bias_sector.parquet")
        sector_parquet.to_parquet(sector_parquet_path, index=False)

    if detail_df is not None:
        # 前向填充保证数据连贯性，保存为Parquet
        detail_parquet = detail_df.copy().ffill()
        detail_parquet_path = os.path.join(processed_dir, "allocation_bias_detail.parquet")
        detail_parquet.to_parquet(detail_parquet_path, index=False)

    if history_df is not None and not history_df.empty:
        history_parquet_path = os.path.join(processed_dir, "allocation_bias_history.parquet")
        history_df.to_parquet(history_parquet_path, index=False)

    return out_path
