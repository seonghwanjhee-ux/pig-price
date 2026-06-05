"""
돼지 가축시장 경락가격 — Streamlit 인터랙티브 대시보드
실행: streamlit run pig_app.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, timedelta
from pathlib import Path

# pig_dashboard.py의 함수 재사용
from pig_dashboard import (
    load_history, update_history, save_history,
    find_latest_data_day, scrape_pig_price,
    calc_3day_avg, business_days_range, prev_business_day,
    MIN_MARKETS, fmt,
)

CSV_PATH = Path(__file__).parent / "pig_price_history.csv"

# ── 페이지 설정 ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="돼지 경락가격 대시보드",
    page_icon="🐷",
    layout="wide",
)

st.markdown("""
<style>
    .kpi-box {
        background: white;
        border: 1px solid #dee2e6;
        border-radius: 10px;
        padding: 18px 10px 14px 10px;
        text-align: center;
    }
    .kpi-label { font-size: 12px; color: #7f8c8d; line-height: 1.6; }
    .kpi-value { font-size: 22px; font-weight: bold; margin: 6px 0 2px 0; }
    .kpi-sub   { font-size: 13px; margin-top: 2px; }
    .block-container { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)


# ── 데이터 로드 ───────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def get_data():
    try:
        return load_history()
    except Exception as e:
        st.warning(f"데이터 로드 실패: {str(e)}")
        return pd.DataFrame(columns=["date", "price", "count", "market_cnt"])


def refresh_data():
    st.cache_data.clear()


# ── 사이드바 ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🐷 돼지 경락가격")
    st.caption("출처: ekapepia.com\n가축시장·등외제외·전국 제주제외")
    st.divider()

    # 데이터 수집은 GitHub Actions에서만 자동 실행
    st.info("ℹ️ 데이터는 매일 자동으로 수집됩니다 (GitHub Actions)")
    st.caption("로컬 PC에서 수동 수집: python pig_dashboard.py")

    st.divider()

    # 날짜 범위 선택
    st.subheader("기간 선택")
    df_all = get_data()

    preset = st.radio("빠른 선택", ["1개월", "3개월", "6개월", "전체"], index=1, horizontal=True)
    today = date.today()
    if preset == "1개월":
        default_start = today - timedelta(days=30)
    elif preset == "3개월":
        default_start = today - timedelta(days=90)
    elif preset == "6개월":
        default_start = today - timedelta(days=180)
    else:
        default_start = df_all["date"].min().date() if len(df_all) else today - timedelta(days=90)

    min_date = df_all["date"].min().date() if len(df_all) else today - timedelta(days=365)
    max_date = df_all["date"].max().date() if len(df_all) else today

    date_start = st.date_input("시작일", value=max(default_start, min_date),
                               min_value=min_date, max_value=max_date)
    date_end   = st.date_input("종료일", value=max_date,
                               min_value=min_date, max_value=max_date)

    st.divider()
    st.caption("Y축 범위 (원/kg)")
    y_min = st.number_input("최소", value=3500, step=500)
    y_max = st.number_input("최대", value=7500, step=500)


# ── 데이터 필터링 ─────────────────────────────────────────────────────────────
df_all = get_data()

if len(df_all) == 0:
    st.warning("데이터가 없습니다. 사이드바에서 데이터를 수집해 주세요.")
    st.stop()

mask = (df_all["date"].dt.date >= date_start) & (df_all["date"].dt.date <= date_end)
df = df_all[mask].copy().reset_index(drop=True)
df["avg3"] = calc_3day_avg(df)

if len(df) == 0:
    st.warning("선택한 기간에 데이터가 없습니다.")
    st.stop()

valid_df   = df[df["price"].notna()]
latest     = valid_df.iloc[-1] if len(valid_df) else df.iloc[-1]
prev_valid = valid_df.iloc[-2] if len(valid_df) >= 2 else None

l_price = latest["price"] if pd.notna(latest["price"]) else None
last3   = valid_df["price"].tail(3).tolist()
l_avg3  = round(sum(last3) / len(last3), 1) if last3 else None

prev3 = valid_df["price"].iloc[-6:-3].tolist()
if l_avg3 and len(prev3) >= 1:
    prev_avg3 = round(sum(prev3) / len(prev3), 1)
    avg3_dv   = l_avg3 - prev_avg3
    avg3_ds   = "%+.0f원 (%+.1f%%)" % (avg3_dv, avg3_dv / prev_avg3 * 100)
    avg3_dc   = "#e74c3c" if avg3_dv >= 0 else "#2980b9"
else:
    avg3_ds, avg3_dc = None, "#7f8c8d"

l_cnt = int(latest["count"])
l_mkt = int(latest.get("market_cnt", 0))
l_date_str = latest["date"].strftime("%Y-%m-%d (%a)").replace(
    "Mon","월").replace("Tue","화").replace("Wed","수").replace(
    "Thu","목").replace("Fri","금")

if l_price and prev_valid is not None and pd.notna(prev_valid["price"]):
    dv = l_price - prev_valid["price"]
    ds = "%+.0f원 (%+.1f%%)" % (dv, dv / prev_valid["price"] * 100)
    dc = "#e74c3c" if dv >= 0 else "#2980b9"
else:
    ds, dc = "-", "#7f8c8d"


# ── 타이틀 ────────────────────────────────────────────────────────────────────
st.title("🐷 돼지 가축시장 경락가격 대시보드")
st.caption("기준: 가축시장·등외제외·전국 제주제외 / 비제주 개별경매장 %d개 미만 시 경락가 없음" % MIN_MARKETS)


# ── KPI 카드 ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)

def kpi_html(label, value, color, sub=None, sub_color="#7f8c8d"):
    sub_html = f'<div class="kpi-sub" style="color:{sub_color}">{sub}</div>' if sub else ""
    return f"""
    <div class="kpi-box">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value" style="color:{color}">{value}</div>
        {sub_html}
    </div>"""

with c1:
    st.markdown(kpi_html(
        f"전일 경락가격<br>{l_date_str}",
        ("%s원/kg" % fmt(l_price)) if l_price else "경락가 없음",
        "#2c3e50" if l_price else "#e74c3c",
    ), unsafe_allow_html=True)

with c2:
    st.markdown(kpi_html(
        "직전 3거래일 산술평균",
        ("%s원/kg" % fmt(l_avg3)) if l_avg3 else "-",
        "#8e44ad",
        sub=avg3_ds, sub_color=avg3_dc,
    ), unsafe_allow_html=True)

with c3:
    st.markdown(kpi_html(
        "직전 거래일 대비 등락",
        ds, dc,
    ), unsafe_allow_html=True)

with c4:
    st.markdown(kpi_html(
        f"경매 두수 / 경매장<br>{l_date_str}",
        "%s두 / %d개" % (fmt(l_cnt), l_mkt),
        "#27ae60" if l_mkt >= MIN_MARKETS else "#e67e22",
    ), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# ── 경락가격 추이 차트 ────────────────────────────────────────────────────────
valid_mask = df["price"].notna()
no_price   = df[~valid_mask & (df["count"] > 0)]

fig = make_subplots(
    rows=2, cols=2,
    row_heights=[0.62, 0.38],
    specs=[[{"colspan": 2}, None], [{}, {}]],
    subplot_titles=(
        "경락가격 추이  (원/kg)",
        "일별 경매 두수",
        "일별 활성 경매장 수",
    ),
    vertical_spacing=0.12,
    horizontal_spacing=0.08,
)

# 경락가격 선
fig.add_trace(go.Scatter(
    x=df.loc[valid_mask, "date"], y=df.loc[valid_mask, "price"],
    name="전일 경락가격",
    mode="lines+markers",
    line=dict(color="#3498db", width=2),
    marker=dict(size=5),
    fill="tozeroy", fillcolor="rgba(52,152,219,0.07)",
    hovertemplate="%{x|%Y-%m-%d}<br>경락가: <b>%{y:,.0f}원/kg</b><extra></extra>",
), row=1, col=1)

# 3거래일 평균 선
avg_mask = df["avg3"].notna()
fig.add_trace(go.Scatter(
    x=df.loc[avg_mask, "date"], y=df.loc[avg_mask, "avg3"],
    name="직전 3거래일 평균",
    mode="lines+markers",
    line=dict(color="#e74c3c", width=2, dash="dash"),
    marker=dict(size=4, symbol="square"),
    hovertemplate="%{x|%Y-%m-%d}<br>3일평균: <b>%{y:,.0f}원/kg</b><extra></extra>",
), row=1, col=1)

# 경락가 없는 날 수직선
for _, nr in no_price.iterrows():
    x_str = nr["date"].strftime("%Y-%m-%d")
    fig.add_shape(type="line",
        x0=x_str, x1=x_str, y0=y_min, y1=y_max,
        line=dict(color="#e67e22", width=1, dash="dot"),
        row=1, col=1)
    fig.add_annotation(
        x=x_str, y=y_min, text="없음", textangle=-90,
        font=dict(size=9, color="#e67e22"),
        showarrow=False, yanchor="bottom",
        row=1, col=1)

fig.update_yaxes(range=[y_min, y_max], tickformat=",", row=1, col=1)


# 경매 두수 막대
mean_cnt   = df.loc[valid_mask, "count"].mean() if valid_mask.any() else 0
bar_colors = []
for _, row_r in df.iterrows():
    if not pd.notna(row_r.get("price")):
        bar_colors.append("#f0b27a")
    elif row_r["count"] >= mean_cnt:
        bar_colors.append("#2ecc71")
    else:
        bar_colors.append("#95a5a6")

fig.add_trace(go.Bar(
    x=df["date"], y=df["count"],
    name="경매 두수",
    marker_color=bar_colors,
    hovertemplate="%{x|%Y-%m-%d}<br>두수: <b>%{y:,.0f}두</b><extra></extra>",
), row=2, col=1)
fig.add_hline(y=mean_cnt, line_dash="dash", line_color="#e74c3c",
              annotation_text="평균 %s두" % fmt(mean_cnt),
              annotation_position="top right",
              row=2, col=1)
fig.update_yaxes(tickformat=",", row=2, col=1)


# 경매장 수 막대
if "market_cnt" in df.columns:
    mc = pd.to_numeric(df["market_cnt"], errors="coerce").fillna(0)
    mkt_colors = ["#27ae60" if v >= MIN_MARKETS else "#e74c3c" for v in mc]
    fig.add_trace(go.Bar(
        x=df["date"], y=mc,
        name="활성 경매장",
        marker_color=mkt_colors,
        hovertemplate="%{x|%Y-%m-%d}<br>경매장: <b>%{y}개</b><extra></extra>",
    ), row=2, col=2)
    fig.add_hline(y=MIN_MARKETS, line_dash="dash", line_color="#e67e22",
                  annotation_text="기준 %d개" % MIN_MARKETS,
                  annotation_position="top right",
                  row=2, col=2)

fig.update_layout(
    height=680,
    plot_bgcolor="white",
    paper_bgcolor="#f8f9fa",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    margin=dict(l=10, r=10, t=60, b=10),
    hovermode="x unified",
)
fig.update_xaxes(showgrid=False)
fig.update_yaxes(showgrid=True, gridcolor="#f0f0f0")

st.plotly_chart(fig, use_container_width=True)


# ── 데이터 테이블 ─────────────────────────────────────────────────────────────
with st.expander("📋 원본 데이터 보기"):
    show_df = df[["date", "price", "count", "market_cnt", "avg3"]].copy()
    show_df.columns = ["날짜", "경락가(원/kg)", "두수", "경매장수", "3일평균"]
    show_df["날짜"] = show_df["날짜"].dt.strftime("%Y-%m-%d")
    show_df = show_df.sort_values("날짜", ascending=False).reset_index(drop=True)
    st.dataframe(show_df, use_container_width=True, height=300)
