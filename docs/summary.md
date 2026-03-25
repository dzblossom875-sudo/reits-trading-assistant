# 📄 最终结论快照

> 只记录经过验证的最终规则和最佳实践，不记录过程。

---

## 核心规则

### 数据加载
- **交易文件匹配**：使用 `"统计分析*交易查询*"` 匹配 csv/xlsx，避免空格敏感
- **列映射优先级**：精确匹配优先于模糊匹配
  - `"业务日期"` > `"日期"`
  - `"成交金额"` > `"全价成交金额"`
- **编码处理**：交易类别字段需用 `latin1` → `gbk` 解码

### 交易方向判断
- **交割金额为正** = 卖出（资金流入）
- **交割金额为负** = 买入（资金流出）
- **交易类别含"红利"/"分红"** = 红利到账

### Heavy Buy/Sell 定义
- **Heavy Buy**：日净买入金额 > 正净买入的 75 分位数
- **Heavy Sell**：日净卖出金额 < 负净卖出的 75 分位数（绝对值）

### 收益率计算
- **区间总收益率**：(期末 / 期初 - 1) × 100%
- **年化收益率**：(1 + 总收益)^(365/天数) - 1
- **年化波动率**：日收益率.std() × √252
- **夏普比率**：(年化收益 - 1.85%) / 年化波动，账户和指数统一计算
- **最大回撤**：max((峰值 - 当前)/峰值)

### 分月收益
- **公式**：(本月末净值 / 上月末净值 - 1) × 100%
- **起点**：上月最后一个交易日的净值
- **终点**：本月最后一个交易日的净值

### 仓位计算
- **持仓市值**：当日所有持仓行市值加总（列43=本币持仓市值）
- **净资产**：日报表"净资产（市值）"列
- **仓位比例**：持仓市值 / 净资产 × 100%
- **⚠️ 子账户去重**：持仓 CSV 同一证券在多个子账户各有一行，必须先 `groupby(['date','code']).sum()` 文件内聚合，再跨文件 dedup；直接 `drop_duplicates(keep='last')` 丢失 ~63% 市值
- **历史/计算切换点**：`≤ 2026-03-06` 用 history data 仓位，`> 2026-03-06` 用持仓查询文件计算
- **验算缓存**：每次运行重算重叠段（末5天）验证缓存正确性，差异 > 0.3% 触发全量重建

---

## 避坑指南

### Excel 数据处理
- 列名可能包含隐藏字符，匹配前用 `.strip()` 清洗
- 同名/相似名列需用精确匹配，避免顺序依赖
- 日期字段可能有多个（业务日期、结算日期、费用结算日期），需精确匹配

### Python 数据处理
- DataFrame.attrs 可用于传递元数据，但需检查属性存在性
- 多空信号阈值应分别计算，不能简单用绝对值对称处理
- 胜率统计需检查样本数是否为 0，避免除零或空值

### Git 与路径
- Windows 中文路径 glob 需用正斜杠或 `os.path.join()` 避免转义问题
- f-string 不能包含未转义的大括号，跨行时注意引号匹配

### Streamlit Dashboard（2026-03-22 更新）
- **双轴归一化锚点**：归一化除数必须从完整数据集找，不能从已裁切的时间窗口找，否则当显示起点晚于基准日时锚点漂移
- **双轴 Y 轴压缩**：Plotly 双轴图中若主轴（左）不设 range，会与副轴互相压缩；两轴均应手动设 range
- **柱状图右轴 range**：用 `np.percentile(abs_vals, 95)` 代替 max，避免单个极值把所有普通柱压扁
- **`st.date_input` 返回 None**：用户清空输入框时返回 None，`pd.to_datetime(None)` 无法与 DatetimeIndex 比较 → 全部日期控件加 `if x else 默认值` 兜底再统一转换
- **`use_container_width`**：Streamlit 已废弃，统一改为 `width='stretch'`
- **parquet monthly 单位**：`performance_summary_monthly.parquet` 的 `nav_return`/`idx_return` 已是百分比值（如 4.807 = 4.807%），不可再乘 100

### Dashboard 配色规范（2026-03-22 补充）
- **主题隔离**：User(Cloud Blue) 与 Company(平安集团) 两套主题，bull/bear/pos/nav/idx 五类颜色独立定义
- **User bull_color 必须用蓝系**：User 主题下 bull_color 若用绿色，视觉上与平安绿几乎相同，用户无法区分；固定用 `#1a6ca0`（钢蓝）
- **气泡图/散点图多类别**：连续色阶会使数值相近的类别颜色重叠，多板块场景必须改用 `_bubble_palette`（分类色）逐个分配颜色
- **面积填充透明度**：背景浅色主题下，fill opacity < 0.15 几乎不可见，推荐 0.18~0.25
- **全局字体变量**：所有 legend/tickfont/title_font 统一引用 `_font9 = dict(size=11, color=text_color)`，一处修改全图同步；主题切换后该变量自动带入正确颜色

---

## 最佳实践

### 代码组织
- 配置集中管理（`config.py`），避免硬编码
- 数据加载与业务分析分离，便于单元测试
- 图表使用 `matplotlib.use("Agg")` 支持无 GUI 环境

### 数据验证
- 加载数据时打印列映射结果，便于快速验证字段识别
- 关键计算前检查空值，使用 `.dropna()` 或条件判断
- 使用 `DataFrame.attrs` 传递阈值、基准日等元数据

### 错误处理
- 文件读取失败返回 `None`，调用处做空值保护
- 异常数据（负数持仓、权重合计异常）打印警告但不中断流程
- 使用 `try/except` 包裹编码转换等易错操作

---

## 图表规范（2026-03-21 更新）

### X 轴日期
- 统一使用 `_apply_date_format(ax)` helper（`AutoDateLocator + ConciseDateFormatter`）
- 自动选择间隔粒度，标注到日

### 净值/指数对齐
- 找两线共同第一个有效日期，在该日统一归一化到1.0
- 不依赖各自起始日独立归一化

### 仓位图
- 使用 `fill_between` 面积图
- 单日变动>10ppt 标注 `异常XX%`（不用 Unicode 符号，SimHei 不支持）

### 板块表现图
- 有行情数据：散点气泡图（X=区间涨跌幅, Y=净买入万, 气泡=交易量, 四象限中文标注）
- 无行情数据：左右并排水平柱状图

---

## Parquet 防腐层（2026-03-22 新增）

为支持 Streamlit Dashboard 独立运行，所有核心数据同时输出到固定路径 `data/processed/*.parquet`：

| 文件 | 来源 | 用途 |
|------|------|------|
| `daily_master.parquet` | `save_merged_daily()` | 主表（净值/指数/仓位/交易），1213天 |
| `allocation_bias_sector.parquet` | `save_allocation_bias()` | 板块配置偏移 |
| `allocation_bias_detail.parquet` | `save_allocation_bias()` | 个券配置偏移 |
| `performance_summary_metrics.parquet` | `save_performance_summary()` | 总体指标（转置格式） |
| `performance_summary_monthly.parquet` | `save_performance_summary()` | 分月表现 |

### 非交易日插值规则（daily_master）
- **净值、仓位**：沿用前一交易日（ffill）
- **仓位变动**：基于 ffill 后的仓位逐日重新计算 diff
- **买入/卖出/红利/净买入**：非交易日保持 NaN（不插值）

---

## Streamlit Dashboard（2026-03-22 新增）

交互式看板 `dashboard.py`，6大模块：
1. **核心趋势归因**：净值 vs 指数 + 超额面积图
2. **调仓意图扫描仪**：仓位变动 ppt（柱状图）
3. **实际仓位水位**：仓位面积图 + 指数对照
4. **板块配置偏移**：水平柱状图（超配/低配）
5. **分月表现对比**：账户 vs 指数（分组柱状图）
6. **板块操作归因**：气泡图四象限诊断（买对了/卖对了/买套了/卖飞了）

**启动命令**：
```bash
streamlit run dashboard.py
```

### Dashboard 模块详细配置

#### 模块1：核心趋势归因（净值 vs 指数 + 超额）
- **数据源**：`daily_master.parquet`
- **计算逻辑**：
  - 以用户选择基准日的净值/指数为起点，归一化为 1.0
  - 超额 = (账户净值归一化 - 指数归一化) × 100%
- **图表元素**：
  - 正超额：红色半透明面积图（tozeroy）
  - 负超额：绿色半透明面积图
  - 净值线：红色实线（#d62728，宽度3）
  - 指数线：蓝色实线（#1f77b4，宽度3）
- **交互**：hover 显示具体数值，X轴日期联动

#### 模块2：调仓意图扫描仪（仓位变动 ppt）
- **数据源**：`daily_master.parquet` 中的 `仓位变动` 列
- **计算逻辑**：
  - 仓位变动 = 当日仓位 - 前一日仓位（单位：ppt，即 0.01 = 1%）
  - 基于 ffill 后的仓位逐日重算，非交易日也有变动值
- **图表元素**：
  - 指数背景线：黑色（#1a1a1a）
  - 加仓柱：红色（#d62728，正值）
  - 减仓柱：蓝色（#1f77b4，负值）
  - 右轴范围对称：±max(|变动|) × 2

#### 模块3：实际仓位水位
- **数据源**：`daily_master.parquet` 中的 `仓位` 列
- **图表元素**：
  - 仓位面积：浅蓝色填充（rgba(93, 173, 226, 0.2)）
  - 指数对照线：黑色虚线
  - Y轴自适应：最小值 max(0, 最小仓位-5%)，最大值 最大仓位+5%

#### 模块4：板块配置偏移
- **数据源**：`allocation_bias_sector.parquet`
- **计算逻辑**：账户权重 - 指数权重
- **图表元素**：
  - 超配（正偏移）：红色柱（#d62728）
  - 低配（负偏移）：绿色柱（#2ca02c）
  - 零线：黑色实线
  - 水平排列：板块名在 Y 轴

#### 模块5：分月表现对比
- **数据源**：`performance_summary_monthly.parquet`
- **过滤**：排除含"至今"的汇总行，只显示自然月
- **图表元素**：
  - 账户收益：红色柱（原始值×100，单位%）
  - 指数收益：蓝色柱
  - 分组模式（barmode='group'）

#### 模块6：板块操作归因气泡图
- **数据源**：
  - 涨跌幅：`wind_prices_cache.csv`（区间首尾日计算）
  - 净买入：`trades_clean.csv`（区间汇总）
  - 板块映射：`reits_info.csv`
- **计算逻辑**：
  - X轴：板块区间涨跌幅（%）
  - Y轴：板块区间净买入（万元，买入为正，卖出为负）
  - 气泡大小：sqrt(总交易量) × 0.5 + 6
  - 气泡颜色：涨跌幅（RdYlGn_r 色阶，红跌绿涨）
- **四象限标注**：
  - 右上（+涨/+买）：【买对了】
  - 左上（-涨/+买）：【买套了】
  - 右下（+涨/-买）：【卖飞了】
  - 左下（-涨/-买）：【卖对了】

### Dashboard 侧边栏控制
- **业绩归一化基准日**：影响模块1的起算点，默认 2026-01-01
- **复盘分析区间**：影响模块2、3、6的时间范围，默认全部数据

### Dashboard 与主程序的关系
```
main.py ──► data/processed/*.parquet ──► dashboard.py
 (生成)                                    (消费)
```
- Dashboard **不依赖** `output/YYYYMMDD/` 下的文件
- Dashboard **只读** `data/processed/*.parquet` 和 `data/processed/*.csv`
- 运行 Dashboard 前必须先运行 `main.py` 生成 Parquet 文件

---

## 输出文件清单（2026-03-22 更新）

| 文件 | 内容 | 备注 |
|------|------|------|
| `daily_master.xlsx` | 历史+计算完整主表（2022-11-24起），含交易数据 | 831行，13列 |
| `performance_summary.xlsx` | 业绩指标（总体+分月） | — |
| `daily_tracking.xlsx` | 日频净值+仓位（BASE_DATE起） | 80行 |
| `trade_summary.xlsx` | 逐日交易汇总+红利明细 | — |
| `allocation_bias.xlsx` | 配置偏移（个券+板块） | — |
| `timing_analysis.xlsx` | 择时事件+胜率统计 | — |

> 已移除：`full_series.csv`（内容含于daily_master）、`tracking_and_history.xlsx`（内容含于其他文件）、`validation_history_vs_calc.xlsx`（验证通过后无需保留）

### daily_master.xlsx 列结构
```
日期 | 资产净值(万) | 指数绝对值 | 指数(基准2022-11-24) | 净值(基准2022-11-24)
   | 超额 | 仓位 | 仓位变动 | 买入(万) | 卖出(万) | 红利(万) | 净买入(万)
   | 交易笔数 | 信号
```
- 历史段（2022-11-24~2025-12-31）：交易列为 NaN
- 计算段（2026-01-05起）：全列有值

---

## Wind 行情缓存

- 缓存路径：`data/processed/wind_prices_cache.csv`
- 增量更新：每次只拉取缓存 max_date 后的新增日期
- 强制全量刷新：删除缓存文件后重新运行

---

## 已知限制

1. **持仓权重 97.14% ≠ 100%**：原始数据存在现金/其他资产，未完全满仓
2. **Wind API 依赖**：个股行情优先从 Wind 获取，失败时回退缓存或本地文件
3. **仓位计算失真风险**：持仓文件非每日更新时，`ffill()` 导致仓位显示为阶梯形
4. **交易日历**：波动率按连续交易日计算（×√252），未剔除节假日

---

## 常用命令

```bash
# 运行主程序（需加编码变量，避免 GBK 崩溃）
PYTHONIOENCODING=utf-8 D:/install/python.exe main.py

# 查看最新输出目录
ls output/$(ls -t output | head -1)/

# 检查交易方向分布
python -c "import pandas as pd; df = pd.read_csv('data/processed/trades_clean.csv'); print(df['direction'].value_counts())"

# 强制刷新 Wind 行情缓存
rm data/processed/wind_prices_cache.csv
```

---

*最后更新：2026-03-22 00:00*
