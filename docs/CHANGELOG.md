# 📋 CHANGELOG

> 完整修改历史，每次归档自动追加，禁止修改已有条目。

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
