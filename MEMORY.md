# 🧠 MEMORY.md — 项目上下文

> 跨工具协作主文件。每次开始工作前先读此文件，结束后必须更新。

## 🔄 当前状态
- **最后操作工具**：Claude Code
- **最后操作**：MD文件整理合并完毕，已删除 docs/memory.md、FIXES_SUMMARY.md、REVIEW_REPORT.md
- **最后 Commit**：`9bc8f4c`
- **待续事项**：
  - [ ] B工具读取 docs/summary.md，检查结论是否完整
  - [ ] 补全缺失的决策理由（如：为什么用累计净值而非单位净值）
  - [ ] 验证交易方向判断逻辑（交割金额正负与买卖方向的对应关系）

## 📐 架构快照

### 8步分析流程
```
[数据加载] → [行情获取] → [板块分析] → [交易分析] → [择时分析] → [业绩分析] → [配置偏移] → [报告生成]
```

### 核心模块
| 模块 | 职责 | 关键函数 |
|------|------|----------|
| `data_loader.py` | 数据加载与清洗 | `align_and_save()`, `load_holdings_timeseries()` |
| `trade_analysis.py` | 交易行为分析 | `summarize_trades()`, `plot_position_vs_index()` |
| `performance_analysis.py` | 业绩归因 | `calc_metrics()`, `calc_metrics_by_period()` |
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

---

## 🔗 关联文档

| 文档 | 用途 | 更新时机 |
|------|------|----------|
| `docs/CHANGELOG.md` | 完整修改历史 | 每次归档追加 |
| `docs/debug-log.md` | 问题与解决方案 | Debug修复后 |
| `docs/decisions.md` | 技术决策理由 | 关键决策后 |
| `docs/summary.md` | 最终规则与最佳实践 | 结论验证后 |

---

*最后更新：2026-03-20*
