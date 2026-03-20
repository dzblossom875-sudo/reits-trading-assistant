"""
报告生成模块
v2 - 直接接收分析数据，不再依赖中间 CSV 文件
"""
import os
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def generate_report(date_str=None, **kwargs):
    """
    生成 Markdown 分析报告

    优先使用 kwargs 传入的内存数据，避免读格式化后的 xlsx 字符串。

    kwargs:
        metrics        : dict       - calc_metrics() 返回的业绩指标
        period_df      : DataFrame  - calc_metrics_by_period() 分月表现
        trades_df      : DataFrame  - 原始交易明细 (含 sector)
        daily_trades   : DataFrame  - summarize_trades() 日度汇总
        timing_result  : DataFrame  - analyze_timing() 择时结果
        bias_sector    : DataFrame  - calc_sector_allocation_bias() 板块偏移
    """
    if date_str is None:
        from datetime import date
        date_str = date.today().strftime("%Y%m%d")

    metrics = kwargs.get("metrics", {})
    period_df = kwargs.get("period_df")
    trades_df = kwargs.get("trades_df")
    daily_trades = kwargs.get("daily_trades")
    timing_result = kwargs.get("timing_result")
    bias_sector = kwargs.get("bias_sector")

    account_name = config.ACCOUNT_NAME

    if len(date_str) >= 8 and date_str[:8].replace("_", "").isdigit():
        display_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    else:
        display_date = date_str

    def _fmt_pct(v):
        if v is None:
            return "N/A"
        if isinstance(v, float) and np.isnan(v):
            return "N/A"
        return f"{v * 100:.2f}%"

    def _fmt_num(v, decimals=4):
        if v is None:
            return "N/A"
        if isinstance(v, float) and np.isnan(v):
            return "N/A"
        return f"{v:.{decimals}f}"

    lines = []

    # ── 标题 ──
    lines.append(f"# {account_name} REITs 交易分析报告")
    lines.append("")
    lines.append(f"**报告日期**: {display_date}")
    lines.append(f"**基准日期**: {config.BASE_DATE}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 1. 核心结论 ──
    lines.append("## 1. 核心结论")
    lines.append("")
    if metrics:
        nav_total = metrics.get("nav_total_return")
        nav_ann = metrics.get("nav_ann_return")
        excess = metrics.get("excess_return")
        if nav_total is not None:
            lines.append(f"- {account_name}区间总收益率：{_fmt_pct(nav_total)}")
        if nav_ann is not None:
            lines.append(f"- {account_name}年化收益率：{_fmt_pct(nav_ann)}")
        if excess is not None:
            lines.append(f"- 相对中证REITs指数超额年化收益：{_fmt_pct(excess)}")

    if trades_df is not None and not trades_df.empty and "direction" in trades_df.columns:
        amounts = pd.to_numeric(trades_df.get("amount", pd.Series(dtype=float)), errors="coerce").fillna(0)
        buy_total = amounts[trades_df["direction"] == "buy"].sum()
        sell_total = amounts[trades_df["direction"] == "sell"].sum()
        div_total = amounts[trades_df["direction"] == "dividend"].sum()
        lines.append(f"- 累计买入：{buy_total / 1e4:.2f} 万元，卖出：{sell_total / 1e4:.2f} 万元")
        if div_total > 0:
            lines.append(f"- 红利到账：{div_total / 1e4:.2f} 万元")
    lines.append("")

    # ── 2. 账户表现 ──
    lines.append("## 2. 账户表现")
    lines.append("")
    if metrics:
        lines.append(f"| 指标 | {account_name} | 指数 |")
        lines.append("|------|------|------|")
        perf_rows = [
            ("区间总收益率", _fmt_pct(metrics.get("nav_total_return")), _fmt_pct(metrics.get("idx_total_return"))),
            ("年化收益率", _fmt_pct(metrics.get("nav_ann_return")), _fmt_pct(metrics.get("idx_ann_return"))),
            ("年化波动率", _fmt_pct(metrics.get("nav_ann_vol")), _fmt_pct(metrics.get("idx_ann_vol"))),
            ("夏普比率(Rf=1.85%)", _fmt_num(metrics.get("nav_sharpe")), _fmt_num(metrics.get("idx_sharpe"))),
            ("最大回撤", _fmt_pct(metrics.get("nav_max_drawdown")), _fmt_pct(metrics.get("idx_max_drawdown"))),
            ("超额年化收益率", _fmt_pct(metrics.get("excess_return")), "N/A"),
        ]
        for label, nav_val, idx_val in perf_rows:
            lines.append(f"| {label} | {nav_val} | {idx_val} |")
    else:
        lines.append("（暂无业绩数据）")
    lines.append("")

    # ── 2.1 分月表现 ──
    if period_df is not None and not period_df.empty:
        lines.append("### 分月表现")
        lines.append("")
        lines.append(f"| 期间 | 起始日 | 结束日 | {account_name}收益 | 指数收益 | 超额收益 |")
        lines.append("|------|--------|--------|------|------|------|")
        for _, row in period_df.iterrows():
            nav_r = f"{row['nav_return']:.2f}%" if pd.notna(row.get("nav_return")) else ""
            idx_r = f"{row['idx_return']:.2f}%" if pd.notna(row.get("idx_return")) else ""
            exc = f"{row['excess']:.2f}%" if pd.notna(row.get("excess")) else ""
            lines.append(
                f"| {row.get('period', '')} | {row.get('start_date', '')} "
                f"| {row.get('end_date', '')} | {nav_r} | {idx_r} | {exc} |"
            )
        lines.append("")

    # ── 3. 配置偏移 ──
    lines.append("## 3. 配置偏移分析")
    lines.append("")
    if bias_sector is not None and not bias_sector.empty:
        lines.append("| 板块 | 账户权重 | 指数权重 | 偏移 |")
        lines.append("|------|----------|----------|------|")
        for _, row in bias_sector.iterrows():
            lines.append(
                f"| {row.get('sector', '')} "
                f"| {row.get('account_weight', 0):.2%} "
                f"| {row.get('index_weight', 0):.2%} "
                f"| {row.get('weight_bias', 0):+.2%} |"
            )
    else:
        lines.append("（暂无配置偏移数据）")
    lines.append("")

    # ── 4. 交易行为复盘 ──
    lines.append("## 4. 交易行为复盘")
    lines.append("")
    if daily_trades is not None and not daily_trades.empty:
        lines.append(f"- 交易日总数：{len(daily_trades)} 天")
        if "signal" in daily_trades.columns:
            hb = len(daily_trades[daily_trades["signal"] == "heavy_buy"])
            hs = len(daily_trades[daily_trades["signal"] == "heavy_sell"])
            if hb > 0:
                lines.append(f"- 大幅加仓日：{hb} 天")
            if hs > 0:
                lines.append(f"- 大幅减仓日：{hs} 天")
    elif trades_df is not None and not trades_df.empty:
        lines.append(f"- 交易记录总数：{len(trades_df)} 笔")
    else:
        lines.append("（暂无交易数据）")

    if trades_df is not None and not trades_df.empty and "sector" in trades_df.columns:
        amounts = pd.to_numeric(trades_df.get("amount", pd.Series(dtype=float)), errors="coerce").fillna(0)
        trades_tmp = trades_df.assign(amount_num=amounts)
        buy_s = trades_tmp.loc[trades_tmp["direction"] == "buy"].groupby("sector")["amount_num"].sum() / 1e4
        sell_s = trades_tmp.loc[trades_tmp["direction"] == "sell"].groupby("sector")["amount_num"].sum() / 1e4
        sector_detail = pd.concat([buy_s.rename("买入"), sell_s.rename("卖出")], axis=1).fillna(0)
        sector_detail["净买入"] = sector_detail["买入"] - sector_detail["卖出"]
        sector_detail = sector_detail.sort_values("买入", ascending=False)

        lines.append("")
        lines.append("**各板块交易（万元）：**")
        lines.append("")
        lines.append("| 板块 | 买入 | 卖出 | 净买入 |")
        lines.append("|------|------|------|--------|")
        for s, row in sector_detail.iterrows():
            lines.append(f"| {s} | {row['买入']:.2f} | {row['卖出']:.2f} | {row['净买入']:.2f} |")
    lines.append("")

    # ── 5. 择时效果评估 ──
    lines.append("## 5. 择时效果评估")
    lines.append("")
    if timing_result is not None and not timing_result.empty:
        lines.append(f"- 大幅加减仓事件数：{len(timing_result)} 次")
        for days in [5, 10, 20]:
            col = f"ret_{days}d"
            if col not in timing_result.columns:
                continue
            buy_rows = timing_result.loc[timing_result["signal"] == "heavy_buy", col].dropna()
            sell_rows = timing_result.loc[timing_result["signal"] == "heavy_sell", col].dropna()
            if not buy_rows.empty:
                wr = (buy_rows > 0).mean()
                lines.append(f"- 买入后{days}日指数胜率：{wr:.1%}（平均涨跌幅 {buy_rows.mean():.2f}%）")
            if not sell_rows.empty:
                wr = (sell_rows < 0).mean()
                lines.append(f"- 卖出后{days}日指数胜率：{wr:.1%}（平均涨跌幅 {sell_rows.mean():.2f}%）")
    else:
        lines.append("（择时信号不足，无法评估）")
    lines.append("")

    # ── 6. 图表附录 ──
    lines.append("## 6. 图表附录")
    lines.append("")
    fig_map = {
        "nav_vs_index.png": "净值 vs 指数归一化对比（含超额）",
        "trade_flow.png": "资金流向与指数走势（买入/卖出）",
        "net_buy_vs_index.png": "净买入与指数走势",
        "position_change_vs_index.png": "仓位变动 vs 指数走势",
        "position_vs_index.png": "仓位比例 vs 指数走势",
        "sector_performance.png": "板块表现 vs 交易金额",
        "sector_rotation_net.png": "板块轮动热力图-净买入",
        "sector_rotation_return.png": "板块轮动热力图-涨跌幅",
        "sector_rotation.png": "板块轮动热力图（周度）",
        "timing_chart.png": "加减仓时点 vs 指数走势",
    }
    for fname, desc in fig_map.items():
        fpath = os.path.join(config.OUTPUT_FIGURES_DIR, fname)
        if os.path.exists(fpath):
            lines.append(f"- **{desc}**: `figures/{fname}`")
        else:
            lines.append(f"- **{desc}**: （未生成）")
    lines.append("")
    lines.append("---")
    lines.append("*本报告由 REITs 交易助手自动生成*")

    report_text = "\n".join(lines)
    out_path = os.path.join(config.OUTPUT_REPORTS_DIR, f"report_{date_str}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    return out_path
