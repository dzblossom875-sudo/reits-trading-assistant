"""
板块分析模块
"""
import os
import sys
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# 中文字体设置
def _setup_font():
    for font in ["SimHei", "KaiTi", "Microsoft YaHei"]:
        try:
            plt.rcParams["font.sans-serif"] = [font]
            plt.rcParams["axes.unicode_minus"] = False
            return font
        except Exception:
            continue
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return "DejaVu Sans"

FONT_NAME = _setup_font()


def analyze_sector_trades(trades_df: pd.DataFrame, reits_info: pd.DataFrame) -> pd.DataFrame:
    """按板块汇总交易金额，返回DataFrame(sector, buy_amount, sell_amount, net_amount)"""
    df = trades_df.copy()
    if "sector" not in df.columns and reits_info is not None:
        df["sector"] = df["code"].map(reits_info.set_index("code")["sector"].to_dict())

    df["sector"] = df["sector"].fillna("其他")

    # 区分买卖和红利
    buy = df[df["direction"] == "buy"].groupby("sector")["amount"].sum().rename("buy_amount")
    sell = df[df["direction"] == "sell"].groupby("sector")["amount"].sum().rename("sell_amount")
    dividend = df[df["direction"] == "dividend"].groupby("sector")["amount"].sum().rename("dividend_amount")

    result = pd.concat([buy, sell, dividend], axis=1).fillna(0)
    result["net_amount"] = result["buy_amount"] - result["sell_amount"]
    result["total_amount"] = result["buy_amount"] + result["sell_amount"]
    return result.sort_values("total_amount", ascending=False).reset_index()


def calc_sector_returns(reits_prices: pd.DataFrame, reits_info: pd.DataFrame, period_start=None, period_end=None) -> pd.DataFrame:
    """
    计算板块区间涨跌幅（个股等权）
    reits_prices: DataFrame, index=date, columns=code, values=close
    reits_info: DataFrame with code, sector
    period_start/period_end: 计算区间
    """
    if reits_prices is None or reits_prices.empty or reits_info is None:
        return None

    df = reits_prices.copy()
    if period_start:
        df = df[df.index >= period_start]
    if period_end:
        df = df[df.index <= period_end]

    if df.empty or len(df) < 2:
        return None

    # 计算个股涨跌幅
    first_day = df.iloc[0]
    last_day = df.iloc[-1]
    stock_return = ((last_day - first_day) / first_day * 100).dropna()

    # 映射到板块
    code_to_sector = reits_info.set_index("code")["sector"].to_dict() if "sector" in reits_info.columns else {}

    result = []
    for code, ret in stock_return.items():
        sector = code_to_sector.get(code)
        if sector:
            result.append({"code": code, "sector": sector, "return_pct": ret})

    if not result:
        return None

    df_ret = pd.DataFrame(result)
    # 板块等权平均
    sector_ret = df_ret.groupby("sector")["return_pct"].mean().reset_index()
    sector_ret.columns = ["sector", "avg_return_pct"]
    return sector_ret.sort_values("avg_return_pct", ascending=False)


def plot_sector_performance(trades_df: pd.DataFrame, reits_info: pd.DataFrame = None,
                           sector_returns: pd.DataFrame = None, period_label=""):
    """
    生成板块交易金额和涨跌幅对比图
    - 横坐标左轴：板块区间涨跌幅（%）
    - 横坐标右轴：账户对应期间板块净买入金额
    标注口径：个股等权
    """
    sector_df = analyze_sector_trades(trades_df, reits_info)
    if sector_df.empty:
        return None

    fig, ax1 = plt.subplots(figsize=(13, 7))

    # 左轴：涨跌幅柱状图（如果有数据）
    if sector_returns is not None and not sector_returns.empty:
        # 合并数据
        merged = sector_df.merge(sector_returns, on="sector", how="left")
        merged = merged.sort_values("avg_return_pct", ascending=True)  # 从左到右涨跌幅递增
        colors = ["#d62728" if x > 0 else "#1f77b4" for x in merged["avg_return_pct"].fillna(0)]
        ax1.barh(range(len(merged)), merged["avg_return_pct"].fillna(0), color=colors, alpha=0.7, height=0.4)
        ax1.set_yticks(range(len(merged)))
        ax1.set_yticklabels(merged["sector"].tolist(), fontsize=10)
        ax1.set_xlabel("板块涨跌幅（%，个股等权）", fontsize=11, color="#333")
        ax1.axvline(0, color="gray", linewidth=0.8, linestyle="-", alpha=0.5)
        ax1.set_ylabel("板块", fontsize=11)
        title_suffix = f" - {period_label}" if period_label else ""
        ax1.set_title(f"板块表现 vs 交易金额{title_suffix}\n（涨跌幅口径：个股等权）", fontsize=13, fontweight="bold")
    else:
        # 没有涨跌幅数据，只显示交易金额
        x = range(len(sector_df))
        width = 0.35
        bars_buy = ax1.bar([i - width / 2 for i in x], sector_df["buy_amount"] / 1e6,
                          width=width, label="买入", color="#d62728", alpha=0.8)
        bars_sell = ax1.bar([i + width / 2 for i in x], sector_df["sell_amount"] / 1e6,
                           width=width, label="卖出", color="#1f77b4", alpha=0.8)
        ax1.set_xticks(list(x))
        ax1.set_xticklabels(sector_df["sector"].tolist(), rotation=30, ha="right", fontsize=10)
        ax1.set_ylabel("金额（百万元）", fontsize=11)
        ax1.set_title("各板块交易金额分布", fontsize=13, fontweight="bold")
        ax1.legend(fontsize=10)

    # 右轴：净买入金额（如果有涨跌幅数据）
    if sector_returns is not None and not sector_returns.empty:
        ax2 = ax1.twinx()
        merged_sorted = sector_df.merge(sector_returns, on="sector", how="left").sort_values("avg_return_pct", ascending=True)
        colors_net = ["#2ca02c" if x > 0 else "#ff7f0e" for x in merged_sorted["net_amount"]]
        ax2.scatter(merged_sorted["net_amount"] / 1e4, range(len(merged_sorted)),
                   c=colors_net, s=100, alpha=0.8, zorder=5, label="净买入")
        ax2.set_ylabel("净买入金额（万元）", fontsize=11, color="#2ca02c")
        ax2.tick_params(axis='y', labelcolor="#2ca02c")
        ax2.set_yticks(range(len(merged_sorted)))
        ax2.set_yticklabels(merged_sorted["sector"].tolist(), fontsize=10)

    ax1.yaxis.grid(True, alpha=0.3)
    ax1.set_axisbelow(True)

    plt.tight_layout()
    out_path = os.path.join(config.OUTPUT_FIGURES_DIR, "sector_performance.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_sector_rotation_dual(trades_df: pd.DataFrame, reits_prices: pd.DataFrame = None,
                              reits_info: pd.DataFrame = None):
    """
    板块轮动双图：
    1. 月度净买入热力图
    2. 月度涨跌幅热力图（如果有价格数据）
    """
    if trades_df is None or trades_df.empty:
        return None, None
    df = trades_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    if "sector" not in df.columns:
        return None, None

    df["signed_amount"] = df.apply(
        lambda r: r["amount"] if r["direction"] == "buy" else (-r["amount"] if r["direction"] == "sell" else 0), axis=1
    )
    df["month"] = df["date"].dt.to_period("M").apply(lambda p: str(p))

    # 图1：月度净买入热力图
    pivot_net = df.groupby(["month", "sector"])["signed_amount"].sum().unstack(fill_value=0) / 1e4

    fig1, ax1 = plt.subplots(figsize=(max(10, len(pivot_net.columns) * 1.2), max(6, len(pivot_net) * 0.6)))
    import matplotlib.colors as mcolors
    cmap1 = plt.cm.RdBu
    vmax1 = pivot_net.abs().values.max()
    vmin1 = -vmax1 if vmax1 > 0 else -1

    im1 = ax1.imshow(pivot_net.values, aspect="auto", cmap=cmap1, vmin=vmin1, vmax=vmax1)
    ax1.set_xticks(range(len(pivot_net.columns)))
    ax1.set_xticklabels(pivot_net.columns.tolist(), rotation=45, ha="right", fontsize=9)
    ax1.set_yticks(range(len(pivot_net.index)))
    ax1.set_yticklabels(pivot_net.index.tolist(), fontsize=9)
    plt.colorbar(im1, ax=ax1, label="净买入（万元）")
    ax1.set_title("板块轮动热力图 - 月度净买入", fontsize=13, fontweight="bold")
    plt.tight_layout()
    out_path1 = os.path.join(config.OUTPUT_FIGURES_DIR, "sector_rotation_net.png")
    plt.savefig(out_path1, dpi=150, bbox_inches="tight")
    plt.close(fig1)

    # 图2：月度涨跌幅热力图（需要价格数据）
    out_path2 = None
    if reits_prices is not None and not reits_prices.empty and reits_info is not None:
        # 计算各板块月度涨跌幅
        sector_monthly = []
        code_to_sector = reits_info.set_index("code")["sector"].to_dict()

        for sector in reits_info["sector"].unique():
            sector_codes = [c for c, s in code_to_sector.items() if s == sector and c in reits_prices.columns]
            if not sector_codes:
                continue
            sector_df = reits_prices[sector_codes].mean(axis=1)  # 板块等权
            sector_df = sector_df.dropna()
            if len(sector_df) < 2:
                continue
            # 计算月度收益
            monthly = sector_df.resample('ME').last()
            monthly_ret = monthly.pct_change().dropna() * 100
            for month, ret in monthly_ret.items():
                sector_monthly.append({
                    "month": month.strftime("%Y-%m"),
                    "sector": sector,
                    "return_pct": ret
                })

        if sector_monthly:
            df_ret = pd.DataFrame(sector_monthly)
            pivot_ret = df_ret.pivot(index="month", columns="sector", values="return_pct").fillna(0)

            fig2, ax2 = plt.subplots(figsize=(max(10, len(pivot_ret.columns) * 1.2), max(6, len(pivot_ret) * 0.6)))
            cmap2 = plt.cm.RdYlGn  # 红绿配色
            vmax2 = max(abs(pivot_ret.values.min()), abs(pivot_ret.values.max()))
            vmin2 = -vmax2

            im2 = ax2.imshow(pivot_ret.values, aspect="auto", cmap=cmap2, vmin=vmin2, vmax=vmax2)
            ax2.set_xticks(range(len(pivot_ret.columns)))
            ax2.set_xticklabels(pivot_ret.columns.tolist(), rotation=45, ha="right", fontsize=9)
            ax2.set_yticks(range(len(pivot_ret.index)))
            ax2.set_yticklabels(pivot_ret.index.tolist(), fontsize=9)
            plt.colorbar(im2, ax=ax2, label="涨跌幅（%）")
            ax2.set_title("板块轮动热力图 - 月度涨跌幅（个股等权）", fontsize=13, fontweight="bold")
            plt.tight_layout()
            out_path2 = os.path.join(config.OUTPUT_FIGURES_DIR, "sector_rotation_return.png")
            plt.savefig(out_path2, dpi=150, bbox_inches="tight")
            plt.close(fig2)

    return out_path1, out_path2
