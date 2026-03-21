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


def _apply_date_format(ax):
    """自动选择合适的日期间隔，格式标注到日"""
    locator = mdates.AutoDateLocator(minticks=6, maxticks=10)
    formatter = mdates.ConciseDateFormatter(locator)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)


def summarize_trades(trades_df: pd.DataFrame, holdings_daily: pd.DataFrame = None, net_assets: pd.DataFrame = None) -> pd.DataFrame:
    """
    按日汇总净买入（买入-卖出），识别大幅加减仓

    参数:
        trades_df: 交易明细
        holdings_daily: 日频持仓市值(可选)，用于计算仓位
        net_assets: 日频净资产(可选)，用于计算仓位比例
    """
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

    # 如果有持仓和净资产数据，计算仓位
    if holdings_daily is not None:
        holdings_daily = holdings_daily.copy()
        holdings_daily.index = pd.to_datetime(holdings_daily.index)
        daily["position_mv"] = daily["date"].map(lambda x: holdings_daily.loc[x, "market_value"] if x in holdings_daily.index else np.nan)

    if net_assets is not None:
        net_assets = net_assets.copy()
        net_assets.index = pd.to_datetime(net_assets.index)
        daily["net_assets"] = daily["date"].map(lambda x: net_assets.loc[x, "net_assets"] if x in net_assets.index else np.nan)

    # 计算仓位比例 (持仓市值/净资产)
    if "position_mv" in daily.columns and "net_assets" in daily.columns:
        daily["position_pct"] = daily["position_mv"] / daily["net_assets"]
    else:
        daily["position_pct"] = np.nan

    # 仓位变动
    if daily["position_pct"].notna().any():
        daily["position_change"] = daily["position_pct"].diff()
    else:
        daily["position_change"] = np.nan

    # heavy_buy定义: 净买入 > 正净买入的75分位数 (与负净卖出独立计算)
    # heavy_sell定义: 净卖出绝对值 > 负净卖出的75分位数绝对值
    buy_threshold = daily[daily["net_amount"] > 0]["net_amount"].quantile(0.75) if (daily["net_amount"] > 0).any() else 0
    sell_threshold = -daily[daily["net_amount"] < 0]["net_amount"].quantile(0.75) if (daily["net_amount"] < 0).any() else 0

    daily["signal"] = "neutral"
    daily.loc[daily["net_amount"] > buy_threshold, "signal"] = "heavy_buy"
    daily.loc[daily["net_amount"] < sell_threshold, "signal"] = "heavy_sell"

    # 添加阈值到attrs供参考
    daily.attrs["buy_threshold"] = buy_threshold
    daily.attrs["sell_threshold"] = sell_threshold
    return daily.sort_values("date").reset_index(drop=True)


def plot_trade_flow(trades_df: pd.DataFrame, index_df: pd.DataFrame):
    """
    资金流向图
    - 左轴：中证REITs指数（加粗折线，强对比度）
    - 右轴：日交易金额，买入为正（红色），卖出为负（蓝色）
    """
    daily = summarize_trades(trades_df)
    daily["date"] = pd.to_datetime(daily["date"])
    base_date = pd.to_datetime(config.BASE_DATE)
    daily_filtered = daily[daily["date"] >= base_date].copy()

    if daily_filtered.empty:
        return None

    idx = index_df.copy()
    idx.index = pd.to_datetime(idx.index)
    idx_filtered = idx[idx.index >= base_date]

    fig, ax1 = plt.subplots(figsize=(14, 7))

    # 左轴：指数走势（加粗折线，强对比度）
    if "reits_index" in idx_filtered.columns and not idx_filtered["reits_index"].dropna().empty:
        idx_clean = idx_filtered["reits_index"].dropna()
        ax1.plot(idx_clean.index, idx_clean.values,
                 color="#1a1a1a", linewidth=2.5, label="中证REITs指数", zorder=5)
        ax1.set_ylabel("中证REITs指数", fontsize=11, color="#1a1a1a")
        ax1.tick_params(axis='y', labelcolor="#1a1a1a")
        idx_min, idx_max = idx_clean.min(), idx_clean.max()
        idx_range = idx_max - idx_min
        ax1.set_ylim(idx_min - idx_range * 0.1, idx_max + idx_range * 0.1)

    ax1.yaxis.grid(True, alpha=0.3)
    ax1.set_axisbelow(True)

    # 右轴：买入卖出金额
    ax2 = ax1.twinx()
    buy_data = daily_filtered[daily_filtered["buy_amount"] > 0]
    ax2.bar(buy_data["date"], buy_data["buy_amount"] / 1e4,
            color="#d62728", alpha=0.6, width=1, label="买入", zorder=3)

    sell_data = daily_filtered[daily_filtered["sell_amount"] > 0]
    ax2.bar(sell_data["date"], -sell_data["sell_amount"] / 1e4,
            color="#1f77b4", alpha=0.6, width=1, label="卖出", zorder=3)

    ax2.axhline(0, color="gray", linewidth=0.5, linestyle="-", zorder=2)
    ax2.set_ylabel("日交易金额（万元）买入+/卖出-", fontsize=11, color="#666")
    max_val = max(
        daily_filtered["buy_amount"].max() / 1e4 if not daily_filtered["buy_amount"].empty else 0,
        daily_filtered["sell_amount"].max() / 1e4 if not daily_filtered["sell_amount"].empty else 0,
    )
    if max_val > 0:
        ax2.set_ylim(-max_val * 1.3, max_val * 1.3)
    ax2.tick_params(axis='y', labelcolor="#666")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9, ncol=2)

    _apply_date_format(ax1)
    plt.xticks(rotation=30)
    ax1.set_title(f"资金流向与指数走势（基准日：{base_date.strftime('%Y-%m-%d')}）",
                  fontsize=13, fontweight="bold")

    plt.tight_layout()
    out_path = os.path.join(config.OUTPUT_FIGURES_DIR, "trade_flow.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_net_buy_vs_index(trades_df: pd.DataFrame, index_df: pd.DataFrame):
    """
    净买入 vs 指数走势图
    - 左轴：中证REITs指数（加粗折线，强对比度）
    - 右轴：日净买入金额（柱状图，正=净买入红色，负=净卖出蓝色）
    """
    daily = summarize_trades(trades_df)
    daily["date"] = pd.to_datetime(daily["date"])
    base_date = pd.to_datetime(config.BASE_DATE)
    daily_filtered = daily[daily["date"] >= base_date].copy()

    if daily_filtered.empty:
        return None

    idx = index_df.copy()
    idx.index = pd.to_datetime(idx.index)
    idx_filtered = idx[idx.index >= base_date]

    fig, ax1 = plt.subplots(figsize=(14, 7))

    if "reits_index" in idx_filtered.columns and not idx_filtered["reits_index"].dropna().empty:
        idx_clean = idx_filtered["reits_index"].dropna()
        ax1.plot(idx_clean.index, idx_clean.values,
                 color="#1a1a1a", linewidth=2.5, label="中证REITs指数", zorder=5)
        ax1.set_ylabel("中证REITs指数", fontsize=11, color="#1a1a1a")
        ax1.tick_params(axis='y', labelcolor="#1a1a1a")
        idx_min, idx_max = idx_clean.min(), idx_clean.max()
        idx_range = idx_max - idx_min
        ax1.set_ylim(idx_min - idx_range * 0.1, idx_max + idx_range * 0.1)

    ax1.yaxis.grid(True, alpha=0.3)
    ax1.set_axisbelow(True)

    ax2 = ax1.twinx()
    net = daily_filtered["net_amount"] / 1e4
    colors = ["#d62728" if v >= 0 else "#1f77b4" for v in net.values]
    ax2.bar(daily_filtered["date"], net.values, color=colors, alpha=0.6, width=1, zorder=3)
    ax2.axhline(0, color="gray", linewidth=0.5, linestyle="-", zorder=2)
    ax2.set_ylabel("日净买入（万元）", fontsize=11, color="#666")
    ax2.tick_params(axis='y', labelcolor="#666")
    net_abs_max = net.abs().max()
    if net_abs_max > 0:
        ax2.set_ylim(-net_abs_max * 1.3, net_abs_max * 1.3)

    from matplotlib.patches import Patch
    lines1, labels1 = ax1.get_legend_handles_labels()
    legend_patches = [Patch(facecolor="#d62728", alpha=0.6, label="净买入"),
                      Patch(facecolor="#1f77b4", alpha=0.6, label="净卖出")]
    ax1.legend(lines1 + legend_patches, labels1 + ["净买入", "净卖出"],
               loc="upper left", fontsize=9, ncol=2)

    _apply_date_format(ax1)
    plt.xticks(rotation=30)
    ax1.set_title(f"净买入与指数走势（基准日：{base_date.strftime('%Y-%m-%d')}）",
                  fontsize=13, fontweight="bold")

    plt.tight_layout()
    out_path = os.path.join(config.OUTPUT_FIGURES_DIR, "net_buy_vs_index.png")
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


def plot_position_vs_index(daily_df: pd.DataFrame, index_df: pd.DataFrame):
    """
    仓位比例 vs 指数走势图（面积图）
    - 左轴：仓位比例(%) — fill_between 面积图
    - 右轴：中证REITs指数
    - 打印每日计算过程；单日变动>10%标注异常值，控制台确认是否采纳
    """
    if daily_df is None or "position_pct" not in daily_df.columns or daily_df["position_pct"].isna().all():
        return None

    daily = daily_df.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    base_date = pd.to_datetime(config.BASE_DATE)
    daily_filtered = daily[daily["date"] >= base_date].copy().sort_values("date")

    if daily_filtered.empty:
        return None

    # ── 打印仓位计算过程 ──
    print("\n📊 仓位计算过程：")
    print(f"{'日期':<12} {'持仓市值(万)':>12} {'净资产(万)':>12} {'仓位(%)':>8} {'变动(ppt)':>10}")
    print("-" * 60)
    prev_pct = None
    for _, row in daily_filtered.iterrows():
        pct = row["position_pct"] * 100 if pd.notna(row["position_pct"]) else float("nan")
        mv = row["position_mv"] / 1e4 if "position_mv" in row and pd.notna(row.get("position_mv")) else float("nan")
        na = row["net_assets"] / 1e4 if "net_assets" in row and pd.notna(row.get("net_assets")) else float("nan")
        chg = (pct - prev_pct) if prev_pct is not None and pd.notna(pct) else float("nan")
        flag = " ⚠️" if abs(chg) > 10 else ""
        print(f"{str(row['date'].date()):<12} {mv:>12.1f} {na:>12.1f} {pct:>8.2f} {chg:>+10.2f}{flag}")
        prev_pct = pct if pd.notna(pct) else prev_pct

    # ── 检测单日变动>10%的异常点 ──
    pos_series = daily_filtered["position_pct"].copy()
    pos_chg = pos_series.diff()
    anomaly_mask = pos_chg.abs() > 0.10
    anomaly_dates = daily_filtered.loc[anomaly_mask.values, "date"].tolist()

    excluded_dates = set()
    if anomaly_dates:
        print(f"\n⚠️  检测到 {len(anomaly_dates)} 个仓位单日变动超过10%的异常点：")
        for d in anomaly_dates:
            idx_pos = daily_filtered[daily_filtered["date"] == d].index[0]
            chg_val = pos_chg.loc[idx_pos] * 100
            pct_val = pos_series.loc[idx_pos] * 100
            print(f"  {d.date()}: 仓位={pct_val:.1f}%, 变动={chg_val:+.1f}ppt")
        try:
            ans = input("\n是否排除以上异常点？[y=排除 / n=保留，默认保留] ").strip().lower()
        except EOFError:
            ans = ""
            print("  (非交互模式，默认保留)")
        if ans == "y":
            excluded_dates = set(d.date() for d in anomaly_dates)
            print(f"  已排除 {len(excluded_dates)} 个异常点")
        else:
            print("  保留所有数据点")

    # 过滤异常点（如用户选择排除）
    if excluded_dates:
        daily_filtered = daily_filtered[~daily_filtered["date"].dt.date.isin(excluded_dates)].copy()

    # ── 准备指数数据 ──
    idx = index_df.copy()
    idx.index = pd.to_datetime(idx.index)
    idx_filtered = idx[idx.index >= base_date]

    fig, ax1 = plt.subplots(figsize=(14, 6))

    # 左轴：仓位比例 — 面积图
    dates = daily_filtered["date"].values
    pos_pct = daily_filtered["position_pct"].values * 100
    ax1.fill_between(dates, 0, pos_pct, alpha=0.35, color="#1f77b4", label="仓位比例(%)", zorder=3)
    ax1.plot(dates, pos_pct, color="#1f77b4", linewidth=1.5, zorder=4)
    ax1.set_ylabel("仓位比例(%)", fontsize=11, color="#1f77b4")
    y_max = max(120, float(np.nanmax(pos_pct)) * 1.1) if len(pos_pct) > 0 else 120
    ax1.set_ylim(0, y_max)
    ax1.tick_params(axis='y', labelcolor="#1f77b4")
    ax1.axhline(100, color="gray", linestyle="--", linewidth=1, alpha=0.6, label="满仓(100%)")
    ax1.yaxis.grid(True, alpha=0.3)
    ax1.set_axisbelow(True)

    # 标注未被排除的异常点
    remaining_anomaly = [d for d in anomaly_dates if d.date() not in excluded_dates]
    for d in remaining_anomaly:
        row = daily_filtered[daily_filtered["date"] == d]
        if not row.empty:
            pct_v = row["position_pct"].iloc[0] * 100
            ax1.annotate(f"异常{pct_v:.0f}%",
                        xy=(d, pct_v), xytext=(0, 12),
                        textcoords="offset points",
                        fontsize=8, color="#d62728",
                        arrowprops=dict(arrowstyle="-", color="#d62728", lw=0.8))

    # 右轴：指数
    ax2 = ax1.twinx()
    if "reits_index" in idx_filtered.columns:
        idx_clean = idx_filtered["reits_index"].dropna()
        if not idx_clean.empty:
            ax2.plot(idx_clean.index, idx_clean.values,
                     color="#ff7f0e", linewidth=1.8, label="中证REITs指数", zorder=2)
            ax2.set_ylabel("中证REITs指数", fontsize=11, color="#ff7f0e")
            ax2.tick_params(axis='y', labelcolor="#ff7f0e")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels() if "reits_index" in idx_filtered.columns else ([], [])
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9)

    _apply_date_format(ax1)
    plt.xticks(rotation=30)
    ax1.set_title(f"仓位比例 vs 中证REITs指数（基准日：{base_date.strftime('%Y-%m-%d')}）",
                  fontsize=13, fontweight="bold")

    plt.tight_layout()
    out_path = os.path.join(config.OUTPUT_FIGURES_DIR, "position_vs_index.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def save_trade_summary(trades_df: pd.DataFrame, holdings_daily: pd.DataFrame = None, net_assets: pd.DataFrame = None):
    """保存交易汇总到Excel，包含多个sheet"""
    daily = summarize_trades(trades_df, holdings_daily, net_assets)
    out_path = os.path.join(config.OUTPUT_DIR, "trade_summary.xlsx")

    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        # Sheet 1: 日度汇总
        display_df = daily.copy()
        for col in ["buy_amount", "sell_amount", "dividend_amount", "net_amount"]:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"{x/1e4:.2f}" if pd.notna(x) else "")
        # 仓位比例格式化
        if "position_pct" in display_df.columns:
            display_df["仓位(%)"] = display_df["position_pct"].apply(lambda x: f"{x*100:.2f}" if pd.notna(x) else "")
            display_df = display_df.drop(columns=["position_pct"])
        if "position_change" in display_df.columns:
            display_df["仓位变动(%)"] = display_df["position_change"].apply(lambda x: f"{x*100:+.2f}" if pd.notna(x) else "")
            display_df = display_df.drop(columns=["position_change"])
        if "position_mv" in display_df.columns:
            display_df["持仓市值(万)"] = display_df["position_mv"].apply(lambda x: f"{x/1e4:.2f}" if pd.notna(x) else "")
            display_df = display_df.drop(columns=["position_mv"])
        if "net_assets" in display_df.columns:
            display_df["净资产(万)"] = display_df["net_assets"].apply(lambda x: f"{x/1e4:.2f}" if pd.notna(x) else "")
            display_df = display_df.drop(columns=["net_assets"])

        # 按日期降序排列，方便查看最新
        display_df = display_df.sort_values("date", ascending=False)
        display_df.to_excel(writer, sheet_name="日度汇总", index=False)

        # Sheet 2: 总结（含阈值说明）
        summary_rows = []
        if hasattr(daily, 'attrs'):
            if "buy_threshold" in daily.attrs:
                summary_rows.append({"项目": "heavy_buy阈值", "数值": f"{daily.attrs['buy_threshold']/1e4:.1f}万", "说明": "日净买入大于75分位数"})
            if "sell_threshold" in daily.attrs:
                summary_rows.append({"项目": "heavy_sell阈值", "数值": f"{daily.attrs['sell_threshold']/1e4:.1f}万", "说明": "日净卖出小于75分位数"})

        summary_rows.append({"项目": "交易记录数", "数值": len(trades_df), "说明": "含买入/卖出/红利"})
        summary_rows.append({"项目": "交易日期数", "数值": daily["date"].nunique(), "说明": "有交易发生的天数"})
        summary_rows.append({"项目": "heavy_buy天数", "数值": len(daily[daily["signal"]=="heavy_buy"]), "说明": ""})
        summary_rows.append({"项目": "heavy_sell天数", "数值": len(daily[daily["signal"]=="heavy_sell"]), "说明": ""})
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="总结", index=False)

        # Sheet 3: 红利明细
        dividend_df = trades_df[trades_df["direction"] == "dividend"].copy()
        if not dividend_df.empty:
            for col in ["quantity", "price", "amount"]:
                if col in dividend_df.columns:
                    dividend_df[col] = dividend_df[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")
            dividend_df.to_excel(writer, sheet_name="红利明细", index=False)

    return out_path
