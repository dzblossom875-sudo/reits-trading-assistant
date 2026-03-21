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

---

## 净值/指数起点不对齐

- **时间**：2026-03-21 14:30
- **现象**：`plot_nav_vs_index()` 中净值曲线和指数曲线起点不在同一Y值，图表视觉误导
- **根因**：两条线独立归一化，起始日期不同（净值从 BASE_DATE 开始，指数从更早日期开始），各自以自己第一个值为1.0
- **解决方案**：找两线共同有效的第一个日期，在该日期重新统一归一化到1.0
  ```python
  common_start = daily_df[["nav_norm", "reits_index_norm"]].dropna().index.min()
  base_nav = daily_df.loc[common_start, "nav_norm"]
  base_idx = daily_df.loc[common_start, "reits_index_norm"]
  nav_plot = daily_df["nav_norm"] / base_nav
  idx_plot = daily_df["reits_index_norm"] / base_idx
  ```
- **验证步骤**：运行后确认两线在图左侧起点均为1.0
- **关联 Commit**：`aabb4b7`（2026-03-21 15:24）

---

## SimHei 字体缺失 Unicode 符号导致乱码方块

- **时间**：2026-03-21 14:45
- **现象**：matplotlib 警告 `Glyph 10003 missing from font(s) SimHei`，图中 ✓ ✗ ⚠️ 等符号显示为空白方块
- **根因**：SimHei 是中文字体，不包含 Unicode 通用符号区（U+2713、U+2717、U+26A0 等）
- **解决方案**：所有标注文字改用纯中文，用【】包裹代替符号
  - 四象限标签：`✓买对了` → `【买对了】`，`✗买错了` → `【买错了】` 等
  - 异常点标注：`⚠{pct:.0f}%` → `异常{pct:.0f}%`
- **验证步骤**：运行后确认图中无方块乱码
- **关联 Commit**：`aabb4b7`（2026-03-21 15:24）

---

## input() 在非交互环境抛 EOFError

- **时间**：2026-03-21 14:50
- **现象**：通过管道或重定向运行时程序崩溃，报 `EOFError: EOF when reading a line`
- **根因**：`input()` 读取 stdin，非 TTY 环境下 stdin 为空管道，立即触发 EOF
- **解决方案**：用 try/except 包裹，EOFError 时默认保留
  ```python
  try:
      ans = input("是否排除以上异常点？[y=排除 / n=保留，默认保留] ")
  except EOFError:
      ans = ""
      print("  (非交互模式，默认保留)")
  ```
- **验证步骤**：用 `echo "" | python main.py` 测试管道运行不崩溃
- **关联 Commit**：`aabb4b7`（2026-03-21 15:24）

---

## Windows GBK 终端 emoji print 崩溃

- **时间**：2026-03-21 15:00
- **现象**：`UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f680'`，程序启动即崩溃
- **根因**：Windows 终端默认编码 GBK，无法编码 emoji（如 🚀 ✅ 📖）
- **解决方案**：运行时设置环境变量 `PYTHONIOENCODING=utf-8`
  ```bash
  PYTHONIOENCODING=utf-8 python main.py
  ```
- **注意**：不修改代码，只改运行方式；或在 `main.py` 顶部加 `sys.stdout.reconfigure(encoding='utf-8')`
- **验证步骤**：在 GBK 终端加环境变量后正常运行
- **关联 Commit**：`aabb4b7`（2026-03-21 15:24）

---

## history data.xlsx 新增列导致 ValueError

- **时间**：2026-03-21 18:10
- **现象**：`ValueError: Length mismatch: Expected axis has 14 elements, new values have 7 elements`
- **根因**：`load_history_data()` 原先用列表直接赋值列名（硬编码7列），文件从7列扩展到14列后长度不匹配
  ```python
  # 旧代码（错误）
  df.columns = ["date", "net_assets", "reits_index_norm", "nav_norm", "excess", "position_pct", "signal"]
  ```
- **解决方案**：改用位置字典映射，`if k < len(df.columns)` 做边界保护，新增列自动适配
  ```python
  col_map = {0:"date", 1:"net_assets", 2:"reits_index_abs", 3:"reits_index_norm",
             4:"nav_norm", 5:"excess", 6:"position_pct", 7:"position_change",
             8:"buy_amount", 9:"sell_amount", 10:"dividend_amount",
             11:"net_amount", 12:"trade_count", 13:"signal"}
  rename = {df.columns[k]: v for k, v in col_map.items() if k < len(df.columns)}
  df = df.rename(columns=rename)
  ```
- **验证步骤**：读取14列文件后检查所有列名正确，再删列测试向下兼容
- **关联 Commit**：`3991d37`（2026-03-21 18:12）

---

## history data 列名含换行符无法作为字典 key

- **时间**：2026-03-21 18:05
- **现象**：按列名访问 history_df 时 KeyError，打印列名发现含 `\n`（如 `"净资产\n(万元)"`）
- **根因**：Excel 列头有手动换行，pandas 读取后保留换行符；直接用中文字符串作 key 无法匹配
- **解决方案**：全程使用位置索引（iloc 或数字 key）映射，不依赖列名字符串
- **关联 Commit**：`df68c7b`（2026-03-21 18:09）

---

## 仓位>100% 的根因（非代码bug）

- **时间**：2026-03-21 14:40
- **现象**：2026-01-05 ~ 01-14 仓位显示 100%~102%，疑似数据错误
- **根因**：持仓文件（`统计分析-持仓查询*.xlsx`）非每日记录，`load_holdings_timeseries()` 使用 `ffill()` 填充空白日，导致持仓市值固定（31,953万），而净资产逐日变化，比值超过1
- **结论**：非真实超仓，是持仓文件覆盖频率不足造成的计算误差；2026-02-09 的 +18.1ppt 跳升是真实买入（春节后新增持仓，市值从31,953万→39,731万），正常
- **关联 Commit**：`aabb4b7`（2026-03-21 15:24）

---

*最后更新：2026-03-21 18:30*
