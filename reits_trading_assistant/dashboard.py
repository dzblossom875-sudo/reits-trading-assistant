import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================= 1. 页面配置与主题切换 =================
st.set_page_config(page_title="REITs 二级策略看板", layout="wide", page_icon="📈")

# 侧边栏控制
st.sidebar.header("🎨 视觉控制")
theme_mode = st.sidebar.radio("显示模式", ["Light", "Dark"], index=0)
# 增加一键缩放选项：控制页面整体留白宽度
page_width_opt = st.sidebar.selectbox("页面布局宽度", ["研报中心 (950px)", "黄金比例 (1100px)", "全屏自适应"], index=0)

# 主题颜色适配
if theme_mode == "Dark":
    bg_color, text_color, grid_color, template = "#0e1117", "#e8e6e0", "#31333f", "plotly_dark"
else:
    bg_color, text_color, grid_color, template = "#ffffff", "#1a1a1a", "#eee", "plotly_white"

# 页面宽度逻辑
width_map = {"研报中心 (950px)": 950, "黄金比例 (1100px)": 1100, "全屏自适应": 1600}
container_width = width_map[page_width_opt]

# 注入 CSS
st.markdown(f"""
    <style>
    .main .block-container {{
        max-width: {container_width}px; 
        padding-top: 1.5rem; 
        margin: 0 auto;
        background-color: {bg_color};
    }}
    [data-testid="stMetricValue"] {{font-size: 1.8rem; color: #d62728; font-weight: 700;}}
    .stMetric {{background-color: {bg_color}; padding: 15px; border-radius: 10px; border: 1px solid {grid_color};}}
    .stSubheader {{margin-top: 40px; border-left: 6px solid #d62728; padding-left: 15px; background: {bg_color};}}
    </style>
    """, unsafe_allow_html=True)

# ================= 2. 数据加载 =================
@st.cache_data
def load_all_data():
    try:
        df = pd.read_parquet("data/processed/daily_master.parquet")
        perf_metrics = pd.read_parquet("data/processed/performance_summary_metrics.parquet")
        perf_monthly = pd.read_parquet("data/processed/performance_summary_monthly.parquet")
        bias_df = pd.read_parquet("data/processed/allocation_bias_sector.parquet").rename(columns={'板块': 'sector', '偏移': 'weight_bias'})
        trades_df = pd.read_csv("data/processed/trades_clean.csv", parse_dates=['date'])
        trades_df['code'] = trades_df['code'].astype(str).str.zfill(6)
        info_df = pd.read_csv("data/processed/reits_info.csv")
        info_df['code'] = info_df['code'].astype(str).str.zfill(6)
        prices_df = pd.read_csv("data/processed/wind_prices_cache.csv", index_col=0, parse_dates=True)
        return df.ffill(), perf_metrics, perf_monthly, bias_df, trades_df, info_df, prices_df
    except Exception as e:
        st.error(f"❌ 数据源异常: {e}"); st.stop()

df, perf_metrics, perf_monthly, bias_df, trades_df, info_df, prices_df = load_all_data()

# ================= 3. 时间与区间控制 =================
st.sidebar.header("🕹️ 时间轴")
min_d, max_d = df.index.min().date(), df.index.max().date()
# 强制默认起始日：2024-02-08
default_start = pd.to_datetime("2024-02-08").date()
start_date = st.sidebar.date_input("分析起始日", value=default_start if default_start >= min_d else min_d)
end_date = st.sidebar.date_input("分析结束日", value=max_d)

# ================= 4. 顶部核心指标 =================
st.title("🛡️ REITs 二级策略复盘")
m1, m2, m3, m4 = st.columns(4)
with m1: st.metric("区间总收益", perf_metrics.loc['区间总收益率', perf_metrics.columns[0]])
with m2: st.metric("年化收益率", perf_metrics.loc['年化收益率', perf_metrics.columns[0]])
with m3: st.metric("最大回撤", perf_metrics.loc['最大回撤', perf_metrics.columns[0]])
with m4: 
    s_row = perf_metrics.index[perf_metrics.index.str.contains('夏普')][0]
    st.metric("夏普比率", perf_metrics.loc[s_row, perf_metrics.columns[0]])
st.divider()

# ================= 5. 单列滚动大图 (对齐截图样式) =================

# --- 1. REITs二级策略 (核心改动：Autoscale + 对齐截图) ---
st.subheader("一、核心归因：REITs 二级策略")
df_p = df[(df.index >= pd.to_datetime(start_date)) & (df.index <= pd.to_datetime(end_date))].copy()

if not df_p.empty:
    v_s = df_p.dropna(subset=['净值(基准2022-11-24)', '指数(基准2022-11-24)']).iloc[0]
    df_p['nav_n'] = df_p['净值(基准2022-11-24)'] / v_s['净值(基准2022-11-24)']
    df_p['idx_n'] = df_p['指数(基准2022-11-24)'] / v_s['指数(基准2022-11-24)']
    alpha_pct = (df_p['nav_n'] - df_p['idx_n']) * 100
    
    fig1 = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 连续超额面积 (右轴) - 严格保留两位小数与%
    fig1.add_trace(go.Scatter(x=df_p.index, y=alpha_pct.clip(lower=0), name="正超额(%)", fill='tozeroy', fillcolor='rgba(214,39,40,0.2)', line_width=0, hovertemplate="%{y:.2f}%"), secondary_y=True)
    fig1.add_trace(go.Scatter(x=df_p.index, y=alpha_pct.clip(upper=0), name="负超额(%)", fill='tozeroy', fillcolor='rgba(44,160,44,0.2)', line_width=0, hovertemplate="%{y:.2f}%"), secondary_y=True)
    
    # 指数与净值 (左轴) - 两位小数
    fig1.add_trace(go.Scatter(x=df_p.index, y=df_p['idx_n'], name="REITs指数", line=dict(color="#1f77b4", width=3.5), hovertemplate="%{y:.2f}"), secondary_y=False)
    fig1.add_trace(go.Scatter(x=df_p.index, y=df_p['nav_n'], name="账户净值", line=dict(color="#d62728", width=3.5), hovertemplate="%{y:.2f}"), secondary_y=False)
    
    # 核心：Autoscale 样式对齐
    fig1.update_layout(
        template=template, height=450, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=0, r=0, t=30, b=0), # 移除边缘留白，实现截图里的“满格感”
        xaxis=dict(range=[df_p.index.min(), df_p.index.max()], autorange=False) # 强制对齐起止日期
    )
    
    fig1.update_yaxes(title_text="归一化净值 / 指数 (左轴)", showgrid=True, gridcolor=grid_color, secondary_y=False)
    # 压低右轴，确保超额面积图只在底部 (对齐截图 3.5倍缩放逻辑)
    max_a = alpha_pct.abs().max() or 1
    fig1.update_yaxes(title_text="区间超额 (%) (右轴)", range=[-max_a*3.5, max_a*3.5], showgrid=False, secondary_y=True)
    
    st.plotly_chart(fig1, use_container_width=True)

# --- 2. 调仓意图与水位 (研报长条 2.5:1) ---
st.subheader("二、主动调仓：意图扫描 (ppt) 与 水位 (%)")
df_t = df_p.copy()
if not df_t.empty:
    # 意图图
    fig2 = make_subplots(specs=[[{"secondary_y": True}]])
    fig2.add_trace(go.Scatter(x=df_t.index, y=df_t['指数绝对值'], name="指数", line=dict(color=text_color, width=2.5)), secondary_y=False)
    p_chg = df_t['仓位变动'].fillna(0) * 100
    fig2.add_trace(go.Bar(x=df_t.index, y=p_chg, name="调仓ppt", marker_color=["#d62728" if v>0 else "#1f77b4" for v in p_chg]), secondary_y=True)
    mx_chg = p_chg.abs().max() or 1
    fig2.update_yaxes(range=[-mx_chg*2, mx_chg*2], secondary_y=True, showgrid=False)
    fig2.update_layout(template=template, height=350, title="主动调仓意图 (每日仓位ppt变动)", margin=dict(l=0, r=0))
    st.plotly_chart(fig2, use_container_width=True)

    # 水位图
    fig3 = make_subplots(specs=[[{"secondary_y": True}]])
    p_lvl = df_t['仓位'].fillna(0) * 100
    fig3.add_trace(go.Scatter(x=df_t.index, y=df_t['指数绝对值'], name="指数", line=dict(color=text_color, width=2)), secondary_y=False)
    fig3.add_trace(go.Scatter(x=df_t.index, y=p_lvl, fill='tozeroy', name="仓位%", fillcolor='rgba(93,173,226,0.15)', line_width=2), secondary_y=True)
    fig3.update_yaxes(range=[max(0, p_lvl.min()-5), p_lvl.max()+5], secondary_y=True, showgrid=False)
    fig3.update_layout(template=template, height=350, title="实际仓位水位监控 (%)", margin=dict(l=0, r=0))
    st.plotly_chart(fig3, use_container_width=True)

# --- 3. 气泡归因 (绝对对称) ---
st.subheader("三、战术诊断：板块操作归因气泡图")
if not trades_df.empty and not prices_df.empty:
    ed_p = prices_df.index[prices_df.index <= pd.to_datetime(end_date)].max()
    st_p = prices_df.index[prices_df.index >= pd.to_datetime(start_date)].min()
    
    if ed_p and st_p:
        rets = ((prices_df.loc[ed_p] / prices_df.loc[st_p]) - 1) * 100
        rets = pd.merge(rets.reset_index().rename(columns={'index':'code', 0:'ret'}), info_df[['code', 'sector']], on='code')
        t_mask = (trades_df['date'].dt.date >= start_date) & (trades_df['date'].dt.date <= end_date)
        pt = pd.merge(trades_df[t_mask], info_df[['code', 'sector']], on='code')
        pt['signed'] = pt.apply(lambda r: r['amount'] if r['direction']=='buy' else -r['amount'], axis=1)
        
        pdf = pd.DataFrame({'ret': rets.groupby('sector')['ret'].mean(), 'net': pt.groupby('sector')['signed'].sum()/1e4, 'vol': pt.groupby('sector')['amount'].sum()/1e4}).dropna()
        
        if not pdf.empty:
            mx, my = pdf['ret'].abs().max() * 1.3, pdf['net'].abs().max() * 1.3
            fig6 = go.Figure(go.Scatter(x=pdf['ret'], y=pdf['net'], mode='markers+text', text=pdf.index, textposition="top center", 
                             marker=dict(size=np.sqrt(pdf['vol'])*0.5 + 6, color=pdf['ret'], colorscale='RdYlGn_r', showscale=False)))
            fig6.add_hline(y=0, line_dash="dash", line_color="gray"); fig6.add_vline(x=0, line_dash="dash", line_color="gray")
            # 象限标注
            fig6.add_annotation(x=mx*0.7, y=my*0.7, text="【买对了】", showarrow=False, font_size=12, opacity=0.5)
            fig6.add_annotation(x=-mx*0.7, y=-my*0.7, text="【卖对了】", showarrow=False, font_size=12, opacity=0.5)
            fig6.update_layout(template=template, height=550, xaxis_range=[-mx, mx], yaxis_range=[-my, my], margin=dict(l=0, r=0))
            st.plotly_chart(fig6, use_container_width=True)