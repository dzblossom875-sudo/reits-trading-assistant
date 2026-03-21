# 🧠 MEMORY.md — 项目上下文

> 跨工具协作主文件。每次开始工作前先读此文件，结束后必须更新。

## 🔄 当前状态
- **最后操作工具**：Cursor
- **最后操作**：持仓文件通配符取最新、日度持仓市值零值前向填充；板块月度 resample 改为 `ME`；归档 MEMORY/CHANGELOG
- **最后 Commit**：`7e9c03a`（持仓通配符与日度零值填充）；`dc334ec`（板块 `ME`）；文档见 `docs/CHANGELOG.md`
- **待续事项**：
  - [ ] 考虑将 output 历史目录清理或归档策略（可选）

## 📐 架构快照

### 8步分析流程
```
[数据加载] → [行情获取] → [板块分析] → [交易分析] → [择时分析] → [业绩分析] → [配置偏移] → [报告生成]
```

### 核心模块
| 模块 | 职责 | 关键函数 |
|------|------|----------|
| `data_loader.py` | 数据加载与清洗 | `align_and_save()`, `load_holdings_timeseries()` |
| `trade_analysis.py` | 交易行为分析 | `summarize_trades()`, `plot_trade_flow()`, `plot_net_buy_vs_index()` |
| `performance_analysis.py` | 业绩归因 | `calc_metrics()`, `save_daily_tracking()`, `plot_position_change_vs_index()` |
| `timing_analysis.py` | 择时效果评估 | `analyze_timing()` |
| `sector_analysis.py` | 板块轮动 | `plot_sector_rotation_dual()` |
| `allocation_analysis.py` | 配置偏移 | `calc_allocation_bias()` |

### 数据流
```
raw/沪深REITs.xlsx ──┐
raw/指数.xlsx        ──┤
raw/日报表_*.xlsx    ──┤  data_loader.py  →  processed/*.csv
raw/持仓查询.xlsx    ──┤  + wind_fallback
raw/交易所成交.xlsx  ──┘
                              ↓
                    src/分析模块 × 5
                              ↓
                    output/figures/ + output/reports/
```

## 📅 开发日志

### 2026-03-20 - Claude Code

#### [数据加载] 修复交易文件读取与列映射
- **模块**：`src/data_loader.py`
- **逻辑变更**：
  - 列映射优先级修正：`"业务日期"` 精确匹配优先于 `"日期"` 模糊匹配
  - 同时支持 CSV/XLSX 格式，根据扩展名选择读取函数
  - 新增 `load_holdings_timeseries()` 读取日频持仓市值
- **避坑指南**：
  - Excel 列名可能含隐藏字符，匹配前用 `.strip()` 清洗
  - 同名/相似名列需用精确匹配，避免顺序依赖
  - Windows 中文路径 glob 需用正斜杠或 `os.path.join()`
- **Commit**：`44037ad`

#### [业绩分析] 双列对比格式与分月逻辑修正
- **模块**：`src/performance_analysis.py`
- **逻辑变更**：
  - 总体指标改为双列格式：`指标 | 账户名称 | 指数`
  - 增加"区间总收益率"与"年化收益率"区分绝对收益与年化收益
  - 分月计算改为：本月收益 = (本月末净值 / 上月末净值 - 1)
  - 分月表增加 `起始日`、`结束日` 列明确计算区间
- **避坑指南**：
  - 分月收益若用"月内首个交易日→月末"，首月会包含跨月持有收益
  - DataFrame.attrs 可用于传递元数据，但需检查属性存在性
- **Commit**：`44037ad`

#### [交易分析] 仓位计算与 heavy_buy/sell 阈值修正
- **模块**：`src/trade_analysis.py`, `src/data_loader.py`
- **逻辑变更**：
  - 阈值分离计算：正净买入75分位数 / 负净卖出75分位数绝对值
  - 新增 `plot_position_vs_index()` 绘制仓位比例 vs 指数双轴图
  - 交易汇总增加仓位(%) = 持仓市值 / 净资产
- **避坑指南**：
  - 多空信号阈值应分别计算，不能简单用绝对值对称处理
  - 持仓市值需从原始文件读取时序，截面数据无法计算历史仓位
- **Commit**：`44037ad`

#### [择时分析] 卖出胜率计算修复
- **模块**：`src/timing_analysis.py`
- **逻辑变更**：使用分离阈值后，heavy_sell 天数从 0 → 12 天
- **避坑指南**：胜率统计需检查样本数是否为 0，避免除零或空值
- **Commit**：`44037ad`

### 2026-03-21 - Cursor

#### [业绩分析] 逐日跟踪表与仓位变动图
- **模块**：`src/performance_analysis.py`
- **逻辑变更**：
  - 新增 `save_daily_tracking()` 输出归一化净值+仓位的逐日表
  - 非交易日用前值填充（`reindex + ffill`），消除指数断档
  - 新增 `plot_position_change_vs_index()` 仓位变动 vs 指数图
  - 夏普比率无风险收益率 2% → 1.85%，新增指数夏普计算
- **避坑指南**：
  - 非交易日填充用 `pd.date_range + ffill`，不能用 `resample` 否则会生成空行
  - 仓位变动 `diff()` 在前值填充后会包含非交易日的0变动，属正常
- **Commit**：`5ddf351`

#### [交易分析] 资金流向图改版 + 净买入图
- **模块**：`src/trade_analysis.py`
- **逻辑变更**：
  - `plot_trade_flow()` 左右轴互换：左轴指数(加粗)，右轴买卖
  - 新增 `plot_net_buy_vs_index()` 净买入 vs 指数图
  - `summarize_trades()` 增加 `position_change` 列
- **避坑指南**：
  - 双轴图指数在左轴时需手动设置 ylim 留出余量，避免柱状图遮挡
- **Commit**：`5ddf351`

#### [报告生成] 修复无数据问题
- **模块**：`src/report_generator.py`
- **逻辑变更**：
  - 根因：报告读 CSV 文件但实际输出为 XLSX → 全部读空
  - 改为 `generate_report(**kwargs)` 直接接收内存数据
  - 新增分月表现、配置偏移完整表格
- **避坑指南**：
  - 报告生成应在所有分析完成后调用，确保数据变量可用
  - 不要依赖中间文件格式，直接传递 DataFrame 更可靠
- **Commit**：`5ddf351`

#### [板块分析] 月度重采样频率别名
- **模块**：`src/sector_analysis.py`
- **逻辑变更**：`resample('M')` → `resample('ME')`，消除 pandas 弃用警告
- **避坑指南**：频率别名随 pandas 版本演进，以官方文档为准
- **Commit**：`dc334ec`

#### [数据加载] 持仓文件通配符与日度市值零值处理
- **模块**：`config.py`, `src/data_loader.py`
- **逻辑变更**：
  - `FILE_HOLDINGS` 支持 `组合持仓查询*.xlsx`，`load_holdings` / `load_holdings_timeseries` 取目录内修改时间最新文件
  - 日度汇总市值为 0 时视为导出缺行，按上一有效日总市值前向填充（避免逐日仓位长段为 0）；真清仓需源数据能体现减仓轨迹
- **避坑指南**：
  - 多版本持仓文件并存时以文件 mtime 为准，勿混用旧表
  - 零值填充与真实空仓需结合业务核对
- **Commit**：`7e9c03a`

---

## 🔗 关联文档

| 文档 | 用途 | 更新时机 |
|------|------|----------|
| `docs/CHANGELOG.md` | 完整修改历史 | 每次归档追加 |
| `docs/debug-log.md` | 问题与解决方案 | Debug修复后 |
| `docs/decisions.md` | 技术决策理由 | 关键决策后 |
| `docs/summary.md` | 最终规则与最佳实践 | 结论验证后 |

---

*最后更新：2026-03-21*
