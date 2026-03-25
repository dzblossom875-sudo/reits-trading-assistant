# 📋 CHANGELOG

> 完整修改历史，每次归档自动追加，禁止修改已有条目。

---

## 2026-03-25 (下午) - `97e2d18`

**工具**：Claude Code

### 分月业绩补全全历史 + load_holdings_timeseries 对齐

#### 分月业绩 (`src/performance_analysis.py`)
- **feat**: `calc_metrics_by_period(full_df=None)` 新增可选参数
- 若传入 `full_df`（含 `nav_norm_full`/`reits_index_norm_full`），自动使用全历史数据计算分月收益（从 2022-11 起，共 42 行；原来只有 4 行）
- 无 `full_df` 时回退到原有 `daily_df["nav"]` 行为（BASE_DATE 之后），向后兼容
- **fix**: `main.py` 传入 `full_df=full_df`

#### 持仓时序 (`src/data_loader.py`)
- **fix**: `load_holdings_timeseries` 重写为委托 `position_calculator.load_holdings_from_raw`
- 支持 xlsx+csv 混合来源（历史 CSV + 当日 xlsx）
- 子账户正确聚合（`groupby.sum()`），3/9 市值从 14,969万 → 40,782万

---

## 2026-03-25 - `da79896`

**工具**：Claude Code

### 仓位计算全面修复 — position_calculator v2.1

#### Bug 修复
- **fix**: 删除错误缓存 `position_cache_v2.parquet`（旧缓存仓位 ~32%，实际应为 ~88-98%）
- **fix**: 根因：旧缓存由不完整持仓数据构建，`drop_duplicates(keep='last')` 仅保留每只证券最后一行，CSV 含两行子账户数据时丢失 ~63% 市值

#### 核心重构 (`src/position_calculator.py` v2.1)
- **feat**: 文件内聚合 — 每个文件读取后先 `groupby(['date','code']).sum()`，确保跨子账户市值求和
- **feat**: 跨文件去重 — xlsx（完整组合视图）优先于 csv（历史明细），`keep='first'` 保留 xlsx
- **feat**: 验算驱动缓存 — 每次运行：读缓存 → 从原始文件重新计算 → 验算重叠段（末尾5天，容忍2%）→ 通过则增量追加，失败则全量重建
- **fix**: `calculate_position_from_holdings` 改为仅用交易日（持仓有记录的日期）作为索引，避免非交易日产生 NaN 行

#### 验证结果
- 计算段（3/9-3/24）仓位 86.9%-95.8%，与 history_df 差异 ≤1.2个百分点 ✓
- 3/6→3/9 切换点连续（88.2%→86.9%），无断层 ✓
- 第二次运行：验算通过（5天重叠，最大差异 0.0000），增量逻辑正常 ✓

---

## 2026-03-22 (下午) - `0c8528c`

**工具**：Claude Code

### Dashboard 视觉全面优化

#### 配色区分
- **fix**: User 模式 `bull_color` 从 `#00806a`（祖母绿，与平安绿 `#007D5E` 视觉相同）改为 `#1a6ca0`（钢蓝），两套主题板块偏移柱状图颜色明显区分
- **feat**: 图六气泡图从连续色阶（`colorscale="RdYlGn_r"`）改为按板块分类着色（`_bubble_palette` 10色列表），消除涨跌幅相近板块颜色相同问题
- **feat**: 各主题独立 `_bubble_palette`（User: 蓝/橙/绿/紫系；Company: 橙/绿/蓝/紫系）

#### 饱和度与对比度
- **fix**: `excess_fill` 透明度 `0.08/0.10` → `0.18`，超额面积在浅色背景下清晰可见
- **fix**: `pos_fill` 透明度 `0.12` → `0.22`，仓位水位面积图轮廓更明确
- **fix**: User `idx_color` `#5a7aa0` → `#4a78b8`，指数折线饱和度提升
- **fix**: Company `idx_color` `#7A7A7A` → `#909090`，灰色指数线在白底上可读性更好

#### 布局一致性
- **fix**: 图四（仓位水位）指数线颜色/粗细与图三（调仓）统一（`text_color, width=2.5`）
- **fix**: 图六右边距 `r=10` → `r=60`，与其他所有图表左右对齐

#### 字体统一
- **feat**: 新增全局字体变量 `_font9 = dict(size=11, color=text_color)`，随主题切换自动更新
- **feat**: 所有图表（图一~六）的图例、坐标轴标题、刻度标签统一应用 `_font9`，告别各图字号不一致

#### 关联文件
- `reits_trading_assistant/dashboard.py`

---

## 2026-03-22 02:00 - `(本次提交)`

**工具**：Claude Code

### Dashboard 全面重构（bug修复 + 交互升级）

#### Bug 修复
- **fix**: Sharpe 指标卡 `perf_metrics.loc[mask][0, col]` 无效双重索引 → CRASH，改用 `.index[mask][0]` 先取行名再 `.loc`
- **fix**: `perf_monthly['nav_return'] * 100` 双重乘100（数据已是%值），图五月度柱状图数值错误（显示480%→4.8%）
- **fix**: 归一化锚点漂移 — 当 `fig1_start > fig1_base` 时，从裁切后的 `df_p1` 里找锚点会漂移到 fig1_start，导致基准日处净值≠1.0；改为始终从完整 `df` 里找锚点
- **fix**: `if sd and ed` NaT 检查无效（Timestamp 永远 truthy），改为 `pd.notna(sd) and pd.notna(ed)`
- **fix**: `date_input` 清空返回 `None` 导致 `pd.to_datetime(None)` 与 DatetimeIndex 比较崩溃，全部日期变量加 `if x else 默认值` 兜底

#### 交互升级
- **feat**: 侧边栏拆为两个独立区块：「图一：核心趋势」（起始日 + 归一化基准日）与「图二~六：区间分析」（起始日 + 结束日），互不干扰
- **feat**: 顶部四张指标卡（总收益/年化/最大回撤/夏普）改为动态计算，跟随图一归一化基准日联动，delta 行显示同期指数对应值

#### 图表优化
- **fix**: 图二图三双轴长周期压缩 — 左轴（指数）手动设置 range（与图一逻辑统一），右轴改用第 95 分位数定高度避免单点大值将其余柱压扁
- **feat**: 图一左轴默认 range 模拟 Autoscale 按钮效果（手动计算 min/max + 5% padding）
- **feat**: 全部图表图例统一移至底部居中（`y=-0.12, x=0.5`），图四/六单 trace 图设 `showlegend=False`
- **fix**: `use_container_width=True` → `width='stretch'`，消除 Streamlit 弃用警告刷屏

#### 关联文件
- `reits_trading_assistant/dashboard.py`

---

## 2026-03-22 00:00 - `36954b5`

**工具**：Claude Code

### Parquet 防腐层建立（架构升级）
- **feat(data_loader)**: `save_merged_daily()` 新增非交易日插值逻辑
  - 净值、仓位数据：非交易日沿用前一交易日（ffill）
  - 仓位变动：基于 ffill 后的仓位逐日重新计算 diff
  - 买入/卖出/红利/净买入：非交易日保持 NaN（不插值）
  - 输出 `daily_master.parquet` 到 `data/processed/` 固定路径
- **feat(allocation_analysis)**: `save_allocation_bias()` 新增 Parquet 输出
  - `allocation_bias_sector.parquet`（板块偏移）
  - `allocation_bias_detail.parquet`（个券偏移）
  - 保存前执行 `.ffill()` 保证数据连贯性
- **feat(performance_analysis)**: `save_performance_summary()` 新增 Parquet 输出
  - `performance_summary_metrics.parquet`（总体指标，转置格式）
  - `performance_summary_monthly.parquet`（分月表现）
  - 过滤单日月份（如 2025-12-31 至 2025-12-31）

### 数据修正
- **fix(trade_analysis)**: `save_trade_summary()` 删除"持仓市值(万)"列（数据不准确）
- **fix(performance_analysis)**: `calc_metrics_by_period()` 跳过起止日期相同的单月记录

### Streamlit Dashboard（新增模块）
- **feat**: 新增 `dashboard.py` 交互式看板，6大模块：
  1. 核心趋势归因（净值 vs 指数 + 超额面积图）
  2. 调仓意图扫描仪（仓位变动 ppt）
  3. 实际仓位水位监控
  4. 板块配置偏移（水平柱状图）
  5. 分月表现对比
  6. 板块操作归因气泡图（四象限诊断）
- **feat**: 所有数据源改为从 `data/processed/*.parquet` 读取，不再依赖带时间戳的输出目录

### 关联文件
- `reits_trading_assistant/src/data_loader.py`
- `reits_trading_assistant/src/allocation_analysis.py`
- `reits_trading_assistant/src/performance_analysis.py`
- `reits_trading_assistant/src/trade_analysis.py`
- `reits_trading_assistant/dashboard.py`

---

## 2026-03-21 20:40 - 分支合并归档

**工具**：Claude Code

### 分支管理
- `review/fix-data-loader` fast-forward 合并至 `main`（`607e96c`）
- 本地分支 `review/fix-data-loader` 已删除
- 远程分支 `origin/review/fix-data-loader` 保留（未推送 main）

---

## 2026-03-21 20:10 - `6a81ae5`

**工具**：Claude Code

### 清理重复输出
- **chore(main)**: 移除 `full_series.csv`（内容已含于 `daily_master.xlsx`）
- **chore(main)**: 移除 `tracking_and_history.xlsx`（内容已含于其他文件）
- **chore(main)**: 移除 `validation_history_vs_calc.xlsx`（验证已通过，改为仅打印控制台摘要）

### 关联文件
- `reits_trading_assistant/main.py`

---

## 2026-03-21 19:45 - `7fcc34d`

**工具**：Claude Code

### 修复与新增
- **fix(data_loader)**: `build_full_series()` 历史段 `reits_index_abs` 从 `daily_df["reits_index"]` 回填（原 history data.xlsx 该列为空）
- **fix(data_loader)**: `build_full_series()` 仓位数据切换：≤2026-03-06 用 history_df，之后用测算数据（持仓市值/净资产）；仓位变动以历史末日为锚点重新差分
- **feat(data_loader)**: 新增 `save_combined_excel()`，输出 `tracking_and_history.xlsx`（两 sheet：逐日跟踪2026起 + 全历史2022起，列结构统一为7列中文）

### 关联文件
- `reits_trading_assistant/src/data_loader.py`
- `reits_trading_assistant/main.py`

---

## 2026-03-21 19:10 - `d4520fd`

**工具**：Claude Code

### 格式统一
- **feat(trade_analysis)**: `trade_summary.xlsx` 日度汇总列名全部翻译：`date→日期`、`buy_amount→买入(万)`、`sell_amount→卖出(万)`、`dividend_amount→红利(万)`、`net_amount→净买入(万)`、`trade_count→交易笔数`、`signal→信号`；signal 值汉化：`heavy_buy→大幅加仓`、`heavy_sell→大幅减仓`、`neutral→中性`；红利明细 sheet 列名翻译
- **feat(allocation_analysis)**: `allocation_bias.xlsx` 个券/板块 sheet 列名翻译：`code→证券代码`、`name→证券名称`、`sector→板块`、`account_weight→账户权重`、`index_weight→指数权重`、`weight_bias→偏移`
- **feat(timing_analysis)**: `timing_analysis.xlsx` 择时明细列名翻译：`date→日期`、`signal→信号`、`net_amount_wan→净买入(万)`、`ret_5d→后5日收益(%)`等；信号值同步汉化
- **feat(performance_analysis)**: `daily_tracking.xlsx` 日期索引由 Timestamp 改为 `YYYY-MM-DD` 字符串（使用 copy 写出，不影响返回值的 DatetimeIndex）
- **feat(data_loader)**: `daily_master.xlsx` 日期索引同上

### 关联文件
- `reits_trading_assistant/src/trade_analysis.py`
- `reits_trading_assistant/src/allocation_analysis.py`
- `reits_trading_assistant/src/timing_analysis.py`
- `reits_trading_assistant/src/performance_analysis.py`
- `reits_trading_assistant/src/data_loader.py`

---

## 2026-03-21 18:23 - `0f82088`

**工具**：Claude Code

### 新增功能
- **feat(data_loader)**: 新增 `save_merged_daily()` — 将 `full_series`（历史+计算）与 `daily_trades`（交易汇总）合并为 `daily_master.xlsx`
- **feat(data_loader)**: `build_full_series()` 扩展新增列：`reits_index_abs`（指数绝对值）、`position_change`（仓位变动，接历史末尾锚点差分）
- **output**: `daily_master.xlsx`，831天，13列，结构与 `history data.xlsx` 同构

### 关联文件
- `reits_trading_assistant/src/data_loader.py`
- `reits_trading_assistant/main.py`

---

## 2026-03-21 18:12 - `3991d37`

**工具**：Claude Code

### 修复问题
- **fix(data_loader)**: `load_history_data()` 兼容新增列结构
  - 原硬编码7列列名赋值，文件扩展到14列后报 `ValueError: Length mismatch`
  - 改为位置字典映射 + `if k < len(df.columns)` 边界保护，自动适配任意列数

### 关联文件
- `reits_trading_assistant/src/data_loader.py`

---

## 2026-03-21 18:09 - `df68c7b`

**工具**：Claude Code

### 新增功能
- **feat(data_loader)**: 新增 `load_history_data()` — 读取 `history data.xlsx`（802条，2022-11-24起），位置映射14列，处理列名含换行符问题
- **feat(data_loader)**: 新增 `build_full_series()` — BASE_DATE对齐，历史段直接使用，计算段 rescale，输出 `full_series.csv`（831天）
- **feat(data_loader)**: 新增 `validate_history_vs_calc()` — 2026+共48天对比验证，净值/指数/净资产差异全为0
- **feat(performance_analysis)**: `save_daily_tracking()` 新增 `净资产(万)` / `持仓市值(万)` 列，百分比保留两位小数
- **feat**: 所有金额输出统一万元单位

### 关联文件
- `reits_trading_assistant/src/data_loader.py`
- `reits_trading_assistant/src/performance_analysis.py`
- `reits_trading_assistant/config.py`（新增 `FILE_HISTORY_DATA`、`SHEET_HISTORY_DATA`）
- `reits_trading_assistant/main.py`

---

## 2026-03-21 17:57 - `bad6117`

**工具**：Claude Code

### 新增功能
- **feat(wind_data_loader)**: Wind 行情增量缓存
  - 缓存路径：`data/processed/wind_prices_cache.csv`
  - 每次运行读缓存 → 找 max_date → 只拉 `(max_date+1)~today` → 合并去重保存
  - 无缓存时全量拉取（起始 2024-01-01）；Wind 失败时回退现有缓存

### 关联文件
- `reits_trading_assistant/src/wind_data_loader.py`

---

## 2026-03-21 15:24 - `aabb4b7`

**工具**：Claude Code

### 新增功能与修复
- **feat(performance)**: `plot_nav_vs_index()` 找共同起始日统一归一化到1.0，解决起点错位
- **feat**: 所有图表 X 轴改用 `AutoDateLocator + ConciseDateFormatter`，标注精确到日，封装为 `_apply_date_format(ax)`
- **feat(trade)**: `plot_position_vs_index()` 仓位改 `fill_between` 面积图；打印每日计算过程；单日变动>10ppt 标注 `异常XX%`；`input()` 询问是否排除（EOFError 默认保留）
- **feat(sector)**: `plot_sector_performance()` 有行情时改散点气泡图（X=涨跌幅,Y=净买入,气泡=交易量,四象限中文标注【买对了】等）；无行情时改左右并排水平柱状图

### 修复 Bug
- **fix**: SimHei 字体不含 Unicode 符号（✓ ✗ ⚠️），改用纯中文【】包裹，消除方块乱码
- **fix**: `input()` 在管道/重定向下抛 `EOFError`，改用 try/except 默认保留
- **fix**: Windows GBK 终端运行需加 `PYTHONIOENCODING=utf-8`

### 关联文件
- `reits_trading_assistant/src/performance_analysis.py`
- `reits_trading_assistant/src/trade_analysis.py`
- `reits_trading_assistant/src/sector_analysis.py`

---

## 2026-03-21 11:38 - 文档归档（MEMORY）

**工具**: Cursor

### 文档
- **docs**: 同步 `MEMORY.md` 当前状态与开发日志（持仓通配符、日度零值填充、`ME` 重采样）

---

## 2026-03-21 - `7e9c03a` / `dc334ec`

**工具**: Cursor

### 修复与优化
- **fix(data_loader)**: 持仓查询文件名支持通配符 `统计分析-持仓查询-组合持仓查询*.xlsx`，读取修改时间最新的文件
- **fix(data_loader)**: `load_holdings_timeseries` 日度总市值为 0 时按上一有效日前向填充，缓解导出缺行导致的假零仓位
- **fix(sector_analysis)**: 月度重采样 `resample('M')` → `resample('ME')`，消除 pandas 弃用警告

### 关联文件
- `reits_trading_assistant/config.py`
- `reits_trading_assistant/src/data_loader.py`
- `reits_trading_assistant/src/sector_analysis.py`

---

## 2026-03-21 - `5ddf351`

**工具**: Cursor

### 新增功能
- **feat(performance)**: 新增 `save_daily_tracking()` 逐日跟踪表（归一化净值+仓位，非交易日前值填充）
- **feat(performance)**: 新增 `plot_position_change_vs_index()` 仓位变动 vs 指数图
- **feat(trade)**: 新增 `plot_net_buy_vs_index()` 净买入 vs 指数图
- **feat(trade)**: `summarize_trades()` 增加 `position_change` 仓位变动列
- **feat(performance)**: 指数夏普比率计算（原仅账户），Rf 统一为 1.85%

### 修复问题
- **fix(trade_analysis)**: `plot_trade_flow()` 左右轴互换（左=指数加粗，右=买卖）
- **fix(report_generator)**: 报告无数据 - 改为 `generate_report(**kwargs)` 直接接收内存数据
- **fix(performance)**: 夏普比率无风险收益率 2% → 1.85%

### 文档
- **docs**: 同步 Wind API 默认开启决策记录
- **docs**: 更新夏普比率公式说明（Rf=1.85%，含指数）

### 关联文件
- `reits_trading_assistant/main.py`
- `reits_trading_assistant/src/performance_analysis.py`
- `reits_trading_assistant/src/trade_analysis.py`
- `reits_trading_assistant/src/report_generator.py`
- `docs/decisions.md`
- `docs/summary.md`

---

## 2026-03-20 - `44037ad`

**工具**: Claude Code

### 新增功能
- **feat**: 新增 `load_holdings_timeseries()` 支持日频仓位计算
- **feat**: 新增 `plot_position_vs_index()` 仓位vs指数双轴图
- **feat**: trade_summary 增加仓位(%)列和"总结"sheet

### 修复问题
- **fix(data_loader)**: 修复交易文件列映射优先级（业务日期/成交金额等）
- **fix(trade_analysis)**: 分离 heavy_buy/sell 阈值计算（正/负分位数独立）
- **fix(performance_analysis)**: 总体指标双列格式，分月起止逻辑修正
- **fix(timing_analysis)**: 卖出胜率计算（原阈值导致样本数为0）
- **fix(data_loader)**: f-string语法错误（单大括号不匹配）
- **fix(sector_analysis)**: 空交易数据保护，避免空数组max崩溃

### 文档
- **docs**: 新建项目记忆文档 `docs/memory.md`，记录开发日志、避坑指南、计算口径

### 关联文件
- `src/data_loader.py`
- `src/trade_analysis.py`
- `src/performance_analysis.py`
- `src/timing_analysis.py`
- `src/sector_analysis.py`
- `main.py`
- `docs/memory.md`

---

## 2026-03-20 - `ebde5d8`

**工具**: Claude Code

### 修复问题
- **fix**: 修复交易文件读取和空数据保护
- **fix(data_loader)**: 修正交易文件glob模式，支持xlsx和csv
- **fix(data_loader)**: 修正列映射被同名列覆盖问题
- **fix(sector_analysis)**: plot_sector_rotation_dual增加空DataFrame保护
- **fix(main)**: analyze_sector_trades增加trades_df为None时的跳过逻辑

---

## 2026-03-20 - `c47b8c0`

**工具**: 外部合并

### 修复问题
- **fix**: 解决合并冲突，使用最新版本

---

## 2026-03-20 - `db9ea63`

**工具**: 外部提交

### 修复问题
- **fix(data_loader)**: 修复 `load_holdings()` 函数
  - 使用正确的列映射（A列日期，L列代码，P列权重，AR列市值）
  - 获取最新日期的持仓（时点数据）
  - 检查负数持仓并报错
  - 验证权重合计
- **fix(performance_analysis)**: 修复 `calc_metrics()` 函数
  - 添加 base_date 参数，统一与分月表现的口径
  - 只计算基准日之后的数据
- **fix(main)**: 更新业绩分析调用
  - 传递 base_date 参数
  - 添加基准日信息输出

---

## 2026-03-20 - Initial

**工具**: Claude Code

### 初始化
- 全套模块初始化开发完成
- 建立从原始数据到可视化报告的完整流程
- 输出: 4个processed CSV + 5张图表 + 1个Markdown报告
