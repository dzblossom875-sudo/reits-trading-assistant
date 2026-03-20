# REITs交易助手 - 调试日志

## 2026-03-20 数据读取重构调试记录

### 1. 问题发现

在重构数据读取模块后，执行诊断测试发现以下问题：

#### 问题1：交易明细方向全为"other"
```
交易数据: (3112, 7)
方向分布:
other       3028
dividend      84
```

**原因分析**：
- 交易类别字段存储为GBK编码，但pandas默认用UTF-8读取导致乱码
- 原始值`b'\xc1\xf5\xc9\xf0\xc2%\xf2%\xc9\xf0\xc2%\xa1\xa3'`实际是"基金买卖"的GBK编码
- 方向判断逻辑依赖解码后的中文关键词（买入/卖出/红利）

**解决方案**：
```python
def decode_trade_type(val):
    try:
        raw_bytes = str(val).encode('latin1')
        decoded = raw_bytes.decode('gbk', errors='ignore')
        return decoded
    except:
        return str(val)
```

#### 问题2：持仓数据code全为"887326854"

**原因分析**：
- 持仓查询文件列结构理解错误
- 原以为证券代码在列6，实际在列11
- 列6是某种内部编号（887326854重复出现）

**文件结构**（跳过1行后）：
```
列0: 日期 (2026/03/19)
列11: 证券代码 (508099)
列12: 证券名称 (中国电建)
列13: 资产类别 (REITs基金)
列25: 参考成本
列40: 持仓市值
```

**解决方案**：
```python
col_map = {
    0: "date",
    11: "code",
    12: "name",
    13: "asset_type",
    25: "cost_price",
    40: "market_value",
}
```

#### 问题3：买入/卖出方向无法区分

**原因分析**：
- 交易明细表无明确的"买入"/"卖出"字段
- 只有"交易类别"（基金买卖/基金红利到账）和"交割金额"

**业务逻辑推导**：
- 交割金额为**正** = 卖出（资金流入账户）
- 交割金额为**负** = 买入（资金流出账户）
- 交易类别含"红利" = 红利到账（单独标记）

**解决方案**：
```python
def determine_direction(row):
    trade_type = str(row.get("trade_type_decoded", ""))
    if "红利" in trade_type or "分红" in trade_type:
        return "dividend"
    elif "买卖" in trade_type:
        amount = row.get("amount", 0)
        if pd.notna(amount):
            return "sell" if amount > 0 else "buy"
    return "other"
```

### 2. 数据文件格式汇总

#### 日报表_*.xlsx
- **净值时间序列** sheet: 第4行为列名，第5行起数据
- **交易明细表** sheet: 第4行为列名，第5行起数据
  - 列0: 发生日期
  - 列2: 交易类别（GBK编码）
  - 列3: 证券代码
  - 列4: 证券名称
  - 列5: 交易数量
  - 列6: 交易价格
  - 列15: 交割金额
  - 列21: 资产类别

#### 统计分析-持仓查询-组合持仓查询.xlsx
- **sheet1**: 第1行为日期，第2行为列名，第3行起数据
  - 列11: 证券代码
  - 列12: 证券名称
  - 列13: 资产类别（REITs基金）
  - 列40: 持仓市值

#### 932006closeweight.xlsx
- 单列名行，含：成分券代码、成分券名称、权重(%)

### 3. 模块变更清单

| 模块 | 变更内容 |
|------|----------|
| `config.py` | 新增持仓文件、权重文件路径；可配置基准日 |
| `data_loader.py` | 重写交易/持仓/权重读取；GBK编码解码处理 |
| `utils.py` | 新增（文件查找、编码处理、通用清洗） |
| `wind_data_loader.py` | 新增（Wind API封装，失败回退机制） |
| `allocation_analysis.py` | 新增（配置偏移计算） |
| `performance_analysis.py` | 添加分月指标计算、超额右轴图表 |
| `sector_analysis.py` | 添加板块轮动双图（净买入+涨跌幅） |
| `trade_analysis.py` | 修复Trade Flow图坐标轴、数据连续性 |
| `timing_analysis.py` | 图表起始日对齐基准日 |
| `report_generator.py` | 报告头部显示账户名称 |
| `main.py` | 整合所有新模块，8步分析流程 |

### 4. 待测试项

- [ ] Wind API连接和数据获取
- [ ] 板块涨跌幅计算（基于个股等权）
- [ ] 配置偏移计算结果验证
- [ ] 图表坐标轴范围正确性
- [ ] 红利到账金额是否正确计入收益
