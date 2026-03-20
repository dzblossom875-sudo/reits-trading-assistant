"""
报告生成模块
"""
import os
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _read_csv_safe(path: str) -> pd.DataFrame:
    if os.path.exists(path):
        try:
            return pd.read_csv(path, encoding="utf-8-sig")
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def generate_report(date_str: str = None):
    """读取所有分析结果，生成 output/reports/report_{date}.md"""
    if date_str is None:
        from datetime import date
        date_str = date.today().strftime("%Y%m%d")

    # 读取各分析结果
    perf_df = _read_csv_safe(os.path.join(config.OUTPUT_DIR, "performance_summary.csv"))
    trade_df = _read_csv_safe(os.path.join(config.OUTPUT_DIR, "trade_summary.csv"))
    timing_df = _read_csv_safe(os.path.join(config.OUTPUT_DIR, "timing_analysis.csv"))
    daily_df = _read_csv_safe(os.path.join(config.DATA_PROCESSED_DIR, "daily.csv"))
    trades_clean_df = _read_csv_safe(os.path.join(config.DATA_PROCESSED_DIR, "trades_clean.csv"))
    holdings_df = _read_csv_safe(os.path.join(config.DATA_PROCESSED_DIR, "holdings.csv"))
    bias_df = _read_csv_safe(os.path.join(config.DATA_PROCESSED_DIR, "allocation_bias.csv"))

    lines = []
    account_name = config.ACCOUNT_NAME

    # 标题
    lines.append(f"# {account_name} REITs 交易分析报告")
    lines.append(f"")
    lines.append(f"**报告日期**: {date_str[:4]}-{date_str[4:6]}-{date_str[6:]}")
    lines.append(f"**基准日期**: {config.BASE_DATE}")
    lines.append(f"")
    lines.append("---")
    lines.append("")

    # 1. 核心结论
    lines.append("## 1. 核心结论")
    lines.append("")
    if not perf_df.empty:
        nav_ret_row = perf_df[perf_df["指标"].str.contains("年化收益率", na=False) & ~perf_df["指标"].str.contains("指数", na=False)]
        excess_row = perf_df[perf_df["指标"].str.contains("超额", na=False)]
        if not nav_ret_row.empty:
            lines.append(f"- {account_name}年化收益率：{nav_ret_row['数值'].iloc[0]}")
        if not excess_row.empty:
            lines.append(f"- 相对中证REITs指数超额收益：{excess_row['数值'].iloc[0]}")
    if not trade_df.empty:
        total_buy = trade_df["buy_amount"].sum() if "buy_amount" in trade_df.columns else 0
        total_sell = trade_df["sell_amount"].sum() if "sell_amount" in trade_df.columns else 0
        total_dividend = trade_df["dividend_amount"].sum() if "dividend_amount" in trade_df.columns else 0
        lines.append(f"- 累计买入：{total_buy/1e6:.2f} 百万元，卖出：{total_sell/1e6:.2f} 百万元")
        if total_dividend > 0:
            lines.append(f"- 红利到账：{total_dividend/1e4:.2f} 万元")
    lines.append("")

    # 2. 账户表现
    lines.append("## 2. 账户表现")
    lines.append("")
    if not perf_df.empty:
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        for _, row in perf_df.iterrows():
            lines.append(f"| {row['指标']} | {row['数值']} |")
    else:
        lines.append("（暂无业绩数据）")
    lines.append("")

    # 3. 配置偏移
    lines.append("## 3. 配置偏移分析")
    lines.append("")
    if bias_df is not None and not bias_df.empty:
        lines.append("| 板块 | 账户权重 | 指数权重 | 偏移 |")
        lines.append("|------|----------|----------|------|")
        for _, row in bias_df.iterrows():
            lines.append(f"| {row.get('板块', '')} | {row.get('账户权重', '')} | {row.get('指数权重', '')} | {row.get('偏移', '')} |")
    else:
        lines.append("（暂无配置偏移数据）")
    lines.append("")

    # 4. 交易行为复盘
    lines.append("## 4. 交易行为复盘")
    lines.append("")
    if not trade_df.empty:
        trade_df["date"] = pd.to_datetime(trade_df["date"], errors="coerce")
        heavy_buy = trade_df[trade_df["signal"] == "heavy_buy"] if "signal" in trade_df.columns else pd.DataFrame()
        heavy_sell = trade_df[trade_df["signal"] == "heavy_sell"] if "signal" in trade_df.columns else pd.DataFrame()
        lines.append(f"- 交易日总数：{len(trade_df)} 天")
        if not heavy_buy.empty:
            lines.append(f"- 大幅加仓日：{len(heavy_buy)} 天")
        if not heavy_sell.empty:
            lines.append(f"- 大幅减仓日：{len(heavy_sell)} 天")
        if not trades_clean_df.empty and "sector" in trades_clean_df.columns:
            trades_clean_df["amount"] = pd.to_numeric(trades_clean_df["amount"], errors="coerce")
            sector_sum = trades_clean_df.groupby('sector')['amount'].sum().sort_values(ascending=False)
            lines.append("")
            lines.append("**各板块交易金额（万元）**：")
            lines.append("")
            lines.append("| 板块 | 金额（万元） |")
            lines.append("|------|------------|")
            for s, v in sector_sum.items():
                lines.append(f"| {s} | {v/1e4:.2f} |")
    else:
        lines.append("（暂无交易数据）")
    lines.append("")

    # 5. 择时效果评估
    lines.append("## 5. 择时效果评估")
    lines.append("")
    if not timing_df.empty:
        lines.append(f"- 大幅加减仓事件数：{len(timing_df)} 次")
        for days in [5, 10, 20]:
            col = f"ret_{days}d"
            if col in timing_df.columns:
                buy_rows = timing_df[timing_df["signal"] == "heavy_buy"][col].dropna()
                sell_rows = timing_df[timing_df["signal"] == "heavy_sell"][col].dropna()
                if not buy_rows.empty:
                    wr = (buy_rows > 0).mean()
                    lines.append(f"- 买入后 {days} 日指数胜率：{wr:.1%}（平均涨跌幅 {buy_rows.mean():.2f}%）")
                if not sell_rows.empty:
                    wr = (sell_rows < 0).mean()
                    lines.append(f"- 卖出后 {days} 日指数胜率：{wr:.1%}（平均涨跌幅 {sell_rows.mean():.2f}%）")
    else:
        lines.append("（择时信号不足，无法评估）")
    lines.append("")

    # 6. 板块分析
    lines.append("## 6. 板块分析")
    lines.append("")
    if not trades_clean_df.empty and "sector" in trades_clean_df.columns:
        trades_clean_df["amount"] = pd.to_numeric(trades_clean_df.get("amount", 0), errors="coerce").fillna(0)
        trades_clean_df["direction"] = trades_clean_df.get("direction", "")
        buy_df = trades_clean_df[trades_clean_df["direction"] == "buy"]
        sell_df = trades_clean_df[trades_clean_df["direction"] == "sell"]
        buy_s = buy_df.groupby("sector")["amount"].sum().rename("买入（万元）") / 1e4
        sell_s = sell_df.groupby("sector")["amount"].sum().rename("卖出（万元）") / 1e4
        sector_detail = pd.concat([buy_s, sell_s], axis=1).fillna(0)
        sector_detail["净买入（万元）"] = sector_detail["买入（万元）"] - sector_detail["卖出（万元）"]
        sector_detail = sector_detail.sort_values("买入（万元）", ascending=False)

        lines.append("| 板块 | 买入（万元） | 卖出（万元） | 净买入（万元） |")
        lines.append("|------|------------|------------|--------------|")
        for s, row in sector_detail.iterrows():
            lines.append(f"| {s} | {row['买入（万元）']:.2f} | {row['卖出（万元）']:.2f} | {row['净买入（万元）']:.2f} |")
    else:
        lines.append("（暂无板块数据）")
    lines.append("")

    # 7. 图表附录
    lines.append("## 7. 图表附录")
    lines.append("")
    fig_map = {
        "nav_vs_index.png": "净值 vs 指数归一化对比（含超额）",
        "trade_flow.png": "资金流向与指数走势",
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
