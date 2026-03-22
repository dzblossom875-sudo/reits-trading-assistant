import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# dashboard.py 以 reits_trading_assistant/ 为工作目录运行
# 若从项目根目录启动，自动切换到正确目录
_HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(_HERE)

# ================= 1. 页面配置与动态主题 =================
st.set_page_config(page_title="REITs二级策略跟踪", layout="wide", page_icon="📈")

st.sidebar.header("🎨 视觉与排版")
theme_mode = st.sidebar.radio(
    "配色方案",
    ["User · Cloud Blue", "Company · 平安集团"],
    index=0,
)
aspect_ratio = st.sidebar.radio(
    "页面比例",
    ["研报长条 (2.5:1, 留白)", "标准宽屏 (16:9, 铺满)"],
    index=0,
)

if theme_mode == "User · Cloud Blue":
    bg_color        = "#f2f6fb"
    text_color      = "#0a1428"
    grid_color      = "rgba(26,74,128,0.10)"
    template        = "plotly_white"
    nav_color       = "#1a4a80"                   # s1 navy  —— 账户净值
    idx_color       = "#4a78b8"                   # steel blue —— 指数（提高饱和度）
    excess_fill     = "rgba(26,74,128,0.18)"      # 超额面积填充（提高不透明度）
    bull_color      = "#1a6ca0"                   # steel blue —— 正向/超配（明显区别于平安绿）
    bear_color      = "#c85a00"                   # burnt orange —— 负向/低配
    pos_line        = "#006080"                   # deep teal —— 仓位线
    pos_fill        = "rgba(0,96,128,0.22)"       # 仓位面积（提高不透明度）
    metric_color    = "#1a4a80"
    _bubble_palette = ["#1a4a80","#c85a00","#00806a","#8b2fc9","#d4a000",
                       "#006080","#c83060","#3a8040","#804020","#205080"]
else:  # Company · 平安集团
    bg_color        = "#F8F6F4"
    text_color      = "#1A1A1A"
    grid_color      = "rgba(0,0,0,0.08)"
    template        = "plotly_white"
    nav_color       = "#F04E23"                   # 平安橙 —— 账户净值
    idx_color       = "#909090"                   # medium grey —— 指数（略提亮可读性）
    excess_fill     = "rgba(240,78,35,0.18)"      # 超额面积填充（提高不透明度）
    bull_color      = "#007D5E"                   # 平安绿 —— 正向/超配
    bear_color      = "#C83800"                   # 深橙红 —— 负向/低配
    pos_line        = "#007D5E"                   # 平安绿 —— 仓位线（区别于净值橙）
    pos_fill        = "rgba(0,125,94,0.22)"       # 仓位面积（提高不透明度）
    metric_color    = "#F04E23"
    _bubble_palette = ["#F04E23","#007D5E","#1a4a80","#8b2fc9","#d4a000",
                       "#006080","#c83060","#3a8040","#804020","#205080"]

_font9 = dict(size=11, color=text_color)

if aspect_ratio == "研报长条 (2.5:1, 留白)":
    container_width, chart_height = 1100, 440
else:
    container_width, chart_height = 1800, 550

st.markdown(f"""
    <style>
    .main .block-container {{
        max-width: {container_width}px;
        padding-top: 1.5rem;
        margin: 0 auto;
    }}
    [data-testid="stMetricValue"] {{font-size: 1.8rem; color: {metric_color}; font-weight: 700;}}
    .stMetric {{background-color: {bg_color}; padding: 15px; border-radius: 10px; border: 1px solid {grid_color};}}
    </style>
    """, unsafe_allow_html=True)

# ================= 2. 数据加载 =================
@st.cache_data(ttl=3600)
def load_all_data():
    try:
        df = pd.read_parquet("data/processed/daily_master.parquet")
        perf_metrics = pd.read_parquet("data/processed/performance_summary_metrics.parquet")
        perf_monthly = pd.read_parquet("data/processed/performance_summary_monthly.parquet")
        # 实际列名已是 sector / weight_bias，无需 rename
        bias_df = pd.read_parquet("data/processed/allocation_bias_sector.parquet")
        trades_df = pd.read_csv("data/processed/trades_clean.csv", parse_dates=["date"])
        trades_df["code"] = trades_df["code"].astype(str).str.zfill(6)
        info_df = pd.read_csv("data/processed/reits_info.csv")
        info_df["code"] = info_df["code"].astype(str).str.zfill(6)
        prices_df = pd.read_csv(
            "data/processed/wind_prices_cache.csv", index_col=0, parse_dates=True
        )
        holdings_df = pd.read_csv("data/processed/holdings.csv")
        holdings_df["code"] = holdings_df["code"].astype(str).str.zfill(6)
        return df.ffill(), perf_metrics, perf_monthly, bias_df, trades_df, info_df, prices_df, holdings_df
    except Exception as e:
        st.error(f"❌ 数据源异常: {e}")
        st.stop()

df, perf_metrics, perf_monthly, bias_df, trades_df, info_df, prices_df, holdings_df = load_all_data()

# ================= 3. 时间轴控制 =================
min_d, max_d = df.index.min().date(), df.index.max().date()
default_start = max(pd.to_datetime("2024-02-08").date(), min_d)

# --- 图一独立控件（放最上方）---
st.sidebar.header("📈 图一：核心趋势")
fig1_base = st.sidebar.date_input(
    "基准日选择",
    value=default_start,
    key="fig1_base",
    help="图表从此日起展示，净值/指数同时归一到 1.0",
)
fig1_start = fig1_base  # 起始日与基准日保持一致

# --- 图二~六共用控件 ---
st.sidebar.header("📊 图二~六：区间分析")
start_date = st.sidebar.date_input("起始日 (默认2024-02-08)", value=default_start, key="main_start")
end_date = st.sidebar.date_input("结束日", value=max_d, key="main_end")

# ================= 4. 预计算图一归一化（指标卡依赖此结果）=================
# date_input 清空时返回 None，需用默认值兜底
_fig1_base  = pd.to_datetime(fig1_base) if fig1_base else pd.to_datetime(default_start)
_fig1_start = _fig1_base  # 起始日与基准日保持一致
_start_date = pd.to_datetime(start_date) if start_date else pd.to_datetime(default_start)
_end_date   = pd.to_datetime(end_date)   if end_date   else pd.to_datetime(max_d)

df_p1 = df[df.index >= _fig1_start].copy()
# 图二~六共用窗口
df_p = df[(df.index >= _start_date) & (df.index <= _end_date)].copy()

# 归一化：锚点始终从完整 df 里找，与 fig1_start 无关
# 这样无论 fig1_start 早于还是晚于 fig1_base，fig1_base 处永远 = 1.0
_nav_n = _idx_n = _alpha = None
_anchor = df[df.index >= _fig1_base].dropna(
    subset=["净值(基准2022-11-24)", "指数(基准2022-11-24)"]
)
if not _anchor.empty:
    _v0 = _anchor.iloc[0]
    df_p1["nav_n"] = df_p1["净值(基准2022-11-24)"] / _v0["净值(基准2022-11-24)"]
    df_p1["idx_n"] = df_p1["指数(基准2022-11-24)"] / _v0["指数(基准2022-11-24)"]
    # 指标卡只算基准日之后的段（归一化起点 = 1.0 那段）
    _base_mask = df_p1.index >= _v0.name
    _nav_n = df_p1.loc[_base_mask, "nav_n"].dropna()
    _idx_n = df_p1.loc[_base_mask, "idx_n"].dropna()
    _alpha = (_nav_n - _idx_n) * 100


def _sector_bias_at(at_date, holdings_df, prices_df, info_df, bias_df):
    """
    按价格还原：用当前持仓持份数 × at_date 价格，计算该日期近似板块配置偏移。
    index_weight 沿用 bias_df 中的基准权重。
    """
    avail = prices_df.index[prices_df.index <= at_date]
    if len(avail) == 0:
        return bias_df.copy()
    target_date = avail.max()
    prices_t = prices_df.loc[target_date]
    prices_latest = prices_df.loc[prices_df.index.max()]

    h = holdings_df.copy()
    def _scale(row):
        p_now = prices_latest.get(row["code"], np.nan)
        p_then = prices_t.get(row["code"], np.nan)
        if pd.notna(p_now) and p_now > 0 and pd.notna(p_then):
            return row["market_value"] * (p_then / p_now)
        return row["market_value"]

    h["scaled_mv"] = h.apply(_scale, axis=1)
    merged = pd.merge(h, info_df[["code", "sector"]], on="code", how="left")
    total = merged["scaled_mv"].sum()
    if total == 0:
        return bias_df.copy()

    sector_w = merged.groupby("sector")["scaled_mv"].sum() / total
    idx_w = bias_df.set_index("sector")["index_weight"]
    result = pd.DataFrame({"account_weight": sector_w}).reset_index()
    result.columns = ["sector", "account_weight"]
    result["index_weight"] = result["sector"].map(idx_w).fillna(0)
    result["weight_bias"] = result["account_weight"] - result["index_weight"]
    return result


def _fmt_pct(v, decimals=2):
    return f"{v:.{decimals}f}%" if pd.notna(v) else "N/A"

def _calc_metrics(s):
    """从归一化序列（起点≈1.0）计算四项指标，返回 dict"""
    s = s.dropna()
    if len(s) < 2:
        return {}
    total = (s.iloc[-1] / s.iloc[0] - 1) * 100
    n_days = max((s.index[-1] - s.index[0]).days, 1)
    ann = ((1 + total / 100) ** (365 / n_days) - 1) * 100
    roll_max = s.cummax()
    mdd = ((s - roll_max) / roll_max).min() * 100
    dr = s.pct_change().dropna()
    vol = dr.std() * np.sqrt(252)
    sharpe = (ann / 100 - 0.0185) / vol if vol > 0 else np.nan
    return {"total": total, "ann": ann, "mdd": mdd, "sharpe": sharpe}


# ================= 5. 顶部指标卡（跟随图一日期动态计算）=================
st.title("REITs二级策略跟踪")

if _nav_n is not None and len(_nav_n) >= 2:
    nm = _calc_metrics(_nav_n)
    im = _calc_metrics(_idx_n) if _idx_n is not None else {}
    label_period = f"{fig1_base} ~ {_nav_n.index[-1].date()}"
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        delta = f"指数 {_fmt_pct(im.get('total'))}" if im else None
        st.metric(f"区间总收益\n({label_period})", _fmt_pct(nm.get("total")), delta=delta)
    with m2:
        delta = f"指数 {_fmt_pct(im.get('ann'))}" if im else None
        st.metric("年化收益率", _fmt_pct(nm.get("ann")), delta=delta)
    with m3:
        delta = f"指数 {_fmt_pct(im.get('mdd'))}" if im else None
        st.metric("最大回撤", _fmt_pct(nm.get("mdd")), delta=delta)
    with m4:
        delta = f"指数 {im.get('sharpe'):.2f}" if im and pd.notna(im.get('sharpe')) else None
        st.metric("夏普比率", f"{nm.get('sharpe'):.2f}" if pd.notna(nm.get("sharpe")) else "N/A", delta=delta)
else:
    st.info("请在侧边栏调整「图一归一化基准日」，使其在数据范围内")
st.divider()

st.subheader("一、REITs二级策略跟踪")

if not df_p1.empty and "nav_n" in df_p1.columns:
    alpha_pct = (df_p1["nav_n"] - df_p1["idx_n"]) * 100

    # go.Figure + yaxis2 overlaying：同一SVG层，trace顺序即z顺序
    # 面积先加（y2，渲染在下） → 折线后加（y1，渲染在上）
    fig1 = go.Figure()
    fig1.add_trace(
        go.Scatter(x=df_p1.index, y=alpha_pct, name="超额(%)",
                   fill="tozeroy", fillcolor=excess_fill,
                   line=dict(color="rgba(0,0,0,0)", width=0),
                   hovertemplate="%{y:.2f}%", yaxis="y2")
    )
    fig1.add_trace(
        go.Scatter(x=df_p1.index, y=df_p1["idx_n"], name="REITs指数",
                   line=dict(color=idx_color, width=2.5),
                   hovertemplate="%{y:.3f}")
    )
    fig1.add_trace(
        go.Scatter(x=df_p1.index, y=df_p1["nav_n"], name="账户净值",
                   line=dict(color=nav_color, width=3.5),
                   hovertemplate="%{y:.3f}")
    )
    fig1.update_layout(
        template=template, height=chart_height, hovermode="x unified",
        margin=dict(l=10, r=60, t=30, b=60),
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5,
                    font=_font9),
        uirevision=str(_fig1_base),
        xaxis=dict(tickfont=_font9),
        yaxis=dict(title="归一化净值 / 指数", showgrid=True, gridcolor=grid_color,
                   tickfont=_font9, title_font=_font9),
        yaxis2=dict(title="区间超额 (%)", overlaying="y", side="right", showgrid=False,
                    zeroline=False, tickfont=_font9, title_font=_font9),
    )
    st.plotly_chart(fig1, width='stretch')
else:
    st.info("所选区间内无有效净值/指数数据")

# ================= 月度收益（紧跟净值图，同起点）=================
st.markdown("<div style='margin-top:2.5rem'></div>", unsafe_allow_html=True)
st.subheader("二、时间归因分析：分月收益对比")

if perf_monthly is not None and not perf_monthly.empty:
    base_month_str = _fig1_base.strftime("%Y-%m")
    pm = perf_monthly[~perf_monthly["period"].str.contains("至今", na=False)].copy()
    pm = pm[pm["period"] >= base_month_str]
    if not pm.empty:
        fig_m = go.Figure()
        fig_m.add_trace(
            go.Bar(x=pm["period"], y=pm["nav_return"], name="账户收益 (%)",
                   marker_color=nav_color,
                   text=pm["nav_return"].round(2).astype(str) + "%", textposition="outside")
        )
        fig_m.add_trace(
            go.Bar(x=pm["period"], y=pm["idx_return"], name="指数收益 (%)",
                   marker_color=idx_color,
                   text=pm["idx_return"].round(2).astype(str) + "%", textposition="outside")
        )
        fig_m.update_layout(
            template=template, height=chart_height, barmode="group",
            margin=dict(l=10, r=60, t=30, b=60),
            legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5,
                        font=_font9),
            yaxis=dict(title="收益率 (%)", tickfont=_font9, title_font=_font9),
            xaxis=dict(tickfont=_font9),
            uirevision=str(_fig1_base),
        )
        st.plotly_chart(fig_m, width='stretch')
    else:
        st.info("基准日之后暂无完整月度数据")

# ================= 图三：调仓意图扫描仪 =================
st.markdown("<div style='margin-top:2.5rem'></div>", unsafe_allow_html=True)
st.subheader("三、主动操作复盘：调仓意图扫描仪 (ppt)")

if not df_p.empty:
    fig2 = make_subplots(specs=[[{"secondary_y": True}]])
    fig2.add_trace(
        go.Scatter(x=df_p.index, y=df_p["指数绝对值"], name="指数",
                   line=dict(color=text_color, width=2.5)),
        secondary_y=False,
    )
    p_chg = df_p["仓位变动"].fillna(0) * 100
    fig2.add_trace(
        go.Bar(x=df_p.index, y=p_chg, name="调仓ppt",
               marker_color=[nav_color if v > 0 else bull_color for v in p_chg]),
        secondary_y=True,
    )
    fig2.update_yaxes(
        title_text="指数", showgrid=True, gridcolor=grid_color, secondary_y=False,
        tickfont=_font9, title_font=_font9,
    )
    fig2.update_yaxes(
        title_text="仓位变动 (ppt)", secondary_y=True, showgrid=False,
        tickfont=_font9, title_font=_font9,
    )
    fig2.update_xaxes(tickfont=_font9)
    fig2.update_layout(
        template=template, height=chart_height, margin=dict(l=10, r=60, t=30, b=60),
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5,
                    font=_font9),
        uirevision=f"{_start_date}_{_end_date}",
    )
    st.plotly_chart(fig2, width='stretch')

# ================= 图四：实际仓位水位 =================
st.markdown("<div style='margin-top:2.5rem'></div>", unsafe_allow_html=True)
st.subheader("四、持仓状态监控：实际仓位水位 (%)")

if not df_p.empty:
    fig3 = make_subplots(specs=[[{"secondary_y": True}]])
    p_lvl = df_p["仓位"].fillna(0) * 100
    p_base = max(0.0, float(p_lvl.min()) - 5)
    fig3.add_trace(
        go.Scatter(x=df_p.index, y=df_p["指数绝对值"], name="指数",
                   line=dict(color=text_color, width=2.5)),
        secondary_y=False,
    )
    # 隐形基线，与 tonexty 搭配实现贴近数据的填充（不从 0 开始）
    fig3.add_trace(
        go.Scatter(x=df_p.index, y=[p_base] * len(df_p), showlegend=False,
                   line=dict(color="rgba(0,0,0,0)", width=0)),
        secondary_y=True,
    )
    fig3.add_trace(
        go.Scatter(x=df_p.index, y=p_lvl, fill="tonexty", name="仓位水位",
                   line=dict(color=pos_line, width=2),
                   fillcolor=pos_fill),
        secondary_y=True,
    )
    fig3.update_yaxes(
        title_text="指数", showgrid=True, gridcolor=grid_color, secondary_y=False,
        tickfont=_font9, title_font=_font9,
    )
    fig3.update_yaxes(
        title_text="仓位水位 (%)", secondary_y=True, showgrid=False,
        range=[p_base, float(p_lvl.max()) + 3],
        tickfont=_font9, title_font=_font9,
    )
    fig3.update_xaxes(tickfont=_font9)
    fig3.update_layout(
        template=template, height=chart_height, margin=dict(l=10, r=60, t=30, b=60),
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5,
                    font=_font9),
        uirevision=f"{_start_date}_{_end_date}",
    )
    st.plotly_chart(fig3, width='stretch')

# ================= 图五：板块配置偏移（期初 vs 期末双图）=================
st.markdown("<div style='margin-top:2.5rem'></div>", unsafe_allow_html=True)
st.subheader("五、结构暴露检查：板块配置偏移 (ppt)")

if not bias_df.empty:
    # 计算期初/期末截面
    bias_start = _sector_bias_at(_start_date, holdings_df, prices_df, info_df, bias_df)
    bias_end   = bias_df.copy()  # 最新持仓即期末截面

    # 统一排序（按期末偏移）
    sector_order = bias_end.sort_values("weight_bias")["sector"].tolist()
    bias_start = bias_start.set_index("sector").reindex(sector_order).reset_index()
    bias_end   = bias_end.set_index("sector").reindex(sector_order).reset_index()

    # 统一坐标轴范围
    max_abs = max(
        bias_start["weight_bias"].abs().max(),
        bias_end["weight_bias"].abs().max(),
    ) * 100 * 1.25
    max_abs = max(max_abs, 1)

    def _bias_bar(b_df, title_label):
        fig = go.Figure(
            go.Bar(
                x=b_df["weight_bias"] * 100,
                y=b_df["sector"],
                orientation="h",
                marker_color=[bull_color if v < 0 else bear_color for v in b_df["weight_bias"]],
                text=(b_df["weight_bias"] * 100).round(1).astype(str) + " ppt",
                textposition="outside",
            )
        )
        fig.add_vline(x=0, line_color=text_color, line_width=2)
        fig.update_layout(
            template=template, height=chart_height,
            title=dict(text=title_label, x=0.5, font=dict(size=13, color=text_color)),
            xaxis=dict(title="偏移百分点 (ppt)", range=[-max_abs, max_abs],
                       tickfont=_font9, title_font=_font9),
            yaxis=dict(title="板块", tickfont=_font9, title_font=_font9),
            margin=dict(l=10, r=110, t=40, b=20),
            showlegend=False,
            uirevision=f"{_start_date}_{_end_date}_{title_label}",
        )
        return fig

    col_l, col_r = st.columns(2)
    with col_l:
        st.plotly_chart(
            _bias_bar(bias_start, f"期初截面 ({_start_date.date()})"),
            width='stretch'
        )
    with col_r:
        st.plotly_chart(
            _bias_bar(bias_end, f"期末截面 ({_end_date.date()})"),
            width='stretch'
        )

# ================= 图六：板块操作归因气泡图 =================
st.markdown("<div style='margin-top:2.5rem'></div>", unsafe_allow_html=True)
st.subheader("六、战术得失诊断：板块操作归因气泡图")

if not trades_df.empty and not prices_df.empty:
    idx_after = prices_df.index[prices_df.index >= _start_date]
    idx_before = prices_df.index[prices_df.index <= _end_date]
    sd = idx_after.min() if len(idx_after) > 0 else None
    ed = idx_before.max() if len(idx_before) > 0 else None

    if pd.notna(sd) and pd.notna(ed) and sd != ed:
        rets = ((prices_df.loc[ed] / prices_df.loc[sd]) - 1) * 100
        rets_df = (
            rets.reset_index()
            .rename(columns={"index": "code", 0: "ret"})
        )
        rets_df["code"] = rets_df["code"].astype(str).str.zfill(6)
        rets_df = pd.merge(rets_df, info_df[["code", "sector"]], on="code")

        t_mask = (trades_df["date"] >= _start_date) & (trades_df["date"] <= _end_date)
        pt = pd.merge(trades_df[t_mask], info_df[["code", "sector"]], on="code")
        pt["signed"] = pt.apply(
            lambda r: r["amount"] if r["direction"] == "buy" else -r["amount"], axis=1
        )

        pdf = pd.DataFrame({
            "ret": rets_df.groupby("sector")["ret"].mean(),
            "net": pt.groupby("sector")["signed"].sum() / 1e4,
            "vol": pt.groupby("sector")["amount"].sum() / 1e4,
        }).dropna()

        if not pdf.empty:
            mx = (pdf["ret"].abs().max() or 1) * 1.3
            my = (pdf["net"].abs().max() or 1) * 1.3
            font_ann = _font9

            sectors_list = pdf.index.tolist()
            marker_colors = [_bubble_palette[i % len(_bubble_palette)] for i in range(len(sectors_list))]

            fig6 = go.Figure(
                go.Scatter(
                    x=pdf["ret"], y=pdf["net"],
                    mode="markers+text", text=sectors_list, textposition="top center",
                    textfont=_font9,
                    marker=dict(
                        size=np.sqrt(pdf["vol"].clip(lower=0)) * 0.6 + 6,
                        color=marker_colors,
                        line_color="rgba(255,255,255,0.6)", line_width=1.5,
                    ),
                    hovertemplate="<b>%{text}</b><br>涨跌幅: %{x:.2f}%<br>净买入: %{y:.1f}万<extra></extra>",
                )
            )
            fig6.add_hline(y=0, line_dash="dash", line_color=text_color, opacity=0.4)
            fig6.add_vline(x=0, line_dash="dash", line_color=text_color, opacity=0.4)
            fig6.add_annotation(x=mx * 0.7, y=my * 0.7, text="【买对了】超配强势板块",
                                 showarrow=False, font=font_ann, opacity=0.55)
            fig6.add_annotation(x=-mx * 0.7, y=-my * 0.7, text="【卖对了】低配弱势板块",
                                 showarrow=False, font=font_ann, opacity=0.55)
            fig6.add_annotation(x=mx * 0.7, y=-my * 0.7, text="【卖飞了】踏空板块涨幅",
                                 showarrow=False, font=font_ann, opacity=0.55)
            fig6.add_annotation(x=-mx * 0.7, y=my * 0.7, text="【买套了】逆势加仓弱势",
                                 showarrow=False, font=font_ann, opacity=0.55)
            fig6.update_layout(
                template=template, height=chart_height + 100,
                xaxis=dict(range=[-mx, mx], title="区间涨跌幅 (%)",
                           tickfont=_font9, title_font=_font9),
                yaxis=dict(range=[-my, my], title="区间净买入 (万元)",
                           tickfont=_font9, title_font=_font9),
                margin=dict(l=10, r=60, t=30, b=30),
                showlegend=False,
                uirevision=f"{_start_date}_{_end_date}",
            )
            st.plotly_chart(fig6, width='stretch')
        else:
            st.info("所选区间内无板块交易数据")
    else:
        st.info("所选区间内无有效行情数据")
