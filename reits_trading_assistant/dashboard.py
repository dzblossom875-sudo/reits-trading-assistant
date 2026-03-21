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
st.set_page_config(page_title="REITs 二级策略看板", layout="wide", page_icon="📈")

st.sidebar.header("🎨 视觉与排版")
theme_mode = st.sidebar.radio("显示主题", ["Light 模式", "Dark 模式"], index=0)
aspect_ratio = st.sidebar.radio(
    "页面比例",
    ["研报长条 (2.5:1, 留白)", "标准宽屏 (16:9, 铺满)"],
    index=0,
)

if theme_mode == "Dark 模式":
    bg_color, text_color, grid_color, template = "#0e1117", "#e8e6e0", "#333333", "plotly_dark"
else:
    bg_color, text_color, grid_color, template = "#ffffff", "#1a1a1a", "#eeeeee", "plotly_white"

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
    [data-testid="stMetricValue"] {{font-size: 1.8rem; color: #d62728; font-weight: 700;}}
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
        return df.ffill(), perf_metrics, perf_monthly, bias_df, trades_df, info_df, prices_df
    except Exception as e:
        st.error(f"❌ 数据源异常: {e}")
        st.stop()

df, perf_metrics, perf_monthly, bias_df, trades_df, info_df, prices_df = load_all_data()

# ================= 3. 时间轴控制 =================
min_d, max_d = df.index.min().date(), df.index.max().date()
default_start = max(pd.to_datetime("2024-02-08").date(), min_d)

# --- 图一独立控件（放最上方）---
st.sidebar.header("📈 图一：核心趋势")
fig1_start = st.sidebar.date_input("图一起始日", value=min_d, key="fig1_start")
fig1_base = st.sidebar.date_input(
    "图一归一化基准日",
    value=default_start,
    key="fig1_base",
    help="净值/指数从此日重新归一到 1.0，不影响顶部指标卡",
)

# --- 图二~六共用控件 ---
st.sidebar.header("📊 图二~六：区间分析")
start_date = st.sidebar.date_input("起始日 (默认2024-02-08)", value=default_start, key="main_start")
end_date = st.sidebar.date_input("结束日", value=max_d, key="main_end")

# ================= 4. 预计算图一归一化（指标卡依赖此结果）=================
# date_input 清空时返回 None，需用默认值兜底
_fig1_start = pd.to_datetime(fig1_start) if fig1_start else pd.to_datetime(min_d)
_fig1_base  = pd.to_datetime(fig1_base)  if fig1_base  else pd.to_datetime(default_start)
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
st.title("🛡️ REITs 投资策略全景看板")

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

# ================= 图一：核心趋势归因 =================
st.subheader("一、核心趋势归因：REITs 二级策略")

if not df_p1.empty and "nav_n" in df_p1.columns:
    alpha_pct = (df_p1["nav_n"] - df_p1["idx_n"]) * 100

    fig1 = make_subplots(specs=[[{"secondary_y": True}]])
    fig1.add_trace(
        go.Scatter(x=df_p1.index, y=alpha_pct.clip(lower=0), name="正超额(%)",
                   fill="tozeroy", fillcolor="rgba(214,39,40,0.25)", line_width=0,
                   hovertemplate="%{y:.2f}%"),
        secondary_y=True,
    )
    fig1.add_trace(
        go.Scatter(x=df_p1.index, y=alpha_pct.clip(upper=0), name="负超额(%)",
                   fill="tozeroy", fillcolor="rgba(44,160,44,0.25)", line_width=0,
                   hovertemplate="%{y:.2f}%"),
        secondary_y=True,
    )
    fig1.add_trace(
        go.Scatter(x=df_p1.index, y=df_p1["idx_n"], name="REITs指数",
                   line=dict(color="#1f77b4", width=3.5), hovertemplate="%{y:.3f}"),
        secondary_y=False,
    )
    fig1.add_trace(
        go.Scatter(x=df_p1.index, y=df_p1["nav_n"], name="账户净值",
                   line=dict(color="#d62728", width=3.5), hovertemplate="%{y:.3f}"),
        secondary_y=False,
    )
    fig1.update_layout(
        template=template, height=chart_height, hovermode="x unified",
        margin=dict(l=0, r=0, t=20, b=50),
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5),
        xaxis=dict(range=[df_p1.index.min(), df_p1.index.max()], autorange=False),
    )
    all_vals = pd.concat([df_p1["nav_n"], df_p1["idx_n"]]).dropna()
    pad = (all_vals.max() - all_vals.min()) * 0.05 or 0.01
    fig1.update_yaxes(
        title_text="归一化净值 / 指数", showgrid=True, gridcolor=grid_color,
        secondary_y=False,
        range=[all_vals.min() - pad, all_vals.max() + pad],
    )
    max_a = alpha_pct.abs().max() or 1
    fig1.update_yaxes(
        title_text="区间超额 (%)", range=[-max_a * 3.5, max_a * 3.5],
        showgrid=False, secondary_y=True,
    )
    st.plotly_chart(fig1, width='stretch')
else:
    st.info("所选区间内无有效净值/指数数据")

# ================= 图二：调仓意图扫描仪 =================
st.subheader("二、主动操作复盘：调仓意图扫描仪 (ppt)")

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
               marker_color=["#d62728" if v > 0 else "#1f77b4" for v in p_chg]),
        secondary_y=True,
    )
    # 左轴（指数）手动 range，防止 Plotly 双轴时互相压缩
    idx_vals = df_p["指数绝对值"].dropna()
    idx_pad = (idx_vals.max() - idx_vals.min()) * 0.05 or 1
    fig2.update_yaxes(
        range=[idx_vals.min() - idx_pad, idx_vals.max() + idx_pad],
        title_text="指数", showgrid=True, gridcolor=grid_color, secondary_y=False,
    )
    # 右轴用 95 分位数定高度，避免单个大变动把所有小柱压扁
    nz = p_chg[p_chg != 0].abs()
    mx_chg = float(np.percentile(nz, 95)) * 1.5 if len(nz) >= 5 else (nz.max() or 1)
    fig2.update_yaxes(
        range=[-mx_chg * 1.5, mx_chg * 1.5], title_text="仓位变动 (ppt)",
        secondary_y=True, showgrid=False,
    )
    fig2.update_layout(
        template=template, height=chart_height, margin=dict(l=0, r=0, t=20, b=50),
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5),
    )
    st.plotly_chart(fig2, width='stretch')

# ================= 图三：实际仓位水位 =================
st.subheader("三、持仓状态监控：实际仓位水位 (%)")

if not df_p.empty:
    fig3 = make_subplots(specs=[[{"secondary_y": True}]])
    p_lvl = df_p["仓位"].fillna(0) * 100
    fig3.add_trace(
        go.Scatter(x=df_p.index, y=df_p["指数绝对值"], name="指数",
                   line=dict(color=text_color, width=2)),
        secondary_y=False,
    )
    fig3.add_trace(
        go.Scatter(x=df_p.index, y=p_lvl, fill="tozeroy", name="仓位水位",
                   line=dict(color="#5DADE2", width=2), fillcolor="rgba(93,173,226,0.2)"),
        secondary_y=True,
    )
    # 左轴（指数）手动 range
    idx_vals3 = df_p["指数绝对值"].dropna()
    idx_pad3 = (idx_vals3.max() - idx_vals3.min()) * 0.05 or 1
    fig3.update_yaxes(
        range=[idx_vals3.min() - idx_pad3, idx_vals3.max() + idx_pad3],
        title_text="指数", showgrid=True, gridcolor=grid_color, secondary_y=False,
    )
    y_min = max(0, p_lvl.min() - 5)
    y_max = p_lvl.max() + 5 if p_lvl.max() > 0 else 110
    fig3.update_yaxes(
        range=[y_min, y_max], title_text="仓位水位 (%)",
        secondary_y=True, showgrid=False,
    )
    fig3.update_layout(
        template=template, height=chart_height, margin=dict(l=0, r=0, t=20, b=50),
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5),
    )
    st.plotly_chart(fig3, width='stretch')

# ================= 图四：板块配置偏移 =================
st.subheader("四、结构暴露检查：最新板块配置偏移 (ppt)")

if not bias_df.empty:
    b_s = bias_df.sort_values("weight_bias")
    fig4 = go.Figure(
        go.Bar(
            x=b_s["weight_bias"] * 100,
            y=b_s["sector"],
            orientation="h",
            marker_color=["#2ca02c" if v < 0 else "#d62728" for v in b_s["weight_bias"]],
            text=(b_s["weight_bias"] * 100).round(1).astype(str) + " ppt",
            textposition="outside",
        )
    )
    fig4.add_vline(x=0, line_color=text_color, line_width=2)
    fig4.update_layout(
        template=template, height=chart_height,
        xaxis_title="偏移百分点 (ppt)", yaxis_title="板块",
        margin=dict(l=0, r=80, t=20, b=20),
        showlegend=False,
    )
    st.plotly_chart(fig4, width='stretch')

# ================= 图五：分月收益对比 =================
st.subheader("五、时间归因分析：分月收益对比")

if perf_monthly is not None and not perf_monthly.empty:
    # nav_return 已是百分比值（e.g. 4.807 = 4.807%），不需要再 *100
    pm = perf_monthly[~perf_monthly["period"].str.contains("至今", na=False)].copy()
    if not pm.empty:
        fig5 = go.Figure()
        fig5.add_trace(
            go.Bar(x=pm["period"], y=pm["nav_return"], name="账户收益 (%)",
                   marker_color="#d62728",
                   text=pm["nav_return"].round(2).astype(str) + "%", textposition="outside")
        )
        fig5.add_trace(
            go.Bar(x=pm["period"], y=pm["idx_return"], name="指数收益 (%)",
                   marker_color="#1f77b4",
                   text=pm["idx_return"].round(2).astype(str) + "%", textposition="outside")
        )
        fig5.update_layout(
            template=template, height=chart_height, barmode="group",
            yaxis_title="收益率 (%)", margin=dict(l=0, r=0, t=20, b=50),
            legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5),
        )
        st.plotly_chart(fig5, width='stretch')

# ================= 图六：板块操作归因气泡图 =================
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
            font_ann = dict(size=13, color=text_color)

            fig6 = go.Figure(
                go.Scatter(
                    x=pdf["ret"], y=pdf["net"],
                    mode="markers+text", text=pdf.index, textposition="top center",
                    marker=dict(
                        size=np.sqrt(pdf["vol"].clip(lower=0)) * 0.6 + 6,
                        color=pdf["ret"], colorscale="RdYlGn_r",
                        line_width=1.5, showscale=False,
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
                xaxis_range=[-mx, mx], yaxis_range=[-my, my],
                xaxis_title="区间涨跌幅 (%)", yaxis_title="区间净买入 (万元)",
                margin=dict(l=0, r=0, t=20, b=20),
                showlegend=False,
            )
            st.plotly_chart(fig6, width='stretch')
        else:
            st.info("所选区间内无板块交易数据")
    else:
        st.info("所选区间内无有效行情数据")
