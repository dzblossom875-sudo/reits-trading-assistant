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


def save_allocation_bias(detail_df: pd.DataFrame, sector_df: pd.DataFrame, output_dir: str):
    """保存配置偏移结果到Excel的不同sheet"""
    if detail_df is None and sector_df is None:
        return None
    out_path = os.path.join(output_dir, "allocation_bias.xlsx")
    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        if detail_df is not None:
            # 格式化百分比
            display_df = detail_df.copy()
            for col in ["account_weight", "index_weight", "weight_bias"]:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(lambda x: f"{x:.2%}")
            display_df.to_excel(writer, sheet_name="个券配置偏移", index=False)
        if sector_df is not None:
            display_df = sector_df.copy()
            for col in ["account_weight", "index_weight", "weight_bias"]:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(lambda x: f"{x:.2%}")
            display_df.to_excel(writer, sheet_name="板块配置偏移", index=False)
    return out_path
