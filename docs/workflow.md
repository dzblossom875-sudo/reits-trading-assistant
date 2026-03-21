# 🗺️ 数据流与架构设计

> 描述数据从原始输入到最终输出的完整流向，以及关键架构决策。

---

## 1. 数据流架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              原始数据层 (data/raw/)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  沪深REITs.xlsx    指数.xlsx    日报表_*.xlsx    交易查询.*    持仓查询.*   │
│     (板块)          (基准)        (净值)           (交易)        (持仓)     │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          数据加载层 (src/data_loader.py)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │load_reits_  │  │load_index() │  │load_nav_    │  │load_trades_ │        │
│  │info()       │  │             │  │from_daily() │  │from_exchange│        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│         │                │                │                │                │
│         └────────────────┴────────────────┴────────────────┘                │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     align_and_save() 数据对齐                         │   │
│  │  - 日期统一为 DatetimeIndex                                          │   │
│  │  - 证券代码统一为6位数字                                              │   │
│  │  - 输出 processed CSV (中间态，向后兼容)                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬───────────────────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
┌─────────────────────┐ ┌─────────────────┐ ┌─────────────────────────────┐
│  output/YYYYMMDD/   │ │ data/processed/ │ │      分析模块 (src/)         │
│   (带时间戳输出)     │ │  (Parquet防腐层) │ │                             │
├─────────────────────┤ ├─────────────────┤ │  ┌─────────┐ ┌───────────┐  │
│ daily_master.xlsx   │ │ daily_master.   │ │  │trade_   │ │performance│  │
│ performance_summary │ │ parquet         │ │  │analysis │ │_analysis  │  │
│ trade_summary.xlsx  │ │                 │ │  └────┬────┘ └─────┬─────┘  │
│ allocation_bias.    │ │ allocation_bias │ │       │            │        │
│ xlsx                │ │ _sector.parquet │ │       └────────────┘        │
│ timing_analysis.    │ │                 │ │              │              │
│ xlsx                │ │ allocation_bias │ │              ▼              │
│                     │ │ _detail.parquet │ │       dashboard.py         │
│ (适合查看和存档)     │ │                 │ │       (Streamlit看板)      │
│                     │ │ performance_    │ │                             │
│                     │ │ summary_metrics │ │                             │
│                     │ │ .parquet        │ │                             │
│                     │ │                 │ │                             │
│                     │ │ performance_    │ │                             │
│                     │ │ summary_monthly │ │                             │
│                     │ │ .parquet        │ │                             │
└─────────────────────┘ └─────────────────┘ └─────────────────────────────┘
       ▲                                                        │
       │                                                        │
       │         ┌──────────────────────────────────────────────┘
       │         │
       │         ▼
       │  ┌─────────────────┐
       │  │  report_*.md    │
       │  │  (最终报告)      │
       │  └─────────────────┘
       │
       └──── 人工查看/存档
```

---

## 2. 双输出架构设计

### 为什么需要两个输出路径？

| 路径 | 用途 | 生命周期 | 消费者 |
|------|------|----------|--------|
| `output/YYYYMMDD/` | 历史存档、人工查看、Excel分析 | 每次运行新建，永不覆盖 | 分析师、基金经理 |
| `data/processed/*.parquet` | 程序消费、快速读取、固定路径 | 每次运行覆盖最新 | Dashboard、下游自动化脚本 |

### 关键区别

```python
# output/ → 带时间戳，保留历史
OUTPUT_DIR = os.path.join(BASE_DIR, "output", RUN_TIMESTAMP)
# 例如: output/20260321_223751/daily_master.xlsx

# processed/ → 固定路径，总是最新
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
# 例如: data/processed/daily_master.parquet (永远是最新数据)
```

---

## 3. Parquet 防腐层详解

### 3.1 什么是"防腐层"？

> 防腐层（Anti-Corruption Layer）：在遗留系统与新系统之间建立翻译层，防止一个系统的模型污染另一个系统。

在本项目中：
- **遗留系统**：`main.py` 的内存直通式流水线（DataFrame 直接传递）
- **新系统**：`dashboard.py` 独立运行的看板（需要固定路径数据源）
- **防腐层**：`data/processed/*.parquet` 固定路径文件

### 3.2 防腐层解决了什么问题？

| 问题 | 解决方案 |
|------|----------|
| `output/` 路径带时间戳，看板无法自动找到最新文件 | `processed/` 使用固定路径 |
| Excel 读取慢（1213行×13列需要数秒） | Parquet 格式读取快10倍 |
| 非交易日数据缺失，看板图表断线 | Parquet 层完成插值（ffill） |
| 看板调试时需要反复跑主程序 | 看板直接读 Parquet，独立于主程序运行 |

### 3.3 插值规则（数据完整性保证）

```python
# daily_master.parquet 生成逻辑
df = full_df.reindex(pd.date_range(start, end, freq='D'))  # 补全非交易日

# 1. 净值、仓位数据：前向填充（ffill）
ffill_cols = ['net_assets_wan', 'reits_index_abs', 'position_pct']

# 2. 仓位变动：基于 ffill 后的仓位重新计算 diff
df['position_change'] = df['position_pct'].diff()

# 3. 交易数据（买入/卖出/净买入）：非交易日保持 NaN，不插值
# 这样看板可以区分"无交易"和"交易为0"
```

---

## 4. Dashboard 数据依赖关系

```
dashboard.py
    │
    ├─► df = pd.read_parquet("data/processed/daily_master.parquet")
    │   ├── 模块1: 核心趋势归因（净值/指数/超额）
    │   ├── 模块2: 调仓意图扫描仪（仓位变动 ppt）
    │   └── 模块3: 实际仓位水位（仓位面积图）
    │
    ├─► bias_df = pd.read_parquet("data/processed/allocation_bias_sector.parquet")
    │   └── 模块4: 板块配置偏移
    │
    ├─► perf_monthly = pd.read_parquet("data/processed/performance_summary_monthly.parquet")
    │   └── 模块5: 分月表现对比
    │
    ├─► trades_df = pd.read_csv("data/processed/trades_clean.csv")
    │   prices_df = pd.read_csv("data/processed/wind_prices_cache.csv")
    │   └── 模块6: 板块操作归因气泡图
    │
    └─► perf_metrics = pd.read_parquet("data/processed/performance_summary_metrics.parquet")
        └── KPI 卡片（区间总收益/年化收益/最大回撤/夏普）
```

---

## 5. 关键架构决策记录

### 决策1：为什么用 Parquet 而不是继续用 CSV？

| 维度 | CSV | Parquet |
|------|-----|---------|
| 读取速度 | 慢（需解析文本） | 快（二进制列式存储） |
| 数据类型 | 丢失（全部变字符串） | 保留（int/float/date） |
| 文件大小 | 大 | 小（压缩） |
| DatetimeIndex | 保存为字符串 | 原生支持 |
| 中文列名 | 易乱码 | 稳定（UTF-8） |

### 决策2：为什么 Dashboard 不直接读 Excel？

1. **性能**：Excel 读取需要 3-5 秒，Parquet 只需 0.1 秒
2. **路径稳定性**：Excel 在 `output/YYYYMMDD/` 下，路径每次都变
3. **数据一致性**：Parquet 在写入前已完成插值，Excel 保持原始数据

### 决策3：为什么保留双输出而不是只保留 Parquet？

- **Excel 不可替代**：基金经理需要下载查看、人工复核、邮件发送
- **Parquet 不可替代**：程序读取快、固定路径、支持复杂数据类型
- **结论**：两者并存，服务不同消费者

---

## 6. 扩展指南

### 新增一个 Parquet 输出

在相应的 `save_xxx()` 函数中添加：

```python
def save_new_analysis(df: pd.DataFrame, output_dir: str):
    # 1. 保存到带时间戳的 Excel（原有功能）
    out_path = os.path.join(output_dir, "new_analysis.xlsx")
    df.to_excel(out_path)

    # 2. 新增：保存到固定路径 Parquet（防腐层）
    parquet_path = os.path.join(config.DATA_PROCESSED_DIR, "new_analysis.parquet")
    df.to_parquet(parquet_path, index=False)
```

### 在 Dashboard 中新增一个图表

```python
# 1. 如果数据已存在 Parquet，直接读取
new_df = pd.read_parquet("data/processed/new_analysis.parquet")

# 2. 如果数据需要实时计算，在 main.py 中先添加 Parquet 输出
```

---

*最后更新：2026-03-22*
