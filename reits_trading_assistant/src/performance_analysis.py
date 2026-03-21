"""
业绩分析模块
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


def _max_drawdown(series: pd.Series) -> float:
    """计算最大回撤"""
    s = series.dropna()
    if s.empty:
        return np.nan
    roll_max = s.cummax()
    drawdown = (s - roll_max) / roll_max
    return float(drawdown.min())


def _annualized_return(series: pd.Series, trading_days: int = 252) -> float:
    s = series.dropna()
    if len(s) < 2:
        return np.nan
    total_ret = s.iloc[-1] / s.iloc[0] - 1
    n_days = (s.index[-1] - s.index[0]).days
    if n_days <= 0:
        return np.nan
    years = n_days / 365.0
    return float((1 + total_ret) ** (1 / years) - 1)


def _annualized_vol(series: pd.Series, trading_days: int = 252) -> float:
    s = series.dropna()
    if len(s) < 2:
        return np.nan
    daily_ret = s.pct_change().dropna()
    return float(daily_ret.std() * np.sqrt(trading_days))


def calc_metrics(nav_df: pd.DataFrame, index_df: pd.DataFrame, base_date=None) -> dict:
    """
    计算年化收益率、波动率、夏普比率、最大回撤、超额收益
    
    base_date: 基准日，如果提供则只计算基准日之后的数据（与分月表现口径一致）
    """
    nav = nav_df["nav"].dropna() if "nav" in nav_df.columns else pd.Series(dtype=float)
    idx = index_df["reits_index"].dropna() if "reits_index" in index_df.columns else pd.Series(dtype=float)
    
    # 如果提供了基准日，筛选数据（与分月表现口径一致）
    if base_date is not None:
        if not nav.empty:
            nav = nav[nav.index >= base_date]
        if not idx.empty:
            idx = idx[idx.index >= base_date]

    metrics = {}

    rf = 0.0185

    if not nav.empty and len(nav) > 1:
        nav_total_ret = nav.iloc[-1] / nav.iloc[0] - 1
        metrics["nav_total_return"] = nav_total_ret
        metrics["nav_ann_return"] = _annualized_return(nav)
        metrics["nav_ann_vol"] = _annualized_vol(nav)
        if metrics["nav_ann_vol"] and metrics["nav_ann_vol"] > 0:
            metrics["nav_sharpe"] = (metrics["nav_ann_return"] - rf) / metrics["nav_ann_vol"]
        else:
            metrics["nav_sharpe"] = np.nan
        metrics["nav_max_drawdown"] = _max_drawdown(nav)

    if not idx.empty and len(idx) > 1:
        idx_total_ret = idx.iloc[-1] / idx.iloc[0] - 1
        metrics["idx_total_return"] = idx_total_ret
        metrics["idx_ann_return"] = _annualized_return(idx)
        metrics["idx_ann_vol"] = _annualized_vol(idx)
        if metrics["idx_ann_vol"] and metrics["idx_ann_vol"] > 0:
            metrics["idx_sharpe"] = (metrics["idx_ann_return"] - rf) / metrics["idx_ann_vol"]
        else:
            metrics["idx_sharpe"] = np.nan
        metrics["idx_max_drawdown"] = _max_drawdown(idx)

    if "nav_ann_return" in metrics and "idx_ann_return" in metrics:
        metrics["excess_return"] = metrics["nav_ann_return"] - metrics["idx_ann_return"]

    # 绝对超额收益
    if "nav_total_return" in metrics and "idx_total_return" in metrics:
        metrics["excess_total"] = metrics["nav_total_return"] - metrics["idx_total_return"]

    if base_date is not None:
        metrics["base_date"] = base_date.strftime("%Y-%m-%d")

    return metrics


def calc_metrics_by_period(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    按自然月计算指标：基准日至今、各自然月
    逻辑：每月收益 = (本月末净值 / 上月末净值 - 1) * 100
    注：若上月末无数据，则用该月第一个交易日的净值
    """
    df = daily_df.copy()
    df.index = pd.to_datetime(df.index)
    base_date = pd.to_datetime(config.BASE_DATE)

    # 筛选基准日之后的数据
    df = df[df.index >= base_date].sort_index()

    results = []

    # 基准日至今
    nav_series = df["nav"].dropna() if "nav" in df.columns else pd.Series(dtype=float)
    idx_series = df["reits_index"].dropna() if "reits_index" in df.columns else pd.Series(dtype=float)

    if not nav_series.empty and len(nav_series) > 1:
        results.append({
            "period": f"{base_date.strftime('%Y-%m-%d')}至今",
            "start_date": nav_series.index[0].strftime('%Y-%m-%d'),
            "end_date": nav_series.index[-1].strftime('%Y-%m-%d'),
            "nav_return": (nav_series.iloc[-1] / nav_series.iloc[0] - 1) * 100,
            "idx_return": (idx_series.iloc[-1] / idx_series.iloc[0] - 1) * 100 if not idx_series.empty else np.nan,
            "excess": ((nav_series.iloc[-1] / nav_series.iloc[0]) - (idx_series.iloc[-1] / idx_series.iloc[0])) * 100 if not idx_series.empty else np.nan,
        })

    # 按自然月计算：用上个月最后一天的净值作为基准
    df["year_month"] = df.index.to_period("M")
    all_periods = sorted(df["year_month"].unique())

    # 获取每个period最后一天的数据点
    prev_nav_val = None
    prev_idx_val = None

    for i, ym in enumerate(all_periods):
        group = df[df["year_month"] == ym].sort_index()
        nav_m = group["nav"].dropna()
        idx_m = group["reits_index"].dropna()

        if not nav_m.empty:
            nav_end = nav_m.iloc[-1]  # 本月末净值
            nav_end_date = nav_m.index[-1]

            if i == 0 or prev_nav_val is None:
                # 第一个月：用该月第一个数据点作为起点（如果基准日在该月内）
                nav_start = nav_m.iloc[0]
                start_date = nav_m.index[0]
            else:
                # 非首月：用上月末净值作为起点
                nav_start = prev_nav_val
                start_date = nav_m.index[0]

            # 计算本月收益率
            nav_ret = (nav_end / nav_start - 1) * 100 if nav_start != 0 else np.nan

            # 指数同理
            idx_ret = np.nan
            if not idx_m.empty:
                idx_end = idx_m.iloc[-1]
                if i == 0 or prev_idx_val is None:
                    idx_start = idx_m.iloc[0]
                else:
                    idx_start = prev_idx_val
                idx_ret = (idx_end / idx_start - 1) * 100 if idx_start != 0 else np.nan

            results.append({
                "period": str(ym),
                "start_date": start_date.strftime('%Y-%m-%d'),
                "end_date": nav_end_date.strftime('%Y-%m-%d'),
                "nav_return": nav_ret,
                "idx_return": idx_ret,
                "excess": nav_ret - idx_ret if not np.isnan(idx_ret) else nav_ret,
            })

            # 保存本月末值给下月使用
            prev_nav_val = nav_end
            if not idx_m.empty:
                prev_idx_val = idx_m.iloc[-1]

    return pd.DataFrame(results)


def _apply_date_format(ax):
    """自动选择合适的日期间隔，格式标注到日"""
    locator = mdates.AutoDateLocator(minticks=6, maxticks=10)
    formatter = mdates.ConciseDateFormatter(locator)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)


def plot_nav_vs_index(daily_df: pd.DataFrame):
    """
    净值 vs 指数归一化对比图
    - 两条线对齐到共同起点（1.0）
    - 左轴：净值指数、指数
    - 右轴：超额（nav-index, %）
    """
    df = daily_df.copy()
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    base_date = pd.to_datetime(config.BASE_DATE)
    df = df[df.index >= base_date]

    if df.empty:
        return None

    # 找两条线共同有效的第一个日期，统一归一化到1.0（解决起点不对齐）
    if "nav_norm" in df.columns and "reits_index_norm" in df.columns:
        both = df[["nav_norm", "reits_index_norm"]].dropna()
        if not both.empty:
            start_nav = both["nav_norm"].iloc[0]
            start_idx = both["reits_index_norm"].iloc[0]
            df = df[df.index >= both.index[0]].copy()
            df["nav_norm"] = df["nav_norm"] / start_nav
            df["reits_index_norm"] = df["reits_index_norm"] / start_idx
            if "excess_pct" in df.columns:
                df["excess_pct"] = (df["nav_norm"] - df["reits_index_norm"]) * 100

    fig, ax1 = plt.subplots(figsize=(14, 6))

    plotted = False
    if "nav_norm" in df.columns:
        nav_clean = df["nav_norm"].dropna()
        if not nav_clean.empty:
            ax1.plot(nav_clean.index, nav_clean.values, color="#d62728",
                    linewidth=2, label=f"{config.ACCOUNT_NAME}净值", zorder=3)
            plotted = True

    if "reits_index_norm" in df.columns:
        idx_clean = df["reits_index_norm"].dropna()
        if not idx_clean.empty:
            ax1.plot(idx_clean.index, idx_clean.values, color="#1f77b4",
                    linewidth=1.8, linestyle="--", label="中证REITs指数(932006)", zorder=2)
            plotted = True

    if not plotted:
        plt.close(fig)
        return None

    ax1.axhline(1.0, color="gray", linewidth=0.8, linestyle=":", alpha=0.7)
    ax1.set_ylabel("归一化净值（起点=1）", fontsize=11, color="#333")
    ax1.set_xlabel("日期", fontsize=11)
    ax1.set_title(f"{config.ACCOUNT_NAME}净值 vs 中证REITs指数（基准日：{base_date.strftime('%Y-%m-%d')}）",
                  fontsize=13, fontweight="bold")
    ax1.tick_params(axis='y', labelcolor="#333")
    ax1.yaxis.grid(True, alpha=0.3)
    ax1.set_axisbelow(True)

    ax2 = ax1.twinx()
    if "nav_norm" in df.columns and "reits_index_norm" in df.columns:
        excess = (df["nav_norm"] - df["reits_index_norm"]) * 100
        excess_clean = excess.dropna()
        if not excess_clean.empty:
            color_excess = "#2ca02c"
            ax2.fill_between(excess_clean.index, 0, excess_clean.values,
                            where=(excess_clean >= 0), alpha=0.2, color=color_excess, label="超额收益")
            ax2.fill_between(excess_clean.index, 0, excess_clean.values,
                            where=(excess_clean < 0), alpha=0.2, color="#d62728")
            ax2.plot(excess_clean.index, excess_clean.values, color=color_excess,
                    linewidth=1, alpha=0.8, zorder=1)
            ax2.set_ylabel("超额收益（%）", fontsize=11, color=color_excess)
            ax2.tick_params(axis='y', labelcolor=color_excess)
            ax2.axhline(0, color=color_excess, linewidth=0.5, linestyle="-", alpha=0.5)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=10)

    _apply_date_format(ax1)
    plt.xticks(rotation=30)
    plt.tight_layout()
    out_path = os.path.join(config.OUTPUT_FIGURES_DIR, "nav_vs_index.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def save_performance_summary(metrics: dict, period_df: pd.DataFrame = None):
    """
    保存业绩汇总到Excel，包含多个sheet：
    - 总体指标（双列对比：明珠76号 vs 指数）
    - 分月指标（含起止日期说明）
    """
    out_path = os.path.join(config.OUTPUT_DIR, "performance_summary.xlsx")

    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        # Sheet 1: 总体指标（双列格式）
        rows = []

        # 区间总收益
        nav_total = metrics.get("nav_total_return")
        idx_total = metrics.get("idx_total_return")
        if nav_total is not None or idx_total is not None:
            rows.append({
                "指标": "区间总收益率",
                config.ACCOUNT_NAME: f"{nav_total*100:.2f}%" if nav_total is not None else "N/A",
                "指数": f"{idx_total*100:.2f}%" if idx_total is not None else "N/A",
            })

        # 年化收益率
        nav_ann = metrics.get("nav_ann_return")
        idx_ann = metrics.get("idx_ann_return")
        if nav_ann is not None or idx_ann is not None:
            rows.append({
                "指标": "年化收益率",
                config.ACCOUNT_NAME: f"{nav_ann*100:.2f}%" if nav_ann is not None else "N/A",
                "指数": f"{idx_ann*100:.2f}%" if idx_ann is not None else "N/A",
            })

        # 年化波动率
        nav_vol = metrics.get("nav_ann_vol")
        idx_vol = metrics.get("idx_ann_vol")
        if nav_vol is not None or idx_vol is not None:
            rows.append({
                "指标": "年化波动率",
                config.ACCOUNT_NAME: f"{nav_vol*100:.2f}%" if nav_vol is not None else "N/A",
                "指数": f"{idx_vol*100:.2f}%" if idx_vol is not None else "N/A",
            })

        nav_sharpe = metrics.get("nav_sharpe")
        idx_sharpe = metrics.get("idx_sharpe")
        if nav_sharpe is not None or idx_sharpe is not None:
            rows.append({
                "指标": "夏普比率(Rf=1.85%)",
                config.ACCOUNT_NAME: f"{nav_sharpe:.4f}" if nav_sharpe is not None else "N/A",
                "指数": f"{idx_sharpe:.4f}" if idx_sharpe is not None else "N/A",
            })

        # 最大回撤
        nav_dd = metrics.get("nav_max_drawdown")
        idx_dd = metrics.get("idx_max_drawdown")
        if nav_dd is not None or idx_dd is not None:
            rows.append({
                "指标": "最大回撤",
                config.ACCOUNT_NAME: f"{nav_dd*100:.2f}%" if nav_dd is not None else "N/A",
                "指数": f"{idx_dd*100:.2f}%" if idx_dd is not None else "N/A",
            })

        # 超额收益
        excess = metrics.get("excess_return")
        if excess is not None:
            rows.append({
                "指标": "超额年化收益率",
                config.ACCOUNT_NAME: f"{excess*100:.2f}%" if excess is not None else "N/A",
                "指数": "N/A",
            })

        # 基准日
        base_date = metrics.get("base_date")
        if base_date:
            rows.append({
                "指标": "计算基准日",
                config.ACCOUNT_NAME: base_date,
                "指数": base_date,
            })

        result_df = pd.DataFrame(rows)
        result_df.to_excel(writer, sheet_name="总体指标", index=False)

        # Sheet 2: 分月指标（含起止日期）
        if period_df is not None and not period_df.empty:
            display_df = period_df.copy()
            for col in ["nav_return", "idx_return", "excess"]:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "")
            # 重命名列更清晰
            col_rename = {
                "period": "期间",
                "start_date": "起始日",
                "end_date": "结束日",
                "nav_return": f"{config.ACCOUNT_NAME}收益",
                "idx_return": "指数收益",
                "excess": "超额收益",
            }
            display_df = display_df.rename(columns=col_rename)
            display_df.to_excel(writer, sheet_name="分月表现", index=False)

    return out_path


def save_daily_tracking(daily_df, holdings_daily=None, nav_df=None):
    """
    保存逐日跟踪表：基准日归一化账户净值、指数净值、仓位
    非交易日用前值填充，确保指数无断档
    """
    df = daily_df.copy()
    df.index = pd.to_datetime(df.index)
    base_date = pd.to_datetime(config.BASE_DATE)
    df = df[df.index >= base_date].sort_index()

    # 构建连续自然日索引，用前值填充非交易日
    full_idx = pd.date_range(start=df.index.min(), end=df.index.max(), freq="D")
    df = df.reindex(full_idx).ffill()

    tracking = pd.DataFrame(index=df.index)
    tracking.index.name = "日期"

    if "nav_norm" in df.columns:
        tracking["账户净值(归一)"] = df["nav_norm"]
    if "reits_index_norm" in df.columns:
        tracking["指数净值(归一)"] = df["reits_index_norm"]
    if "excess_pct" in df.columns:
        tracking["超额(%)"] = df["excess_pct"]

    if holdings_daily is not None and nav_df is not None and "net_assets" in nav_df.columns:
        hd = holdings_daily.copy()
        hd.index = pd.to_datetime(hd.index)
        na = nav_df[["net_assets"]].copy()
        na.index = pd.to_datetime(na.index)

        pos = pd.DataFrame(index=tracking.index)
        pos["market_value"] = hd["market_value"].reindex(pos.index).ffill()
        pos["net_assets"] = na["net_assets"].reindex(pos.index).ffill()
        pos["position_pct"] = pos["market_value"] / pos["net_assets"] * 100

        tracking["仓位(%)"] = pos["position_pct"]
        tracking["仓位变动(%)"] = tracking["仓位(%)"].diff()

    out_path = os.path.join(config.OUTPUT_DIR, "daily_tracking.xlsx")
    tracking.to_excel(out_path, engine='openpyxl')
    return tracking, out_path


def plot_position_change_vs_index(tracking_df, daily_df):
    """
    仓位变动 vs 指数走势图
    - 左轴：中证REITs指数归一化走势（加粗折线）
    - 右轴：仓位日变动（柱状图，加仓红色/减仓蓝色）
    """
    if tracking_df is None or "仓位变动(%)" not in tracking_df.columns:
        return None

    pos_chg = tracking_df["仓位变动(%)"].dropna()
    if pos_chg.empty:
        return None

    base_date = pd.to_datetime(config.BASE_DATE)

    fig, ax1 = plt.subplots(figsize=(14, 6))

    df = daily_df.copy()
    df.index = pd.to_datetime(df.index)
    df = df[df.index >= base_date]

    if "reits_index_norm" in df.columns:
        idx_clean = df["reits_index_norm"].dropna()
        if not idx_clean.empty:
            ax1.plot(idx_clean.index, idx_clean.values,
                     color="#1a1a1a", linewidth=2.5, label="中证REITs指数(归一)", zorder=5)
    ax1.set_ylabel("指数（归一化）", fontsize=11, color="#1a1a1a")
    ax1.tick_params(axis='y', labelcolor="#1a1a1a")
    ax1.yaxis.grid(True, alpha=0.3)
    ax1.set_axisbelow(True)

    ax2 = ax1.twinx()
    colors = ["#d62728" if v > 0 else "#1f77b4" for v in pos_chg.values]
    ax2.bar(pos_chg.index, pos_chg.values, color=colors, alpha=0.6, width=1, zorder=3)
    ax2.set_ylabel("仓位变动(%)", fontsize=11, color="#666")
    ax2.tick_params(axis='y', labelcolor="#666")
    ax2.axhline(0, color="gray", linewidth=0.5, linestyle="-", zorder=2)

    from matplotlib.patches import Patch
    lines1, labels1 = ax1.get_legend_handles_labels()
    legend_patches = [Patch(facecolor="#d62728", alpha=0.6, label="加仓"),
                      Patch(facecolor="#1f77b4", alpha=0.6, label="减仓")]
    ax1.legend(lines1 + legend_patches, labels1 + ["加仓", "减仓"],
               loc="upper left", fontsize=9)

    _apply_date_format(ax1)
    plt.xticks(rotation=30)
    ax1.set_title(f"仓位变动 vs 中证REITs指数（基准日：{base_date.strftime('%Y-%m-%d')}）",
                  fontsize=13, fontweight="bold")

    plt.tight_layout()
    out_path = os.path.join(config.OUTPUT_FIGURES_DIR, "position_change_vs_index.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
