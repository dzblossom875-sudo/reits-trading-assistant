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
    板块表现 vs 交易行为对比图

    有涨跌幅数据时：
      散点/气泡图（X=涨跌幅%, Y=净买入万元），气泡大小=总交易量
      四象限标注，直观回答"买没买对板块"

    无涨跌幅数据时：
      左右并排水平柱状图（左=买入/卖出，右=净买入）
    """
    sector_df = analyze_sector_trades(trades_df, reits_info)
    if sector_df.empty:
        return None

    title_suffix = f" - {period_label}" if period_label else ""

    if sector_returns is not None and not sector_returns.empty:
        # ── 散点气泡图：涨跌幅 vs 净买入 ──
        merged = sector_df.merge(sector_returns, on="sector", how="left").copy()
        merged["avg_return_pct"] = merged["avg_return_pct"].fillna(0)
        merged["net_wan"] = merged["net_amount"] / 1e4
        merged["total_wan"] = merged["total_amount"] / 1e4

        fig, ax = plt.subplots(figsize=(12, 8))

        # 气泡大小正比于总交易量
        max_total = merged["total_wan"].max()
        sizes = (merged["total_wan"] / max_total * 400).clip(lower=40) if max_total > 0 else [80] * len(merged)
        colors = ["#d62728" if v > 0 else "#1f77b4" for v in merged["net_wan"]]

        ax.scatter(merged["avg_return_pct"], merged["net_wan"],
                   s=sizes, c=colors, alpha=0.75, zorder=5,
                   edgecolors="white", linewidths=0.8)

        # 板块名标注
        for _, row in merged.iterrows():
            ax.annotate(row["sector"],
                        xy=(row["avg_return_pct"], row["net_wan"]),
                        xytext=(6, 4), textcoords="offset points",
                        fontsize=9, color="#333")

        # 四象限参考线
        ax.axvline(0, color="gray", linewidth=1, linestyle="--", alpha=0.6)
        ax.axhline(0, color="gray", linewidth=1, linestyle="--", alpha=0.6)

        # 四象限文字说明
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        xr, yr = xlim[1] - xlim[0], ylim[1] - ylim[0]
        quadrant_style = dict(fontsize=8, alpha=0.45, style="italic")
        ax.text(xlim[1] - xr*0.01, ylim[1] - yr*0.02, "涨 & 净买入\n【买对了】",
                ha="right", va="top", color="#2ca02c", **quadrant_style)
        ax.text(xlim[0] + xr*0.01, ylim[1] - yr*0.02, "跌 & 净买入\n【买错了】",
                ha="left",  va="top", color="#d62728", **quadrant_style)
        ax.text(xlim[1] - xr*0.01, ylim[0] + yr*0.02, "涨 & 净卖出\n【卖早了】",
                ha="right", va="bottom", color="#ff7f0e", **quadrant_style)
        ax.text(xlim[0] + xr*0.01, ylim[0] + yr*0.02, "跌 & 净卖出\n【躲过了】",
                ha="left",  va="bottom", color="#2ca02c", **quadrant_style)

        ax.set_xlabel("板块区间涨跌幅（%，个股等权）", fontsize=11)
        ax.set_ylabel("净买入金额（万元）", fontsize=11)
        ax.set_title(
            f"板块交易行为 vs 涨跌幅{title_suffix}\n"
            "气泡大小 = 总交易量   红 = 净买入   蓝 = 净卖出",
            fontsize=13, fontweight="bold"
        )
        ax.yaxis.grid(True, alpha=0.25)
        ax.xaxis.grid(True, alpha=0.25)
        ax.set_axisbelow(True)

    else:
        # ── 无涨跌幅：左右并排水平柱状图 ──
        df = sector_df.sort_values("total_amount", ascending=True).reset_index(drop=True)
        sectors = df["sector"].tolist()
        n = len(sectors)
        y = np.arange(n)
        bar_h = 0.35

        fig, (ax_left, ax_right) = plt.subplots(
            1, 2, figsize=(14, max(5, n * 0.9)), sharey=True
        )
        fig.subplots_adjust(wspace=0.05)

        # 左图：买入 / 卖出
        ax_left.barh(y + bar_h/2, df["buy_amount"] / 1e4,  height=bar_h,
                     color="#d62728", alpha=0.8, label="买入")
        ax_left.barh(y - bar_h/2, df["sell_amount"] / 1e4, height=bar_h,
                     color="#1f77b4", alpha=0.8, label="卖出")
        ax_left.set_yticks(y)
        ax_left.set_yticklabels(sectors, fontsize=10)
        ax_left.set_xlabel("金额（万元）", fontsize=10)
        ax_left.set_title("买入 / 卖出金额", fontsize=11)
        ax_left.legend(fontsize=9, loc="lower right")
        ax_left.xaxis.grid(True, alpha=0.3)
        ax_left.set_axisbelow(True)

        # 右图：净买入
        net_colors = ["#2ca02c" if v > 0 else "#ff7f0e" for v in df["net_amount"]]
        ax_right.barh(y, df["net_amount"] / 1e4, height=0.5,
                      color=net_colors, alpha=0.85)
        ax_right.axvline(0, color="gray", linewidth=0.8, linestyle="-")
        ax_right.set_xlabel("净买入金额（万元）", fontsize=10)
        ax_right.set_title("净买入金额", fontsize=11)
        ax_right.xaxis.grid(True, alpha=0.3)
        ax_right.set_axisbelow(True)

        fig.suptitle(f"各板块交易金额分布{title_suffix}", fontsize=13, fontweight="bold")

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
