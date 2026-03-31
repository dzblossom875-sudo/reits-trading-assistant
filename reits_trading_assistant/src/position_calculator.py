"""
持仓计算器 v2.1 - 验算驱动的增量缓存
逻辑:
1. 3月6日前: 使用 history data 的仓位
2. 3月7日后: 基于持仓查询文件计算仓位
3. 缓存策略:
   a. 读取现有缓存
   b. 从原始文件计算重叠段，验算缓存正确性
   c. 验算通过 → 仅增量追加新日期
   d. 验算失败 → 全量重建，替换缓存
"""
import os
import glob
import pandas as pd
import numpy as np
from typing import Optional, Tuple
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


_POSITION_CACHE_PATH = os.path.join(config.DATA_PROCESSED_DIR, "position_cache_v2.parquet")
_VALIDATION_TOLERANCE = 0.003  # 仓位差异容忍阈值（绝对值，0.3个百分点）
_VALIDATION_DAYS = 5            # 验算最近N个交易日（缓存末尾）


# ══════════════════════════════════════════════════════════════
# 缓存读写
# ══════════════════════════════════════════════════════════════

def load_position_cache(cache_path: str = None) -> Tuple[Optional[pd.DataFrame], Optional[pd.Timestamp]]:
    """读取持仓缓存"""
    cache_path = cache_path or _POSITION_CACHE_PATH
    if not os.path.exists(cache_path):
        return None, None
    try:
        df = pd.read_parquet(cache_path)
        df.index = pd.to_datetime(df.index)
        max_date = df.index.max()
        print(f"  📦 读取持仓缓存: {len(df)} 天，至 {max_date.strftime('%Y-%m-%d')}")
        return df, max_date
    except Exception as e:
        print(f"  ⚠️ 读取持仓缓存失败: {e}")
        return None, None


def save_position_cache(df: pd.DataFrame, cache_path: str = None) -> None:
    """保存持仓缓存"""
    cache_path = cache_path or _POSITION_CACHE_PATH
    try:
        df.to_parquet(cache_path, index=True)
        print(f"  💾 保存持仓缓存: {len(df)} 天，至 {df.index.max().strftime('%Y-%m-%d')}")
    except Exception as e:
        print(f"  ⚠️ 保存持仓缓存失败: {e}")


# ══════════════════════════════════════════════════════════════
# 原始持仓文件读取
# ══════════════════════════════════════════════════════════════

def load_holdings_from_raw() -> Optional[pd.DataFrame]:
    """
    从原始持仓查询文件读取全部日期的持仓明细
    遍历所有匹配的 xlsx 和 csv 文件，合并数据

    Returns:
        DataFrame: columns=[date, code, market_value]
    """
    all_files = []
    xlsx_pattern = os.path.join(config.DATA_RAW_DIR, "统计分析-持仓查询-组合持仓查询*.xlsx")
    csv_pattern  = os.path.join(config.DATA_RAW_DIR, "统计分析-持仓查询-组合持仓查询*.csv")
    all_files.extend([(f, 'xlsx') for f in glob.glob(xlsx_pattern)])
    all_files.extend([(f, 'csv')  for f in glob.glob(csv_pattern)])

    if not all_files:
        print("  ⚠️ 持仓文件不存在")
        return None

    print(f"  📖 发现 {len(all_files)} 个持仓文件")

    all_data = []
    for filepath, ftype in all_files:
        try:
            if ftype == 'xlsx':
                df = pd.read_excel(filepath, sheet_name=config.SHEET_HOLDINGS, header=0, dtype=str)
            else:
                df = pd.read_csv(filepath, header=0, dtype=str, encoding='utf-8')

            # 按列名映射（防止列位置因文件版本差异漂移）
            name_map = {
                "业务日期": "date",
                "证券代码": "code",
                "本币持仓市值(元)": "market_value",
                "当前成本(元)": "cost_mv",
            }
            df = df.rename(columns={k: v for k, v in name_map.items() if k in df.columns})

            keep_cols = [c for c in ["date", "code", "market_value", "cost_mv"] if c in df.columns]
            if "date" not in keep_cols or "code" not in keep_cols:
                print(f"  ⚠️ {os.path.basename(filepath)} 缺少必要列，跳过")
                continue

            df = df[keep_cols].copy()
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df[df["date"].notna()]

            from src.utils import clean_number, clean_code
            df["market_value"] = df["market_value"].apply(clean_number)
            # market_value=0 时用当前成本兜底（年底/假期等无最新价的日期）
            if "cost_mv" in df.columns:
                df["cost_mv"] = df["cost_mv"].apply(clean_number)
                mask_zero = df["market_value"] == 0
                df.loc[mask_zero, "market_value"] = df.loc[mask_zero, "cost_mv"]
            df = df[df["market_value"] > 0]

            df["code"] = df["code"].apply(clean_code)
            df = df[df["code"].notna() & (df["code"] != "000000")]

            # 文件内聚合：同一 (date, code) 可能分散在多个子账户，求和合并
            rows_raw = len(df)
            df = df.groupby(['date', 'code'], as_index=False)['market_value'].sum()
            print(f"  ✅ {os.path.basename(filepath)}: {rows_raw}行 → {len(df)}条，"
                  f"{df['date'].min().date()} ~ {df['date'].max().date()}")
            all_data.append(df)

        except Exception as e:
            print(f"  ❌ 读取 {os.path.basename(filepath)} 失败: {e}")

    if not all_data:
        print("  ⚠️ 所有持仓文件读取失败")
        return None

    # 跨文件合并：all_files 顺序为 xlsx 先、csv 后；keep='first' 使 xlsx 数据优先
    # （xlsx 为完整组合视图，csv 为历史明细，日期不重叠时两者互补）
    combined = pd.concat(all_data, ignore_index=True)
    combined = combined.drop_duplicates(subset=["date", "code"], keep="first")
    print(f"  📊 合并: {len(combined['date'].unique())} 个交易日，"
          f"{combined['date'].min().date()} ~ {combined['date'].max().date()}")
    return combined


# ══════════════════════════════════════════════════════════════
# 仓位计算
# ══════════════════════════════════════════════════════════════

def calculate_position_from_holdings(
    holdings_df: pd.DataFrame,
    net_assets_df: pd.DataFrame,
    start_date,
    end_date
) -> pd.DataFrame:
    """
    根据持仓查询文件计算每日仓位

    Returns:
        DataFrame: index=date, columns=[total_market_value, position_pct, position_change]
    """
    start = pd.to_datetime(start_date)
    end   = pd.to_datetime(end_date)

    holdings = holdings_df[
        (holdings_df['date'] >= start) &
        (holdings_df['date'] <= end)
    ].copy()

    if holdings.empty:
        print(f"  ⚠️ 持仓文件无 {start.date()} ~ {end.date()} 的数据")
        return pd.DataFrame()

    # 按日汇总市值
    daily_mv = holdings.groupby('date')['market_value'].sum()
    daily_mv.index = pd.to_datetime(daily_mv.index)

    print(f"  📊 持仓数据: {len(daily_mv)} 天，"
          f"市值 {daily_mv.min()/1e4:,.1f}万 ~ {daily_mv.max()/1e4:,.1f}万")

    net_assets_df = net_assets_df.copy()
    net_assets_df.index = pd.to_datetime(net_assets_df.index)

    # 构建日历索引（仅交易日）
    result = pd.DataFrame(index=daily_mv.index.sort_values())
    result['total_market_value'] = daily_mv

    result['net_assets'] = net_assets_df['net_assets'].reindex(result.index).ffill()
    result['position_pct'] = (result['total_market_value'] / result['net_assets']).round(4)
    result['position_change'] = result['position_pct'].diff()

    result = result[result['total_market_value'].notna() & result['net_assets'].notna()]

    print(f"  ✅ 仓位计算: {len(result)} 天，最新 {result['position_pct'].iloc[-1]:.2%} "
          f"({result.index[-1].date()})")

    return result[['total_market_value', 'position_pct', 'position_change']]


# ══════════════════════════════════════════════════════════════
# 验算逻辑
# ══════════════════════════════════════════════════════════════

def validate_cache(
    new_calc: pd.DataFrame,
    cached: pd.DataFrame,
    tolerance: float = _VALIDATION_TOLERANCE,
    check_days: int = _VALIDATION_DAYS
) -> Tuple[bool, int, float]:
    """
    验算新计算结果与缓存的一致性

    取缓存末尾 check_days 个交易日与新计算对比。

    Returns:
        (is_valid, overlap_count, max_diff)
    """
    if cached is None or cached.empty or new_calc is None or new_calc.empty:
        return True, 0, 0.0

    overlap = new_calc.index.intersection(cached.index)
    if len(overlap) == 0:
        return True, 0, 0.0

    # 只校验缓存末尾 N 天
    tail_dates = cached.index.sort_values()[-check_days:]
    validate_dates = overlap.intersection(tail_dates)
    if len(validate_dates) == 0:
        return True, 0, 0.0

    diff = (new_calc.loc[validate_dates, 'position_pct']
            - cached.loc[validate_dates, 'position_pct']).abs()
    max_diff = float(diff.max())
    is_valid = max_diff <= tolerance

    return is_valid, len(validate_dates), max_diff


# ══════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════

def build_position_timeseries(
    history_df: pd.DataFrame,
    net_assets_df: pd.DataFrame,
    position_cutoff: str = "2026-03-06",
    use_cache: bool = True
) -> pd.DataFrame:
    """
    构建完整持仓时序 v2.1

    策略:
    1. ≤ position_cutoff  → history_df.position_pct
    2. > position_cutoff  → 持仓查询文件 + 验算缓存

    缓存验算流程:
      a. 读缓存
      b. 从原始文件计算所有可用日期的仓位
      c. 取缓存末尾 N 天做比对
      d. 验算通过 → 仅追加缓存之后的新日期
         验算失败 → 全量替换缓存
    """
    position_cutoff = pd.to_datetime(position_cutoff)

    print("=" * 60)
    print("📊 构建持仓时序 v2.1（验算驱动）...")
    print(f"  历史/计算切换点: {position_cutoff.date()}")

    result_parts = []

    # ── 1. 历史段 (≤ position_cutoff) ──
    if history_df is not None and 'position_pct' in history_df.columns:
        hist_part = history_df[history_df.index <= position_cutoff].copy()
        if not hist_part.empty:
            hist_result = pd.DataFrame({
                'position_pct':    hist_part['position_pct'],
                'position_change': hist_part['position_pct'].diff(),
            })
            result_parts.append(hist_result)
            print(f"  📚 历史段: {len(hist_result)} 天（至 {hist_result.index.max().date()}）")

    # ── 2. 计算段 (> position_cutoff) ──
    calc_start = position_cutoff + pd.Timedelta(days=1)
    calc_end   = net_assets_df.index.max()

    # a. 读缓存
    cached_pos, cache_date = (None, None)
    if use_cache:
        cached_pos, cache_date = load_position_cache()

    # b. 从原始文件计算所有可用日期
    holdings_df = load_holdings_from_raw()

    if holdings_df is not None and not holdings_df.empty:
        all_calc = calculate_position_from_holdings(
            holdings_df, net_assets_df, calc_start, calc_end
        )

        if not all_calc.empty:
            # c/d. 验算
            if cached_pos is not None and not cached_pos.empty:
                is_valid, n_checked, max_diff = validate_cache(all_calc, cached_pos)

                if is_valid:
                    print(f"  ✅ 验算通过：{n_checked} 天重叠，最大差异 {max_diff:.4f} < {_VALIDATION_TOLERANCE}")
                    # 仅追加缓存末尾之后的新日期
                    new_dates = all_calc[all_calc.index > cache_date]
                    if not new_dates.empty:
                        updated = pd.concat([
                            cached_pos[cached_pos.index >= calc_start],
                            new_dates
                        ]).sort_index()
                        updated = updated[~updated.index.duplicated(keep='last')]
                        print(f"  ➕ 增量追加: {len(new_dates)} 天 "
                              f"({new_dates.index.min().date()} ~ {new_dates.index.max().date()})")
                    else:
                        updated = cached_pos[cached_pos.index >= calc_start]
                        print("  ℹ️ 无新数据，缓存已是最新")
                    if use_cache:
                        save_position_cache(updated)
                    result_parts.append(updated)

                else:
                    print(f"  ⚠️ 验算失败：最大差异 {max_diff:.2%} > {_VALIDATION_TOLERANCE:.1%}")
                    print("  🔄 全量重建缓存...")
                    if use_cache:
                        save_position_cache(all_calc)
                    result_parts.append(all_calc)

            else:
                # 无缓存 → 全量建立
                print("  🆕 无缓存，全量建立...")
                if use_cache:
                    save_position_cache(all_calc)
                result_parts.append(all_calc)

        else:
            print("  ⚠️ 持仓文件无有效数据，回退到已有缓存")
            if cached_pos is not None:
                result_parts.append(cached_pos[cached_pos.index >= calc_start])

    elif cached_pos is not None:
        print("  ⚠️ 无法读取持仓文件，使用已有缓存")
        result_parts.append(cached_pos[cached_pos.index >= calc_start])

    else:
        print("  ⚠️ 既无持仓文件，也无缓存，计算段跳过")

    # ── 3. 合并 ──
    if result_parts:
        full_result = pd.concat(result_parts)
        full_result = full_result[~full_result.index.duplicated(keep='last')].sort_index()
    else:
        full_result = pd.DataFrame()

    print(f"\n✅ 持仓时序构建完成: {len(full_result)} 天")
    if not full_result.empty:
        print(f"   最新仓位: {full_result['position_pct'].iloc[-1]:.2%} "
              f"({full_result.index[-1].date()})")

    return full_result


# ══════════════════════════════════════════════════════════════
# 独立测试
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("持仓计算器 v2.1 测试")
    from src.data_loader import load_history_data

    history = load_history_data()
    nav = pd.read_csv(
        os.path.join(config.DATA_PROCESSED_DIR, "nav_daily.csv"),
        index_col=0, parse_dates=True
    )

    result = build_position_timeseries(
        history_df=history,
        net_assets_df=nav[['net_assets']],
        position_cutoff="2026-03-06"
    )

    print("\n结果预览（切换点前后各5天）:")
    cutoff = pd.to_datetime("2026-03-06")
    window = result[(result.index >= cutoff - pd.Timedelta(days=10)) &
                    (result.index <= cutoff + pd.Timedelta(days=14))]
    print(window[['position_pct', 'position_change']].to_string())
