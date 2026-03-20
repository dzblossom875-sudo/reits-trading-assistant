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


def calc_metrics(nav_df: pd.DataFrame, index_df: pd.DataFrame) -> dict:
    """计算年化收益率、波动率、夏普比率、最大回撤、超额收益"""
    nav = nav_df["nav"].dropna() if "nav" in nav_df.columns else pd.Series(dtype=float)
    idx = index_df["reits_index"].dropna() if "reits_index" in index_df.columns else pd.Series(dtype=float)

    metrics = {}

    if not nav.empty:
        metrics["nav_ann_return"] = _annualized_return(nav)
        metrics["nav_ann_vol"] = _annualized_vol(nav)
        rf = 0.02  # 无风险利率近似
        if metrics["nav_ann_vol"] and metrics["nav_ann_vol"] > 0:
            metrics["nav_sharpe"] = (metrics["nav_ann_return"] - rf) / metrics["nav_ann_vol"]
        else:
            metrics["nav_sharpe"] = np.nan
        metrics["nav_max_drawdown"] = _max_drawdown(nav)

    if not idx.empty:
        metrics["idx_ann_return"] = _annualized_return(idx)
        metrics["idx_ann_vol"] = _annualized_vol(idx)
        metrics["idx_max_drawdown"] = _max_drawdown(idx)

    if "nav_ann_return" in metrics and "idx_ann_return" in metrics:
        metrics["excess_return"] = metrics["nav_ann_return"] - metrics["idx_ann_return"]

    return metrics


def calc_metrics_by_period(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    按自然月计算指标：基准日至今、各自然月
    返回DataFrame包含各期指标
    """
    df = daily_df.copy()
    df.index = pd.to_datetime(df.index)
    base_date = pd.to_datetime(config.BASE_DATE)

    # 筛选基准日之后的数据
    df = df[df.index >= base_date]

    results = []

    # 基准日至今
    nav_series = df["nav"].dropna() if "nav" in df.columns else pd.Series(dtype=float)
    idx_series = df["reits_index"].dropna() if "reits_index" in df.columns else pd.Series(dtype=float)

    if not nav_series.empty:
        results.append({
            "period": f"{base_date.strftime('%Y-%m-%d')}至今",
            "nav_return": (nav_series.iloc[-1] / nav_series.iloc[0] - 1) * 100 if len(nav_series) > 1 else np.nan,
            "idx_return": (idx_series.iloc[-1] / idx_series.iloc[0] - 1) * 100 if len(idx_series) > 1 else np.nan,
            "excess": ((nav_series.iloc[-1] / nav_series.iloc[0]) - (idx_series.iloc[-1] / idx_series.iloc[0])) * 100 if len(nav_series) > 1 else np.nan,
        })

    # 按自然月计算
    df["year_month"] = df.index.to_period("M")
    for ym, group in df.groupby("year_month"):
        nav_m = group["nav"].dropna() if "nav" in group.columns else pd.Series(dtype=float)
        idx_m = group["reits_index"].dropna() if "reits_index" in group.columns else pd.Series(dtype=float)
        if not nav_m.empty and len(nav_m) > 1:
            results.append({
                "period": str(ym),
                "nav_return": (nav_m.iloc[-1] / nav_m.iloc[0] - 1) * 100,
                "idx_return": (idx_m.iloc[-1] / idx_m.iloc[0] - 1) * 100 if not idx_m.empty else np.nan,
                "excess": ((nav_m.iloc[-1] / nav_m.iloc[0]) - (idx_m.iloc[-1] / idx_m.iloc[0])) * 100 if not idx_m.empty else np.nan,
            })

    return pd.DataFrame(results)


def plot_nav_vs_index(daily_df: pd.DataFrame):
    """
    净值 vs 指数归一化对比图
    - 基准日归一化
    - 左轴：净值指数、指数
    - 右轴：超额（nav-index, %）
    - 起始日=基准日
    """
    df = daily_df.copy()
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    # 以基准日为起点
    base_date = pd.to_datetime(config.BASE_DATE)
    df = df[df.index >= base_date]

    if df.empty:
        return None

    fig, ax1 = plt.subplots(figsize=(14, 6))

    # 左轴：归一化净值和指数
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
    ax1.set_ylabel("归一化净值（基准=1）", fontsize=11, color="#333")
    ax1.set_xlabel("日期", fontsize=11)
    ax1.set_title(f"{config.ACCOUNT_NAME}净值 vs 中证REITs指数（基准日：{base_date.strftime('%Y-%m-%d')}）",
                  fontsize=13, fontweight="bold")
    ax1.tick_params(axis='y', labelcolor="#333")
    ax1.yaxis.grid(True, alpha=0.3)
    ax1.set_axisbelow(True)

    # 右轴：超额收益
    ax2 = ax1.twinx()
    if "nav_norm" in df.columns and "reits_index_norm" in df.columns:
        excess = (df["nav_norm"] - df["reits_index_norm"]) * 100  # 转为百分比
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

    # 合并图例
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=10)

    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.xticks(rotation=30)
    plt.tight_layout()
    out_path = os.path.join(config.OUTPUT_FIGURES_DIR, "nav_vs_index.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def save_performance_summary(metrics: dict, period_df: pd.DataFrame = None):
    """
    保存业绩汇总到Excel，包含多个sheet：
    - 总体指标
    - 分月指标
    """
    out_path = os.path.join(config.OUTPUT_DIR, "performance_summary.xlsx")

    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        # Sheet 1: 总体指标
        rows = []
        label_map = {
            "nav_ann_return": f"{config.ACCOUNT_NAME}年化收益率",
            "nav_ann_vol": f"{config.ACCOUNT_NAME}年化波动率",
            "nav_sharpe": f"{config.ACCOUNT_NAME}夏普比率",
            "nav_max_drawdown": f"{config.ACCOUNT_NAME}最大回撤",
            "idx_ann_return": "指数年化收益率",
            "idx_ann_vol": "指数年化波动率",
            "idx_max_drawdown": "指数最大回撤",
            "excess_return": "超额年化收益率",
        }
        for k, v in metrics.items():
            label = label_map.get(k, k)
            if isinstance(v, float) and not np.isnan(v):
                if "return" in k or "vol" in k or "drawdown" in k or "excess" in k:
                    display = f"{v * 100:.2f}%"
                else:
                    display = f"{v:.4f}"
            else:
                display = str(v)
            rows.append({"指标": label, "数值": display})

        result_df = pd.DataFrame(rows)
        result_df.to_excel(writer, sheet_name="总体指标", index=False)

        # Sheet 2: 分月指标
        if period_df is not None and not period_df.empty:
            display_df = period_df.copy()
            for col in ["nav_return", "idx_return", "excess"]:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "")
            display_df.to_excel(writer, sheet_name="分月表现", index=False)

    return out_path
