"""
择时效果分析模块
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


def analyze_timing(trades_df: pd.DataFrame, index_df: pd.DataFrame) -> pd.DataFrame:
    """
    计算每次大幅加减仓后5/10/20日指数涨跌幅，统计胜率

    heavy_buy 定义: 日净买入金额 > 正净买入的75分位数
    heavy_sell 定义: 日净卖出金额 < 负净卖出的75分位数(绝对值)
    ret_5d 计算: (事件日后第5个交易日指数 / 事件日指数 - 1) * 100
    """
    from src.trade_analysis import summarize_trades
    daily = summarize_trades(trades_df)
    daily["date"] = pd.to_datetime(daily["date"])

    # 只取大幅加减仓信号
    signals = daily[daily["signal"].isin(["heavy_buy", "heavy_sell"])].copy()
    if signals.empty:
        return pd.DataFrame()

    idx = index_df.copy()
    idx.index = pd.to_datetime(idx.index)
    idx_vals = idx["reits_index"].dropna() if "reits_index" in idx.columns else pd.Series(dtype=float)

    records = []
    for _, row in signals.iterrows():
        t = row["date"]
        if t not in idx_vals.index:
            # 找最近的可用日期
            avail = idx_vals.index[idx_vals.index >= t]
            if avail.empty:
                continue
            t_actual = avail[0]
        else:
            t_actual = t

        v0 = idx_vals.get(t_actual, np.nan)
        if pd.isna(v0) or v0 == 0:
            continue

        rec = {
            "date": row["date"],
            "signal": row["signal"],
            "net_amount_wan": row["net_amount"] / 1e4,
        }
        for days in [5, 10, 20]:
            future_dates = idx_vals.index[idx_vals.index > t_actual]
            if len(future_dates) >= days:
                vf = idx_vals.iloc[idx_vals.index.get_loc(t_actual) + min(days, len(future_dates) - 1)]
                rec[f"ret_{days}d"] = (vf / v0 - 1) * 100
            else:
                rec[f"ret_{days}d"] = np.nan
        records.append(rec)

    if not records:
        return pd.DataFrame()

    result = pd.DataFrame(records)
    # 买入胜率：买入后指数上涨
    for days in [5, 10, 20]:
        col = f"ret_{days}d"
        if col in result.columns:
            buy_mask = result["signal"] == "heavy_buy"
            sell_mask = result["signal"] == "heavy_sell"
            buy_win = (result.loc[buy_mask, col] > 0).sum()
            buy_total = buy_mask.sum()
            sell_win = (result.loc[sell_mask, col] < 0).sum()
            sell_total = sell_mask.sum()
            result.attrs[f"buy_winrate_{days}d"] = buy_win / buy_total if buy_total > 0 else np.nan
            result.attrs[f"sell_winrate_{days}d"] = sell_win / sell_total if sell_total > 0 else np.nan

    return result


def plot_timing_chart(trades_df: pd.DataFrame, index_df: pd.DataFrame):
    """
    加减仓时点叠加指数走势图
    起始日=基准日
    """
    from src.trade_analysis import summarize_trades
    daily = summarize_trades(trades_df)
    daily["date"] = pd.to_datetime(daily["date"])

    # 以基准日为起点
    base_date = pd.to_datetime(config.BASE_DATE)
    daily = daily[daily["date"] >= base_date]

    idx = index_df.copy()
    idx.index = pd.to_datetime(idx.index)
    idx = idx[idx.index >= base_date]

    fig, ax = plt.subplots(figsize=(14, 6))

    if "reits_index" in idx.columns:
        idx_clean = idx["reits_index"].dropna()
        if not idx_clean.empty:
            ax.plot(idx_clean.index, idx_clean.values, color="#1f77b4",
                    linewidth=1.8, label="中证REITs指数", zorder=2)

    buy_sig = daily[daily["signal"] == "heavy_buy"]
    sell_sig = daily[daily["signal"] == "heavy_sell"]

    for _, row in buy_sig.iterrows():
        ax.axvline(x=row["date"], color="#d62728", alpha=0.5, linewidth=1.2, linestyle="--")
    for _, row in sell_sig.iterrows():
        ax.axvline(x=row["date"], color="#2ca02c", alpha=0.5, linewidth=1.2, linestyle="--")

    # 图例代理
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], color="#1f77b4", linewidth=1.8, label="中证REITs指数"),
        Line2D([0], [0], color="#d62728", linewidth=1.2, linestyle="--", label="大幅买入"),
        Line2D([0], [0], color="#2ca02c", linewidth=1.2, linestyle="--", label="大幅卖出"),
    ]
    ax.legend(handles=legend_elements, fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.xticks(rotation=30)
    ax.set_ylabel("中证REITs指数", fontsize=11)
    ax.set_title(f"加减仓时点 vs 指数走势（基准日：{base_date.strftime('%Y-%m-%d')}）", fontsize=13, fontweight="bold")
    ax.yaxis.grid(True, alpha=0.3)

    plt.tight_layout()
    out_path = os.path.join(config.OUTPUT_FIGURES_DIR, "timing_chart.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def save_timing_result(result: pd.DataFrame):
    """保存择时分析结果到Excel"""
    out_path = os.path.join(config.OUTPUT_DIR, "timing_analysis.xlsx")

    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        # Sheet 1: 明细
        if result is not None and not result.empty:
            display_df = result.copy()
            for col in ["net_amount_wan", "ret_5d", "ret_10d", "ret_20d"]:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")
            display_df.to_excel(writer, sheet_name="择时明细", index=False)

        # Sheet 2: 胜率统计
        if result is not None and hasattr(result, 'attrs'):
            stats = []
            for days in [5, 10, 20]:
                buy_key = f"buy_winrate_{days}d"
                sell_key = f"sell_winrate_{days}d"
                if buy_key in result.attrs:
                    stats.append({
                        "周期": f"{days}日",
                        "买入胜率": f"{result.attrs[buy_key]:.1%}" if pd.notna(result.attrs[buy_key]) else "N/A",
                        "卖出胜率": f"{result.attrs[sell_key]:.1%}" if pd.notna(result.attrs.get(sell_key)) else "N/A",
                    })
            if stats:
                pd.DataFrame(stats).to_excel(writer, sheet_name="胜率统计", index=False)

    return out_path
