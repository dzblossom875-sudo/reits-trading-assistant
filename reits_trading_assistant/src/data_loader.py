"""
数据加载与清洗模块
v2.1 - 修复持仓数据读取（时点数据 + 负数检查）
"""
import os, re, sys
import glob
import pandas as pd
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src.utils import clean_code, clean_number, parse_date, get_latest_daily_report, normalize_series


# ============== Wind API 检查 ==============

def check_wind_connection():
    """检查 Wind API 是否成功接入"""
    try:
        from WindPy import w
        result = w.start()
        if result.ErrorCode == 0:
            return True, "Wind API 连接成功"
        else:
            return False, f"Wind API 连接失败：ErrorCode={result.ErrorCode}"
    except ImportError:
        return False, "WindPy 未安装"
    except Exception as e:
        return False, f"Wind API 检查异常：{str(e)}"


# ============== 基础数据加载 ==============

def load_reits_info():
    """加载 REITs 基础信息（代码、名称、板块）"""
    filepath = os.path.join(config.DATA_RAW_DIR, config.FILE_REITS_INFO)
    print(f"📖 读取 REITs 基础信息：{filepath}")
    xl = pd.ExcelFile(filepath)
    df = pd.read_excel(filepath, sheet_name=xl.sheet_names[0])
    col_map = {}
    for col in df.columns:
        if "代码" in str(col): col_map["code"] = col
        elif "名称" in str(col) and "name" not in col_map: col_map["name"] = col
        elif "项目类型" in str(col) or "板块" in str(col): col_map["sector"] = col
    df = df.rename(columns={v:k for k,v in col_map.items()})
    keep = [c for c in ["code","name","sector"] if c in df.columns]
    df = df[keep].copy()
    df["code"] = df["code"].apply(clean_code)
    df = df[df["code"].notna() & (df["code"]!="000000")]
    if "sector" in df.columns:
        df["sector"] = df["sector"].apply(lambda x: config.SECTOR_SYNONYMS.get(str(x).strip(), str(x).strip()))
    print(f"  ✅ 读取完成：{len(df)} 条")
    return df.drop_duplicates(subset=["code"]).reset_index(drop=True)


def load_index():
    """加载指数数据（本地 Excel）"""
    filepath = os.path.join(config.DATA_RAW_DIR, config.FILE_INDEX)
    print(f"📖 读取指数数据：{filepath}")
    df_raw = pd.read_excel(filepath, sheet_name="Sheet2", header=None)
    col_names = df_raw.iloc[3].tolist()
    df_data = df_raw.iloc[5:].copy().reset_index(drop=True)
    df_data.columns = range(len(df_data.columns))
    df_data = df_data.rename(columns={0:"date"})
    df_data["date"] = df_data["date"].apply(parse_date)
    df_data = df_data[df_data["date"].notna()].copy()
    rename_map = {}
    for i,name in enumerate(col_names):
        n = str(name).strip()
        if "REITs" in n and "全收" in n: rename_map[i] = "reits_index"
        elif "10Y" in n or "国债" in n: rename_map[i] = "tb10y"
        elif "沪深 300" in n or ("300" in n and "红利" not in n): rename_map[i] = "hs300"
        elif "红利" in n: rename_map[i] = "csi_dividend"
    df_data = df_data.rename(columns=rename_map)
    keep = ["date"] + [c for c in ["reits_index","tb10y","hs300","csi_dividend"] if c in df_data.columns]
    df_data = df_data[keep]
    for col in keep[1:]: df_data[col] = pd.to_numeric(df_data[col], errors="coerce")
    print(f"  ✅ 读取完成：{len(df_data)} 条")
    return df_data.sort_values("date").set_index("date")


def load_nav_from_daily_report():
    """从日报表读取净值时间序列"""
    daily_report_path = get_latest_daily_report(config.DATA_RAW_DIR, config.DAILY_REPORT_PATTERN)
    if daily_report_path is None:
        print("⚠️ 未找到日报表文件")
        return None
    print(f"📖 读取日报表：{os.path.basename(daily_report_path)}")
    df_raw = pd.read_excel(daily_report_path, sheet_name=config.SHEET_NAV, header=None)
    col_names = df_raw.iloc[3].tolist()
    df_data = df_raw.iloc[4:].copy().reset_index(drop=True)
    df_data.columns = col_names
    df_data = df_data.rename(columns={col_names[0]:"date"})
    df_data["date"] = df_data["date"].apply(parse_date)
    df_data = df_data[df_data["date"].notna()]
    nav_col = next((c for c in df_data.columns if "累计" in str(c) and "净值" in str(c)), None)
    if nav_col is None:
        nav_col = next((c for c in df_data.columns if "净值" in str(c)), None)
    # 同时读取净资产（市值）用于仓位计算
    net_assets_col = next((c for c in df_data.columns if "净资产" in str(c) and "市值" in str(c)), None)
    keep_cols = ["date", nav_col] + ([net_assets_col] if net_assets_col else [])
    rename = {nav_col: "nav"}
    if net_assets_col:
        rename[net_assets_col] = "net_assets"
    df_data = df_data[keep_cols].rename(columns=rename)
    df_data["nav"] = pd.to_numeric(df_data["nav"], errors="coerce")
    if "net_assets" in df_data.columns:
        df_data["net_assets"] = pd.to_numeric(df_data["net_assets"], errors="coerce")
    df_clean = df_data[df_data["nav"].notna()].sort_values("date").drop_duplicates("date").set_index("date")
    print(f"  ✅ 读取完成：{len(df_clean)} 条")
    return df_clean


# ============== 交易数据加载 ==============

def load_trades_from_exchange_query():
    """从交易所成交查询文件读取交易数据"""
    files = (
        glob.glob(os.path.join(config.DATA_RAW_DIR, "统计分析*交易查询*.csv")) +
        glob.glob(os.path.join(config.DATA_RAW_DIR, "统计分析*交易查询*.xlsx"))
    )

    if not files:
        print("⚠️ 未找到交易所成交查询文件")
        return None

    latest_file = max(files, key=os.path.getmtime)
    print(f"📖 读取交易所成交查询：{os.path.basename(latest_file)}")
    
    try:
        if latest_file.endswith('.xlsx') or latest_file.endswith('.xls'):
            df = pd.read_excel(latest_file, dtype=str)
        else:
            df = pd.read_csv(latest_file, sep=None, engine='python', dtype=str)
    except Exception as e:
        print(f"❌ 读取交易文件失败：{e}")
        return None
    
    col_map = {}
    for col in df.columns:
        col_str = str(col).strip()
        if "证券代码" in col_str or "代码" == col_str: col_map["code"] = col
        elif "证券名称" in col_str or "简称" in col_str or "名称" == col_str: col_map["name"] = col
        elif "委托方向" in col_str or "方向" in col_str: col_map["direction"] = col
        elif "成交价格" in col_str or "价格" == col_str: col_map["price"] = col
        elif col_str == "成交数量" or "成交数量(股" in col_str: col_map["quantity"] = col
        elif col_str == "成交金额" or (col_str.startswith("成交金额") and "amount" not in col_map): col_map["amount"] = col
        elif col_str == "全价成交金额" and "amount" not in col_map: col_map["amount"] = col
        elif "业务日期" in col_str: col_map["date"] = col
        elif "日期" in col_str and "date" not in col_map: col_map["date"] = col
    
    print(f"  列映射：{col_map}")
    df = df.rename(columns={v:k for k,v in col_map.items()})
    
    required_cols = ["date", "code", "direction", "amount"]
    missing = set(required_cols) - set(df.columns)
    if missing:
        print(f"⚠️ 缺少字段：{missing}")
        return None
    
    df["date"] = df["date"].apply(parse_date)
    df = df[df["date"].notna()]
    df["code"] = df["code"].apply(clean_code)
    df = df[df["code"].notna() & (df["code"] != "000000")]
    
    for col in ["quantity", "amount", "price"]:
        if col in df.columns:
            df[col] = df[col].apply(clean_number)
    
    def normalize_direction(dir_val):
        if pd.isna(dir_val):
            return "other"
        dir_str = str(dir_val).strip().upper()
        if "买入" in dir_str or dir_str == "B":
            return "buy"
        elif "卖出" in dir_str or dir_str == "S":
            return "sell"
        elif "分红" in dir_str or "红利" in dir_str:
            return "dividend"
        else:
            return "other"
    
    df["direction"] = df["direction"].apply(normalize_direction)
    
    direction_counts = df["direction"].value_counts()
    print(f"  交易方向分布:")
    for direction, count in direction_counts.items():
        print(f"    - {direction}: {count} 笔")
    
    keep_cols = [c for c in ["date","code","name","direction","quantity","price","amount"] if c in df.columns]
    df_clean = df[keep_cols].copy()
    
    print(f"  ✅ 读取完成：{len(df_clean)} 笔交易")
    return df_clean.sort_values("date").reset_index(drop=True)


# ============== 持仓数据加载（v2.1 修复版） ==============

def load_holdings():
    """
    读取持仓查询文件
    文件结构（根据实际文件确认）：
    - A 列（0）：日期
    - L 列（11）：证券代码
    - P 列（15）：权重（单券市值/组合净值）
    - AR 列（43）：市值
    
    处理逻辑：
    1. 读取全部数据
    2. 筛选最新日期的持仓（时点数据）
    3. 检查负数持仓（报错）
    4. 验证权重合计
    """
    files = glob.glob(os.path.join(config.DATA_RAW_DIR, config.FILE_HOLDINGS))
    if not files:
        print(f"⚠️ 持仓文件不存在：{config.FILE_HOLDINGS}")
        return None
    filepath = max(files, key=os.path.getmtime)
    print(f"📖 读取持仓查询：{os.path.basename(filepath)}")
    
    # 读取 Excel（无表头）
    df = pd.read_excel(filepath, sheet_name=config.SHEET_HOLDINGS, header=None, dtype=str)
    
    # 列映射（0-indexed）
    # A=0, L=11, P=15, AR=43
    col_map = {
        0: "date",        # A 列：日期
        11: "code",       # L 列：证券代码
        15: "weight",     # P 列：权重
        43: "market_value",  # AR 列：市值
    }
    df = df.rename(columns=col_map)
    
    # 保留关键列
    keep_cols = [c for c in ["date", "code", "weight", "market_value"] if c in df.columns]
    df = df[keep_cols].copy()
    
    # 检查必需字段
    required = ["date", "code", "market_value"]
    missing = set(required) - set(df.columns)
    if missing:
        print(f"❌ 缺少必需字段：{missing}")
        print(f"  当前字段：{list(df.columns)}")
        return None
    
    # 清洗日期
    df["date"] = df["date"].apply(parse_date)
    df = df[df["date"].notna()]
    
    # 清洗代码
    df["code"] = df["code"].apply(clean_code)
    df = df[df["code"].notna() & (df["code"] != "000000")]
    
    # 清洗市值（数值）
    df["market_value"] = df["market_value"].apply(clean_number)
    
    # 清洗权重（如果有）
    if "weight" in df.columns:
        df["weight"] = df["weight"].apply(clean_number)
        # 转换为小数（如果是百分比）
        if df["weight"].max() > 1:
            df["weight"] = df["weight"] / 100
    
    # 🔴 检查负数持仓（报错）
    negative_holdings = df[df["market_value"] < 0]
    if not negative_holdings.empty:
        print(f"❌ 错误：发现{len(negative_holdings)}条负数持仓记录！")
        print("  负数持仓明细（前 10 条）：")
        for idx, row in negative_holdings.head(10).iterrows():
            code = row.get('code', 'N/A')
            mv = row.get('market_value', 0)
            print(f"    - {code}: {mv:.2f}")
        print("  请检查持仓数据源！")
        # 过滤负数持仓
        df = df[df["market_value"] >= 0]
    
    # 🔴 获取最新日期的持仓（时点数据）
    latest_date = df["date"].max()
    min_date = df["date"].min()
    print(f"  持仓日期范围：{min_date.strftime('%Y-%m-%d')} ~ {latest_date.strftime('%Y-%m-%d')}")
    print(f"  → 使用最新日期持仓：{latest_date.strftime('%Y-%m-%d')}")
    df_latest = df[df["date"] == latest_date].copy()
    
    # 如果权重字段为空，用市值计算
    if "weight" not in df_latest.columns or df_latest["weight"].isna().all():
        total_mv = df_latest["market_value"].sum()
        if total_mv > 0:
            df_latest["weight"] = df_latest["market_value"] / total_mv
            print(f"  权重已计算（市值/总市值）")
    
    # 验证权重合计
    weight_sum = df_latest["weight"].sum()
    print(f"  权重合计：{weight_sum:.2%}")
    if abs(weight_sum - 1.0) > 0.01:
        print(f"  ⚠️ 警告：权重合计{weight_sum:.2%} 不等于 100%，请检查数据")
    
    print(f"  ✅ 读取完成：{len(df_latest)} 条持仓（日期：{latest_date.strftime('%Y-%m-%d')}）")
    return df_latest.reset_index(drop=True)


def load_holdings_timeseries():
    """
    读取持仓查询文件全部日期，返回日频持仓市值汇总
    用于仓位计算
    """
    files = glob.glob(os.path.join(config.DATA_RAW_DIR, config.FILE_HOLDINGS))
    if not files:
        return None
    filepath = max(files, key=os.path.getmtime)
    df = pd.read_excel(filepath, sheet_name=config.SHEET_HOLDINGS, header=None, dtype=str)
    col_map = {0: "date", 11: "code", 43: "market_value"}
    df = df.rename(columns=col_map)
    keep = [c for c in ["date", "code", "market_value"] if c in df.columns]
    if not keep:
        return None
    df = df[keep].copy()
    df["date"] = df["date"].apply(parse_date)
    df = df[df["date"].notna()]
    df["market_value"] = df["market_value"].apply(clean_number)
    df = df[df["market_value"] >= 0]  # 过滤负数
    # 按日汇总持仓市值
    daily_mv = df.groupby("date")["market_value"].sum().reset_index()
    daily_mv = daily_mv.sort_values("date").set_index("date")
    # 部分导出在缺行时日内合计为 0；0 视为缺失，沿用上一有效持仓总市值（真清仓需源文件显式非零后归零）
    mv = daily_mv["market_value"].replace(0, np.nan).ffill()
    daily_mv["market_value"] = mv.fillna(0)
    return daily_mv


def load_index_weight_932006():
    """读取 932006 指数权重文件"""
    filepath = os.path.join(config.DATA_RAW_DIR, config.FILE_WEIGHT_932006)
    if not os.path.exists(filepath):
        print(f"⚠️ 权重文件不存在：{filepath}")
        return None
    print(f"📖 读取指数权重：{os.path.basename(filepath)}")
    df = pd.read_excel(filepath)
    col_map = {}
    for col in df.columns:
        col_str = str(col).strip()
        if "成分券代码" in col_str or "Constituent Code" in col_str: col_map["code"] = col
        elif "成分券名称" in col_str or "Constituent Name" in col_str: col_map["name"] = col
        elif "权重" in col_str or "weight" in col_str.lower(): col_map["weight"] = col
    df = df.rename(columns={v:k for k,v in col_map.items()})
    if "code" in df.columns:
        df["code"] = df["code"].apply(clean_code)
    if "weight" in df.columns:
        df["weight"] = df["weight"].apply(clean_number) / 100
    keep_cols = [c for c in ["code","name","weight"] if c in df.columns]
    df_clean = df[keep_cols].dropna(subset=["code"]).reset_index(drop=True)
    print(f"  ✅ 读取完成：{len(df_clean)} 条")
    return df_clean


# ============== 主数据对齐函数 ==============

def align_and_save():
    """主数据对齐函数"""
    print("=" * 60)
    print("🚀 开始加载数据...")
    print("=" * 60)
    
    # 检查 Wind API 连接
    if config.USE_WIND_API:
        print("\n🔌 检查 Wind API 连接...")
        wind_ok, wind_msg = check_wind_connection()
        if wind_ok:
            print(f"  ✅ {wind_msg}")
        else:
            print(f"  ⚠️ {wind_msg}")
            print("  → 将使用本地数据")
    
    # 加载 REITs 基础信息
    reits_info = load_reits_info()
    
    # 加载指数数据
    index_df = load_index()
    
    # 加载净值数据
    nav_df = load_nav_from_daily_report()
    
    # 加载交易数据（使用交易所成交查询文件）
    trades_df = load_trades_from_exchange_query()
    
    # 加载持仓数据（时点数据）
    holdings_df = load_holdings()
    
    # 加载指数权重
    weight_df = load_index_weight_932006()
    
    # 保存处理后的数据
    print("\n💾 保存处理后的数据...")
    reits_info.to_csv(os.path.join(config.DATA_PROCESSED_DIR,"reits_info.csv"), index=False, encoding="utf-8-sig")
    if nav_df is not None:
        nav_df.to_csv(os.path.join(config.DATA_PROCESSED_DIR,"nav_daily.csv"), encoding="utf-8-sig")
    if trades_df is not None:
        trades_df.to_csv(os.path.join(config.DATA_PROCESSED_DIR,"trades_clean.csv"), index=False, encoding="utf-8-sig")
    if holdings_df is not None:
        holdings_df.to_csv(os.path.join(config.DATA_PROCESSED_DIR,"holdings.csv"), index=False, encoding="utf-8-sig")
    if weight_df is not None:
        weight_df.to_csv(os.path.join(config.DATA_PROCESSED_DIR,"index_weight_932006.csv"), index=False, encoding="utf-8-sig")
    
    # 合并日频数据
    daily = pd.merge(index_df.reset_index(), nav_df.reset_index(), on="date", how="outer").sort_values("date").set_index("date")
    
    # 按配置的基准日进行归一化
    base_date = pd.to_datetime(config.BASE_DATE)
    if base_date is not None:
        ib = None
        nb = None
        if "reits_index" in index_df.columns:
            idx_before = index_df.loc[index_df.index <= base_date, "reits_index"]
            if not idx_before.empty:
                ib = idx_before.iloc[-1]
        if nav_df is not None and "nav" in nav_df.columns:
            nav_before = nav_df.loc[nav_df.index <= base_date, "nav"]
            if not nav_before.empty:
                nb = nav_before.iloc[-1]
        if ib is not None and not pd.isna(ib) and "reits_index" in daily.columns:
            daily["reits_index_norm"] = daily["reits_index"] / ib
        if nb is not None and not pd.isna(nb) and "nav" in daily.columns:
            daily["nav_norm"] = daily["nav"] / nb
        if "nav_norm" in daily.columns and "reits_index_norm" in daily.columns:
            daily["excess"] = daily["nav_norm"] - daily["reits_index_norm"]
            daily["excess_pct"] = daily["excess"] * 100
    
    daily.to_csv(os.path.join(config.DATA_PROCESSED_DIR,"daily.csv"), encoding="utf-8-sig")
    
    # 给交易数据添加板块信息
    if trades_df is not None and "sector" in reits_info.columns:
        trades_df["sector"] = trades_df["code"].map(reits_info.set_index("code")["sector"].to_dict())
    
    print("\n" + "=" * 60)
    print("✅ 数据加载完成！")
    print("=" * 60)
    
    return reits_info, daily, nav_df, trades_df, holdings_df, weight_df


if __name__ == "__main__":
    reits_info, daily, nav_df, trades_df, holdings_df, weight_df = align_and_save()
    print(f"\n📊 数据概览：")
    print(f"  REITs 信息：{len(reits_info)} 条")
    if "sector" in reits_info.columns:
        print(f"    板块：{sorted(reits_info['sector'].dropna().unique().tolist())}")
    print(f"  日频数据：{daily.shape}, 日期：{daily.index.min().date()} ~ {daily.index.max().date()}")
    if nav_df is not None:
        print(f"  净值数据：{nav_df.shape}, 日期：{nav_df.index.min().date()} ~ {nav_df.index.max().date()}")
    if trades_df is not None:
        print(f"  交易数据：{trades_df.shape}, 日期：{trades_df['date'].min().date()} ~ {trades_df['date'].max().date()}")
        print(f"    交易类型分布:\n{trades_df['direction'].value_counts()}")
    if holdings_df is not None:
        print(f"  持仓数据：{holdings_df.shape}")
        print(f"    持仓日期：{holdings_df['date'].iloc[0] if 'date' in holdings_df.columns else 'N/A'}")
        print(f"    权重合计：{holdings_df['weight'].sum():.2%}" if 'weight' in holdings_df.columns else "    权重合计：N/A")
    if weight_df is not None:
        print(f"  指数权重：{weight_df['weight'].sum():.2%}")
