# 🐛 Debug Log

> 记录所有已解决的问题，格式统一，禁止删除历史条目。

---

## 交易方向判断逻辑错误

- **现象**：3028条交易全是"sell"，方向分布异常
- **根因**：
  1. 交易类别字段存储为GBK编码，pandas默认用UTF-8读取导致乱码
  2. 原始值`b'\xc1xf5\xc9xf0\xc2%\xf2%\xc9xf0\xc2%\xa1xa3'`实际是"基金买卖"的GBK编码
  3. 方向判断逻辑依赖解码后的中文关键词（买入/卖出/红利）
- **解决方案**：
  ```python
  def decode_trade_type(val):
      try:
          raw_bytes = str(val).encode('latin1')
          decoded = raw_bytes.decode('gbk', errors='ignore')
          return decoded
      except:
          return str(val)
  ```
  交割金额为正=卖出（资金流入），为负=买入（资金流出）
- **验证步骤**：
  1. 查看原始数据中几笔典型交易
  2. 确认交割金额正负与买卖方向的对应关系
  3. 运行后检查方向分布是否合理（buy/sell/other）
- **关联 Commit**：`44037ad`

---

## 持仓数据code全为"887326854"

- **现象**：持仓数据证券代码全部相同（887326854）
- **根因**：持仓查询文件列结构理解错误，原以为证券代码在列6，实际在列11；列6是某种内部编号（887326854重复出现）
- **解决方案**：更新列映射
  ```python
  col_map = {
      0: "date",
      11: "code",    # 原错误：6
      12: "name",
      13: "asset_type",
      40: "market_value",
  }
  ```
- **验证步骤**：读取持仓文件后检查code列是否有重复值过多
- **关联 Commit**：`db9ea63`

---

## heavy_sell信号数为0

- **现象**：`timing_analysis.xlsx` 卖出胜率为空或 N/A
- **根因**：原阈值逻辑：`|净买入|.quantile(0.75)`，同时用于正负方向；实际交易以净买入为主，负值绝对值小，无法触发阈值
- **解决方案**：阈值分离计算
  ```python
  buy_threshold = daily[daily["net_amount"] > 0]["net_amount"].quantile(0.75)
  sell_threshold = -daily[daily["net_amount"] < 0]["net_amount"].quantile(0.75)
  ```
- **验证步骤**：检查交易汇总中 heavy_sell 天数是否大于0
- **关联 Commit**：`44037ad`

---

## 列映射被同名列覆盖

- **现象**：交易日期解析失败，读取到`费用结算日期`（全为NaN）而非`业务日期`
- **根因**：模糊匹配 `"日期" in col_str` 导致取到最后出现的列；多个列含"日期"、"金额"、"数量"字样
- **解决方案**：优先级匹配
  ```python
  elif "业务日期" in col_str: col_map["date"] = col
  elif "日期" in col_str and "date" not in col_map: col_map["date"] = col
  ```
- **验证步骤**：加载数据时打印列映射结果，确认字段识别正确
- **关联 Commit**：`44037ad`

---

## 交易文件glob匹配失败

- **现象**：`⚠️ 未找到交易所成交查询文件`，交易数据为None
- **根因**：glob模式 `"统计分析 - 交易查询*.csv"` 不匹配实际文件名（连字符两侧无空格，且为xlsx格式）
- **解决方案**：
  ```python
  files = (
      glob.glob(os.path.join(config.DATA_RAW_DIR, "统计分析*交易查询*.csv")) +
      glob.glob(os.path.join(config.DATA_RAW_DIR, "统计分析*交易查询*.xlsx"))
  )
  ```
- **验证步骤**：检查是否能正确识别并读取交易文件
- **关联 Commit**：`ebde5d8`

---

## 板块轮动图空数组崩溃

- **现象**：`ValueError: zero-size array to reduction operation maximum which has no identity`
- **根因**：`plot_sector_rotation_dual()` 未处理空交易数据，空数组调用 `.max()` 报错
- **解决方案**：
  ```python
  if trades_df is None or trades_df.empty:
      return None, None
  ```
- **验证步骤**：运行程序时传入空DataFrame测试
- **关联 Commit**：`ebde5d8`

---

*最后更新：2026-03-20*
