# 数据文件路径配置
import os
from datetime import datetime

# 基础路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
DATA_PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")

# 输出目录按日期时间生成（避免覆盖）
RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", RUN_TIMESTAMP)
OUTPUT_FIGURES_DIR = os.path.join(OUTPUT_DIR, "figures")
OUTPUT_REPORTS_DIR = os.path.join(OUTPUT_DIR, "reports")

# 文件名配置（根据实际文件名调整）
FILE_REITS_INFO = "沪深REITs.xlsx"
FILE_INDEX = "指数.xlsx"  # 中证 REITs 全收益指数
FILE_WEIGHT_932006 = "932006closeweight.xlsx"  # 932006收盘价指数权重
FILE_HOLDINGS = "统计分析-持仓查询-组合持仓查询*.xlsx"  # 持仓查询文件（支持通配符，取最新）
FILE_LOCAL_PRICES = "行情数据251231至今.xlsx"         # 本地个股行情（Wind回退）

# 日报表配置：自动读取input目录下最新日期的日报表
DAILY_REPORT_PATTERN = "日报表_*.xlsx"

# 交易所成交查询文件（优先使用）
FILE_EXCHANGE_TRADES = "统计分析-交易查询*.csv"

# Sheet 名配置
SHEET_NAV = "净值时间序列"
SHEET_TRADES = "交易明细表"  # 日报表中的交易明细sheet
SHEET_HOLDINGS = "sheet1"  # 持仓查询sheet名

# 账户配置
ACCOUNT_NAME = "中诚信托-明珠76号"  # 用于报表表头显示

# 基准日配置（用于归一化和图表起始）
BASE_DATE = "2025-12-31"  # 格式：YYYY-MM-DD

# Wind API配置
USE_WIND_API = True   # 优先使用Wind API获取行情，失败自动回退本地文件
WIND_CACHE_DAYS = 1  # Wind数据缓存天数

# 证券代码处理
REITS_CODE_LENGTH = 6  # 统一为 6 位数字

# 日期格式
DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y%m%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
]

# 板块标准化映射
SECTOR_SYNONYMS = {
    "产业园": "产业园区",
    "产业园区": "产业园区",
    "仓储物流": "仓储物流",
    "物流": "仓储物流",
    "能源": "能源",
    "新能源": "能源",
    "保障房": "保障房",
    "保障性租赁住房": "保障房",
    "高速公路": "高速公路",
    "高速": "高速公路",
    "环保": "环保",
    "水务": "环保",
}

# 确保目录存在
for d in [DATA_PROCESSED_DIR, OUTPUT_FIGURES_DIR, OUTPUT_REPORTS_DIR]:
    os.makedirs(d, exist_ok=True)
