# REITs 交易助手 - 开发需求文档（指定数据源版）

## 项目目标
构建一个 REITs 交易分析助手，基于用户提供的本地数据源，实现交易行为复盘、择时分析、板块轮动分析，并生成可视化报告。

---

## 数据源说明（核心）

### 文件夹在

### 1. 沪深 REITs 表（板块分类数据）
**文件**：`data/沪深 REITs 表.xlsx` 或 `data/沪深 REITs 表.csv`
**用途**：证券代码与板块分类映射
**关键字段**：
- 证券代码（如 508000.SH, 180101.SZ）
- 证券名称
- 项目类型（即板块分类：产业园/仓储物流/能源/保障房/高速公路等）

**处理要求**：
- 证券代码清洗：去除后缀（.SH/.SZ），统一为 6 位数字
- 项目类型标准化：合并同义词（如"产业园"="产业园区"）

---

### 2. 指数.xlsx（基准指数数据）
**文件**：`data/指数.xlsx`
**Sheet 名**：需确认（可能是"中证 REITs 全收益指数"或类似）
**关键字段**：
- 日期
- 中证 REITs 全收益指数收盘价/净值
- 指数涨跌幅

**处理要求**：
- 日期格式统一（YYYY-MM-DD）
- 与交易数据日期对齐

---

### 3. 日报表_中诚信托 - 明珠 76 号（账户净值数据）
**文件**：`data/日报表_中诚信托 - 明珠 76 号.xlsx`
**Sheet 名**：`净值时间序列`
**关键字段**：
- 日期
- 累计单位净值

**用途**：
- 计算账户整体收益曲线
- 与指数对比分析

**处理要求**：
- 日期格式统一
- 处理可能的缺失日期（向前填充）

---

### 4. 统计分析 - 交易查询（交易数据）
**文件**：`data/统计分析 - 交易查询.xlsx`
**Sheet 名**：需确认（可能是"交易查询"或"交易明细"）
**关键字段**：
- 证券代码（数字一致即可，如 508000）
- 成交数量（委托方向字段标识买卖方向）
- 成交金额
- 成交日期（需确认字段名）

**用途**：
- 交易行为复盘（加减仓、个券调整）
- 择时分析（交易时点 vs 指数走势）

**处理要求**：
- 证券代码对齐（与沪深 REITs 表匹配）
- 买卖方向识别（根据成交数量正负或单独字段）
- 日期格式统一

---

## 核心功能模块

### 模块 1：数据加载与清洗
**任务**：
1. 读取上述 4 个数据源
2. 数据清洗：
   - 日期格式统一（YYYY-MM-DD）
   - 证券代码统一（6 位数字，去除后缀）
   - 处理缺失值、异常值
   - 处理分隔符问题（CSV 可能有，/，; 等）
3. 数据对齐：
   - 以交易日期为基准
   - 对齐指数数据、净值数据
   - 输出统一格式的 DataFrame

**输出**：
- `data/processed/reits_info.csv` - REITs 基础信息（代码、名称、板块）
- `data/processed/daily.csv` - 指数日频原数据，账户净值日频原数据，指数vs账户（以2025年最后一个交易日作为原点对齐）
- `data/processed/nav_daily.csv` - 
- `data/processed/trades_clean.csv` - 清洗后交易数据

---

### 模块 2：板块分类与板块指数计算
**任务**：
1. 根据沪深 REITs 表，将 REITs 按项目类型分组
2. 获取各 REITs 的行情数据（收盘价、市值）
   - **优先**：从用户提供的数据中提取
   - **备选**：提示用户上传行情数据（CSV/Excel）
3. 计算各板块指数：
   - 市值加权（默认）
   - 等权（备选）

**输出**：
- `data/processed/sector_indices.csv` - 各板块指数时间序列
- `output/figures/sector_performance.png` - 板块收益对比图

---

### 模块 3：交易行为复盘
**任务**：
1. 加减仓识别：
   - 读取数据范围为近一个月
   - 按日期汇总净买入/卖出金额
   - 识别大幅加减仓时点（如单日净买入>阈值）
2. 板块调整识别：
   - 按板块汇总交易金额
   - 识别板块轮动方向
3. 个券调整识别：
   - 统计各 REITs 的累计交易金额
   - 识别前十大活跃交易券

**输出**：
- `output/trade_summary.csv` - 交易统计汇总表
- `output/figures/trade_flow.png` - 资金流向图(副坐标轴为期间指数走势)
- `output/figures/sector_rotation.png` - 板块轮动图

---

### 模块 4：择时分析
**任务**：
1. 将交易时点与指数走势叠加
2. 计算每次交易后的指数表现：
   - 加仓后 5 日/10 日/20 日指数涨跌幅
   - 减仓后 5 日/10 日/20 日指数涨跌幅
3. 计算择时效果指标：
   - 胜率（加仓后上涨次数/总加仓次数）
   - 平均收益
   - 最大回撤

**输出**：
- `output/timing_analysis.csv` - 择时效果统计表
- `output/figures/timing_chart.png` - 加减仓时点 vs 指数走势叠加图

---

### 模块 5：账户表现分析
**任务**：
1. 账户净值曲线 vs 指数曲线。（以2025年最后一个交易日作为原点对齐）
2. 计算超额收益
3. 计算风险指标：
   - 年化收益率
   - 波动率
   - 夏普比率
   - 最大回撤

**输出**：
- `output/performance_summary.csv` - 业绩指标汇总表
- `output/figures/nav_vs_index.png` - 净值 vs 指数对比图

---

### 模块 6：报告生成
**任务**：
整合上述分析结果，生成 Markdown 报告

**报告结构**：
```markdown
# REITs 交易分析报告

## 一、核心结论
- 结论 1
- 结论 2
- 结论 3

## 二、账户表现
- 净值曲线图
- 业绩指标表

## 三、交易行为复盘
- 加减仓统计
- 板块轮动图
- 个券调整表

## 四、择时效果评估
- 择时效果统计表
- 加减仓时点图

## 五、板块分析
- 板块收益对比图
- 板块配置建议

## 六、图表附录
```

**输出**：
- `output/report_{date}.md`

---

## 技术栈要求
- **语言**：Python 3.9+
- **核心库**：pandas, numpy, matplotlib, seaborn, openpyxl
- **可视化**：matplotlib/seaborn
- **报告**：Markdown

---

## 项目结构
```
reits_trading_assistant/
├── data/
│   ├── raw/                    # 原始数据（用户放入）
│   │   ├── 沪深 REITs 表.xlsx
│   │   ├── 指数.xlsx
│   │   ├── 日报表_中诚信托 - 明珠 76 号.xlsx
│   │   └── 统计分析 - 交易查询.xlsx
│   └── processed/              # 处理后数据
├── src/
│   ├── data_loader.py          # 数据加载与清洗
│   ├── sector_analysis.py      # 板块分析
│   ├── trade_analysis.py       # 交易分析
│   ├── timing_analysis.py      # 择时分析
│   ├── performance_analysis.py # 业绩分析
│   └── report_generator.py     # 报告生成
├── output/
│   ├── figures/                # 图表
│   └── reports/                # 报告
├── config.py                   # 配置文件路径等
├── main.py                     # 主程序
└── requirements.txt            # 依赖
```

---

## 开发步骤

### 第一步：创建项目结构 + 数据加载模块
```bash
mkdir -p reits_trading_assistant/{data/{raw,processed},src,output/{figures,reports}}
```
创建 `src/data_loader.py`，实现：
- 读取 4 个数据源
- 数据清洗（日期、代码、分隔符）
- 数据对齐
- 输出到 processed 目录

**请先创建此模块，我用测试数据验证**

---

### 第二步：板块分析模块
创建 `src/sector_analysis.py`，实现：
- 读取沪深 REITs 表，建立代码→板块映射
- 计算各板块指数（需要行情数据）
- **注意**：如果无法从现有数据源提取行情，请提示用户上传

---

### 第三步：交易分析模块
创建 `src/trade_analysis.py`，实现：
- 读取交易数据
- 识别加减仓、板块调整、个券调整
- 生成统计汇总表

---

### 第四步：择时分析模块
创建 `src/timing_analysis.py`，实现：
- 交易时点与指数叠加
- 计算择时效果指标
- 生成可视化图表

---

### 第五步：业绩分析模块
创建 `src/performance_analysis.py`，实现：
- 净值曲线 vs 指数曲线
- 计算风险指标

---

### 第六步：报告生成模块
创建 `src/report_generator.py`，实现：
- 整合上述分析结果
- 生成 Markdown 报告

---

### 第七步：主程序整合
创建 `main.py`，串联所有模块

---

## 注意事项

1. **数据清洗优先**：先处理好数据加载模块，确保 4 个数据源能正确读取和对齐
2. **容错处理**：
   - 文件不存在时给出明确提示
   - Sheet 名不确定时，列出所有 Sheet 供用户选择
   - 字段名不确定时，尝试模糊匹配
3. **日期对齐**：以交易数据的日期为基准，其他数据向前/向后填充
4. **证券代码**：统一为 6 位数字（去除.SZ/.SH 后缀）
5. **图表质量**：确保图表清晰、专业，适合投研报告使用
6. **中文支持**：matplotlib 需要配置中文字体（如 中文楷体+英文/数字Arial）

---

## 配置文件模板（`config.py`）

```python
# 数据文件路径配置
DATA_RAW_DIR = "data/raw"
DATA_PROCESSED_DIR = "data/processed"
OUTPUT_DIR = "output"

# 文件名配置（可根据实际文件名调整）
FILE_REITS_INFO = "沪深 REITs 表.xlsx"
FILE_INDEX = "指数.xlsx"
FILE_NAV = "日报表_中诚信托 - 明珠 76 号.xlsx"
FILE_TRADES = "统计分析 - 交易查询.xlsx"

# Sheet 名配置（如不确定，可先列出所有 Sheet）
SHEET_NAV = "净值时间序列"
SHEET_TRADES = "交易查询"  # 待确认

# 证券代码处理
REITS_CODE_LENGTH = 6  # 统一为 6 位数字
```

---

## 数据清洗细节

### 日期格式处理
```python
# 常见日期格式
date_formats = [
    "%Y-%m-%d",      # 2024-01-01
    "%Y/%m/%d",      # 2024/01/01
    "%Y%m%d",        # 20240101
    "%Y-%m-%d %H:%M:%S",  # 2024-01-01 00:00:00
]
```

### 证券代码处理
```python
# 去除后缀
def clean_code(code):
    # 508000.SH -> 508000
    # 180101.SZ -> 180101
    return str(code).split('.')[0].zfill(6)
```

### 分隔符处理
```python
# CSV 可能使用不同分隔符
def read_csv_auto(filepath):
    for sep in [',', '\t', ';', '|']:
        try:
            df = pd.read_csv(filepath, sep=sep)
            if len(df.columns) > 1:
                return df
        except:
            continue
```

---

## 开始开发

**请先完成第一步**：
1. 创建项目结构
2. 创建 `src/data_loader.py`
3. 创建 `config.py`（配置文件路径）
4. 创建 `requirements.txt`

然后告诉我，我会放入测试数据验证数据加载模块。

---

## 使用说明

**将此 prompt 发送给 Claude Code**：

```bash
# 方法 1：直接粘贴
claude-code
# 然后粘贴上述 prompt

# 方法 2：保存为文件后读取
cat > reits_assistant_prompt.md << 'EOF'
[上述 prompt 内容]
EOF
claude-code -f reits_assistant_prompt.md
```

---

**文档版本**：v1.0  
**创建时间**：2026-03-19  
**作者**：Daisy 的 REITs 交易助手项目组
