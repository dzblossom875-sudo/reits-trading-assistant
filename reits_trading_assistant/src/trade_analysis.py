"""
交易行为分析模块
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

_setup_font()


def summarize_trades(trades_df: pd.DataFrame) -> pd.DataFrame:
    """按日汇总净买入（买入-卖出），识别大幅加减仓"""
    df = trades_df.copy()
    df["signed_amount"] = df.apply(
        lambda r: r["amount"] if r["direction"] == "buy" else (-r["amount"] if r["direction"] == "sell" else 0), axis=1
    )
    daily = df.groupby("date").agg(
        buy_amount=("amount", lambda x: x[df.loc[x.index, "direction"] == "buy"].sum()),
        sell_amount=("amount", lambda x: x[df.loc[x.index, "direction"] == "sell"].sum()),
        dividend_amount=("amount", lambda x: x[df.loc[x.index, "direction"] == "dividend"].sum()),
        net_amount=("signed_amount", "sum"),
        trade_count=("amount", "count"),
    ).reset_index()

    threshold = daily["net_amount"].abs().quantile(0.75)
    daily["signal"] = "neutral"
    daily.loc[daily["net_amount"] > threshold, "signal"] = "heavy_buy"
    daily.loc[daily["net_amount"] < -threshold, "signal"] = "heavy_sell"
    return daily.sort_values("date").reset_index(drop=True)


def plot_trade_flow(trades_df: pd.DataFrame, index_df: pd.DataFrame):
    """
    资金流向图 - 全时间范围
    - 左轴：日交易金额，买入为正（红色），卖出为负（蓝色），同一柱状图
    - 净买入用散点标识
    - 检查数据连续性，调整坐标轴确保最高最低点都在图内
    """
    daily = summarize_trades(trades_df)
    daily["date"] = pd.to_datetime(daily["date"])

    # 获取全量数据（不再限制为最近一个月）
    # 以基准日为起点
    base_date = pd.to_datetime(config.BASE_DATE)
    daily_filtered = daily[daily["date"] >= base_date].copy()

    if daily_filtered.empty:
        return None

    # 准备指数数据
    idx = index_df.copy()
    idx.index = pd.to_datetime(idx.index)
    idx_filtered = idx[idx.index >= base_date]

    fig, ax1 = plt.subplots(figsize=(14, 7))

    # 左轴：日交易金额（买入正红色，卖出负蓝色）
    # 买入
    buy_data = daily_filtered[daily_filtered["buy_amount"] > 0]
    ax1.bar(buy_data["date"], buy_data["buy_amount"] / 1e4,
            color="#d62728", alpha=0.7, width=1, label="买入", zorder=3)

    # 卖出（取负值）
    sell_data = daily_filtered[daily_filtered["sell_amount"] > 0]
    ax1.bar(sell_data["date"], -sell_data["sell_amount"] / 1e4,
            color="#1f77b4", alpha=0.7, width=1, label="卖出", zorder=3)

    ax1.axhline(0, color="black", linewidth=0.8, linestyle="-", zorder=4)
    ax1.set_ylabel("日交易金额（万元）\n买入+/卖出-", fontsize=11, color="#333")

    # 计算Y轴范围确保所有数据可见
    max_val = max(daily_filtered["buy_amount"].max() / 1e4, daily_filtered["sell_amount"].max() / 1e4)
    ax1.set_ylim(-max_val * 1.1, max_val * 1.1)

    # 净买入散点
    ax1.scatter(daily_filtered["date"], daily_filtered["net_amount"] / 1e4,
               c="#2ca02c", s=30, alpha=0.6, zorder=5, label="净买入")

    # 右轴：指数
    if "reits_index" in idx_filtered.columns and not idx_filtered["reits_index"].dropna().empty:
        ax2 = ax1.twinx()
        idx_clean = idx_filtered["reits_index"].dropna()
        ax2.plot(idx_clean.index, idx_clean.values,
                 color="#ff7f0e", linewidth=1.5, label="中证REITs指数", zorder=2)
        ax2.set_ylabel("中证REITs指数", fontsize=11, color="#ff7f0e")
        ax2.tick_params(axis='y', labelcolor="#ff7f0e")

        # 确保指数在图内
        idx_min, idx_max = idx_clean.min(), idx_clean.max()
        ax2.set_ylim(idx_min * 0.95, idx_max * 1.05)

        lines2, labels2 = ax2.get_legend_handles_labels()
    else:
        lines2, labels2 = [], []

    lines1, labels1 = ax1.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9, ncol=2)

    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.xticks(rotation=30)
    ax1.set_title(f"资金流向与指数走势（基准日：{base_date.strftime('%Y-%m-%d')}）", fontsize=13, fontweight="bold")
    ax1.yaxis.grid(True, alpha=0.3)
    ax1.set_axisbelow(True)

    plt.tight_layout()
    out_path = os.path.join(config.OUTPUT_FIGURES_DIR, "trade_flow.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_sector_rotation(trades_df: pd.DataFrame):
    """板块轮动热力图 - 周度净买入（保留原功能）"""
    df = trades_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    if "sector" not in df.columns:
        return None

    df["signed_amount"] = df.apply(
        lambda r: r["amount"] if r["direction"] == "buy" else (-r["amount"] if r["direction"] == "sell" else 0), axis=1
    )
    df["week"] = df["date"].dt.to_period("W").apply(lambda p: str(p.start_time.date()))
    pivot = df.groupby(["week", "sector"])["signed_amount"].sum().unstack(fill_value=0) / 1e4

    if pivot.empty:
        return None

    fig, ax = plt.subplots(figsize=(max(10, len(pivot.columns) * 1.5), max(6, len(pivot) * 0.5)))
    import matplotlib.colors as mcolors
    cmap = plt.cm.RdBu
    vmax = pivot.abs().values.max()
    vmin = -vmax if vmax > 0 else -1

    im = ax.imshow(pivot.T.values, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_xticks(range(len(pivot.index)))
    ax.set_xticklabels(pivot.index.tolist(), rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(pivot.columns)))
    ax.set_yticklabels(pivot.columns.tolist(), fontsize=9)
    plt.colorbar(im, ax=ax, label="净买入（万元）")
    ax.set_title("板块轮动热力图（周度净买入）", fontsize=13, fontweight="bold")

    plt.tight_layout()
    out_path = os.path.join(config.OUTPUT_FIGURES_DIR, "sector_rotation.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def save_trade_summary(trades_df: pd.DataFrame):
    """保存交易汇总到Excel，包含多个sheet"""
    daily = summarize_trades(trades_df)
    out_path = os.path.join(config.OUTPUT_DIR, "trade_summary.xlsx")

    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        # Sheet 1: 日度汇总
        display_df = daily.copy()
        for col in ["buy_amount", "sell_amount", "dividend_amount", "net_amount"]:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"{x/1e4:.2f}" if pd.notna(x) else "")
        display_df.to_excel(writer, sheet_name="日度汇总", index=False)

        # Sheet 2: 红利明细
        dividend_df = trades_df[trades_df["direction"] == "dividend"].copy()
        if not dividend_df.empty:
            for col in ["quantity", "price", "amount"]:
                if col in dividend_df.columns:
                    dividend_df[col] = dividend_df[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")
            dividend_df.to_excel(writer, sheet_name="红利明细", index=False)

    return out_path
