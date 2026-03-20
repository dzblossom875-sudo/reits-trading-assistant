"""
REITs 交易助手主入口
"""
import sys
import os
import pandas as pd

# 确保项目根目录在 sys.path 中
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import config  # noqa: 触发目录创建

from src.data_loader import align_and_save, load_holdings_timeseries
from src.sector_analysis import analyze_sector_trades, plot_sector_performance, plot_sector_rotation_dual, calc_sector_returns
from src.trade_analysis import plot_trade_flow, plot_net_buy_vs_index, plot_sector_rotation, save_trade_summary, plot_position_vs_index, summarize_trades
from src.timing_analysis import analyze_timing, plot_timing_chart, save_timing_result
from src.performance_analysis import calc_metrics, plot_nav_vs_index, save_performance_summary, calc_metrics_by_period, save_daily_tracking, plot_position_change_vs_index
from src.allocation_analysis import calc_allocation_bias, calc_sector_allocation_bias, save_allocation_bias
from src.wind_data_loader import load_reits_prices_with_fallback, load_index_data_with_fallback
from src.report_generator import generate_report


def main():
    print("=" * 60)
    print(f"REITs 交易助手启动 - {config.ACCOUNT_NAME}")
    print(f"基准日期: {config.BASE_DATE}")
    print("=" * 60)

    # Step 1: 数据加载与整合
    print("\n[1/7] 数据加载与清洗...")
    reits_info, daily_df, nav_df, trades_df, holdings_df, weight_df = align_and_save()

    # 加载日频持仓和净资产数据（用于仓位计算）
    holdings_daily = load_holdings_timeseries()  # 日频持仓市值
    net_assets = nav_df.get("net_assets") if nav_df is not None and "net_assets" in nav_df.columns else None
    if net_assets is not None:
        net_assets = pd.DataFrame({"net_assets": net_assets})

    print(f"  REITs 信息: {len(reits_info)} 条")
    print(f"  日频数据: {daily_df.shape}")
    if nav_df is not None:
        print(f"  净值数据: {nav_df.shape}")
    if trades_df is not None:
        print(f"  交易数据: {trades_df.shape}")
        if "direction" in trades_df.columns:
            print(f"    交易类型: {trades_df['direction'].value_counts().to_dict()}")
    if holdings_df is not None:
        print(f"  持仓数据: {holdings_df.shape}（截面：{holdings_df['date'].iloc[0].strftime('%Y-%m-%d') if 'date' in holdings_df.columns else 'N/A'}）")
    if holdings_daily is not None:
        print(f"  持仓时序: {len(holdings_daily)} 天")
    if weight_df is not None:
        print(f"  指数权重: {len(weight_df)} 条, 总权重={weight_df['weight'].sum():.2%}")

    # Step 2: 尝试从Wind获取行情数据
    print("\n[2/7] 获取行情数据...")
    reits_prices = None
    if config.USE_WIND_API:
        print("  尝试从Wind API获取个股行情...")
        codes = reits_info["code"].tolist() if "code" in reits_info.columns else []
        reits_prices = load_reits_prices_with_fallback(codes)
        if reits_prices is not None:
            print(f"  Wind数据: {reits_prices.shape}")
        else:
            print("  Wind获取失败，后续板块涨跌幅计算将跳过")
    else:
        print("  跳过Wind API，使用本地数据")

    # Step 3: 板块分析
    print("\n[3/7] 板块分析...")
    if trades_df is None:
        print("  ⚠️ 无交易数据，跳过板块交易分析")
        sector_result = pd.DataFrame()
    else:
        sector_result = analyze_sector_trades(trades_df, reits_info)
        print(f"  板块数量: {len(sector_result)}")

    # 计算板块区间涨跌幅
    sector_returns = None
    if reits_prices is not None:
        from pandas import to_datetime
        period_end = daily_df.index.max() if not daily_df.empty else None
        period_start = daily_df.index.min() if not daily_df.empty else None
        sector_returns = calc_sector_returns(reits_prices, reits_info, period_start, period_end)
        if sector_returns is not None:
            print(f"  板块涨跌幅计算完成: {len(sector_returns)} 个板块")

    plot_sector_performance(trades_df, reits_info, sector_returns)
    print("  已生成: sector_performance.png")

    # 板块轮动双图
    paths = plot_sector_rotation_dual(trades_df, reits_prices, reits_info)
    if paths[0]:
        print("  已生成: sector_rotation_net.png")
    if paths[1]:
        print("  已生成: sector_rotation_return.png")

    # 保留周度轮动图
    plot_sector_rotation(trades_df)
    print("  已生成: sector_rotation.png")

    # Step 4: 交易分析
    print("\n[4/7] 交易行为分析...")
    from src.trade_analysis import summarize_trades
    daily_trades = summarize_trades(trades_df, holdings_daily, net_assets) if trades_df is not None else None
    save_trade_summary(trades_df, holdings_daily, net_assets)
    print("  已保存: trade_summary.xlsx")

    plot_trade_flow(trades_df, daily_df) if trades_df is not None else None
    print("  已生成: trade_flow.png")

    plot_net_buy_vs_index(trades_df, daily_df) if trades_df is not None else None
    print("  已生成: net_buy_vs_index.png")

    # 仓位变动图
    pos_path = plot_position_vs_index(daily_trades, daily_df) if daily_trades is not None else None
    if pos_path:
        print("  已生成: position_vs_index.png")

    # Step 5: 择时分析
    print("\n[5/7] 择时效果分析...")
    timing_result = analyze_timing(trades_df, daily_df)
    if timing_result is not None and not timing_result.empty:
        print(f"  加减仓事件: {len(timing_result)} 次")
        save_timing_result(timing_result)
        print("  已保存: timing_analysis.xlsx")
    else:
        print("  择时信号不足，跳过详细统计")
        save_timing_result(timing_result)

    plot_timing_chart(trades_df, daily_df)
    print("  已生成: timing_chart.png")

    # Step 6: 业绩分析
    print("\n[6/7] 业绩表现分析...")
    # 传递 base_date，确保总体指标与分月表现口径一致
    base_date = pd.to_datetime(config.BASE_DATE)
    metrics = calc_metrics(nav_df, daily_df, base_date=base_date)
    for k, v in metrics.items():
        if isinstance(v, float) and not __import__("math").isnan(v):
            print(f"  {k}: {v:.4f}")
    if "base_date" in metrics:
        print(f"  计算基准日：{metrics['base_date']}")

    # 计算分月指标
    period_df = calc_metrics_by_period(daily_df)
    save_performance_summary(metrics, period_df)
    print("  已保存: performance_summary.xlsx")

    plot_nav_vs_index(daily_df)
    print("  已生成: nav_vs_index.png")

    # 逐日跟踪表（归一化净值 + 仓位）
    tracking_df, tracking_path = save_daily_tracking(daily_df, holdings_daily, nav_df)
    print(f"  已保存: daily_tracking.xlsx ({len(tracking_df)} 天)")

    # 仓位变动 vs 指数图
    pos_chg_path = plot_position_change_vs_index(tracking_df, daily_df)
    if pos_chg_path:
        print("  已生成: position_change_vs_index.png")

    # Step 7: 配置偏移分析
    print("\n[7/7] 配置偏移分析...")
    bias_sector = None
    if holdings_df is not None and weight_df is not None:
        bias_detail = calc_allocation_bias(holdings_df, weight_df, reits_info)
        bias_sector = calc_sector_allocation_bias(holdings_df, weight_df, reits_info)
        if bias_detail is not None:
            print(f"  个券偏移计算完成: {len(bias_detail)} 只")
        if bias_sector is not None:
            print(f"  板块偏移计算完成: {len(bias_sector)} 个板块")
            print("  板块偏移:")
            for _, row in bias_sector.iterrows():
                print(f"    {row['sector']}: 账户{row['account_weight']:.2%} - 指数{row['index_weight']:.2%} = {row['weight_bias']:+.2%}")
        save_allocation_bias(bias_detail, bias_sector, config.OUTPUT_DIR)
        print("  已保存: allocation_bias.xlsx")
    else:
        print("  缺少持仓或权重数据，跳过配置偏移分析")

    # Step 8: 报告生成
    print("\n[8/8] 生成分析报告...")
    report_path = generate_report(
        config.RUN_TIMESTAMP,
        metrics=metrics,
        period_df=period_df,
        trades_df=trades_df,
        daily_trades=daily_trades,
        timing_result=timing_result,
        bias_sector=bias_sector,
    )
    print(f"  报告已生成: {report_path}")

    print("\n" + "=" * 60)
    print("所有分析完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
