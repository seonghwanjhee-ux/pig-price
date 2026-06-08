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
GITHUB_BASE      = "https://raw.githubusercontent.com/seonghwanjhee-ux/pig-price/data"
GITHUB_CSV_URL   = f"{GITHUB_BASE}/pig_price_all.csv"
GITHUB_MONTH_URL = f"{GITHUB_BASE}/pig_supply_month.csv"
GITHUB_WEEK_URL  = f"{GITHUB_BASE}/pig_supply_week.csv"

@st.cache_data(ttl=3600, show_spinner=False)
def get_data():
    """전체 데이터 로드 (경매장 제한 없음) - 앱에서 필터링"""
    try:
        df = pd.read_csv(GITHUB_CSV_URL, encoding="utf-8-sig")
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        return df.sort_values("date").reset_index(drop=True)
    except Exception as e:
        st.warning(f"경락가격 데이터 로드 실패: {str(e)}")
        return pd.DataFrame(columns=["date", "price", "count", "market_cnt"])

def apply_market_filter(df: pd.DataFrame) -> pd.DataFrame:
    """경매장 5개 미만인 날 price → None 처리 (일별 현황용)"""
    df = df.copy()
    mask = pd.to_numeric(df["market_cnt"], errors="coerce").fillna(0) < MIN_MARKETS
    df.loc[mask, "price"] = None
    return df

@st.cache_data(ttl=3600, show_spinner=False)
def get_supply_month():
    try:
        return pd.read_csv(GITHUB_MONTH_URL, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def get_supply_week():
    try:
        return pd.read_csv(GITHUB_WEEK_URL, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()

def refresh_data():
    st.cache_data.clear()


# ── 사이드바 ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🐷 돼지 경락가격")
    st.caption("출처: ekapepia.com\n가축시장·등외제외·전국 제주제외")
    st.divider()

    st.info("ℹ️ 데이터는 매일 자동으로 수집됩니다 (GitHub Actions)")
    st.caption("로컬 PC에서 수동 수집: python pig_dashboard.py")

    st.divider()

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
df_all_raw = get_data()                        # 제한 없는 원본 (연도별 비교용)
df_all     = apply_market_filter(df_all_raw)   # 경매장 5개 이상 필터 (일별 현황용)

if len(df_all) == 0:
    st.warning("데이터가 없습니다.")
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

tab1, tab2 = st.tabs(["📈 일별 현황", "📦 출하물량 분석"])


# ════════════════════════════════════════════════════════════
# TAB 1: 일별 현황
# ════════════════════════════════════════════════════════════
with tab1:

    # ── KPI 카드 ──────────────────────────────────────────────────────────────
    def kpi_html(label, value, color, sub=None, sub_color="#7f8c8d"):
        sub_html = f'<div class="kpi-sub" style="color:{sub_color}">{sub}</div>' if sub else ""
        return f"""
        <div class="kpi-box">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value" style="color:{color}">{value}</div>
            {sub_html}
        </div>"""

    c1, c2, c3, c4 = st.columns(4)
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

    # ── 2주간 경락가격 표 ──────────────────────────────────────────────────────
    def make_2week_table(df_src: pd.DataFrame) -> pd.DataFrame:
        col_labels = ["월", "화", "수", "목", "금"]
        biz = df_src[df_src["date"].dt.weekday < 5].copy()
        weeks = {}
        for _, r in biz.iterrows():
            iso = r["date"].isocalendar()
            key = (iso[0], iso[1])
            if key not in weeks:
                weeks[key] = {}
            price_str = f"{int(r['price']):,}원" if pd.notna(r["price"]) else "-"
            weeks[key][r["date"].weekday()] = (r["date"].strftime("%m/%d"), price_str)
        last_2_keys = sorted(weeks.keys())[-2:]
        table_rows = []
        for key in last_2_keys:
            week_data = weeks[key]
            dates_in_week = [v[0] for v in week_data.values()]
            date_range = f"{min(dates_in_week)} ~ {max(dates_in_week)}"
            row = {"기간": date_range}
            for i, label in enumerate(col_labels):
                row[label] = week_data[i][1] if i in week_data else "-"
            table_rows.append(row)
        return pd.DataFrame(table_rows)

    st.subheader("최근 2주 경락가격")
    tbl = make_2week_table(df_all)
    st.dataframe(
        tbl, use_container_width=True, hide_index=True,
        column_config={
            "기간": st.column_config.TextColumn("기간", width="medium"),
            **{col: st.column_config.TextColumn(col, width="small") for col in ["월","화","수","목","금"]},
        },
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 차트 옵션 ─────────────────────────────────────────────────────────────
    opt_col1, opt_col2, opt_col3 = st.columns([1, 1, 4])
    with opt_col1:
        show_ma   = st.toggle("3일 이동평균", value=True)
    with opt_col2:
        show_year = st.toggle("연도별 비교", value=False)

    # ── 경락가격 추이 차트 ────────────────────────────────────────────────────
    valid_mask = df["price"].notna()
    no_price   = df[~valid_mask & (df["count"] > 0)]

    if not show_year:
        # ── 일반 뷰 ──────────────────────────────────────────────────────────
        fig = make_subplots(
            rows=2, cols=2,
            row_heights=[0.62, 0.38],
            specs=[[{"colspan": 2}, None], [{}, {}]],
            subplot_titles=("경락가격 추이  (원/kg)", "일별 경매 두수", "일별 활성 경매장 수"),
            vertical_spacing=0.12, horizontal_spacing=0.08,
        )

        fig.add_trace(go.Scatter(
            x=df.loc[valid_mask, "date"], y=df.loc[valid_mask, "price"],
            name="전일 경락가격", mode="lines+markers",
            line=dict(color="#3498db", width=2), marker=dict(size=5),
            fill="tozeroy", fillcolor="rgba(52,152,219,0.07)",
            hovertemplate="%{x|%Y-%m-%d}<br>경락가: <b>%{y:,.0f}원/kg</b><extra></extra>",
        ), row=1, col=1)

        if show_ma:
            avg_mask = df["avg3"].notna()
            fig.add_trace(go.Scatter(
                x=df.loc[avg_mask, "date"], y=df.loc[avg_mask, "avg3"],
                name="3거래일 평균", mode="lines",
                line=dict(color="#e74c3c", width=2, dash="dash"),
                hovertemplate="%{x|%Y-%m-%d}<br>3일평균: <b>%{y:,.0f}원/kg</b><extra></extra>",
            ), row=1, col=1)

        for _, nr in no_price.iterrows():
            x_str = nr["date"].strftime("%Y-%m-%d")
            fig.add_shape(type="line", x0=x_str, x1=x_str, y0=y_min, y1=y_max,
                line=dict(color="#e67e22", width=1, dash="dot"), row=1, col=1)
            fig.add_annotation(x=x_str, y=y_min, text="없음", textangle=-90,
                font=dict(size=9, color="#e67e22"), showarrow=False, yanchor="bottom", row=1, col=1)

        fig.update_yaxes(range=[y_min, y_max], tickformat=",", row=1, col=1)

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
            x=df["date"], y=df["count"], name="경매 두수", marker_color=bar_colors,
            hovertemplate="%{x|%Y-%m-%d}<br>두수: <b>%{y:,.0f}두</b><extra></extra>",
        ), row=2, col=1)
        fig.add_hline(y=mean_cnt, line_dash="dash", line_color="#e74c3c",
                      annotation_text="평균 %s두" % fmt(mean_cnt),
                      annotation_position="top right", row=2, col=1)
        fig.update_yaxes(tickformat=",", row=2, col=1)

        if "market_cnt" in df.columns:
            mc = pd.to_numeric(df["market_cnt"], errors="coerce").fillna(0)
            mkt_colors = ["#27ae60" if v >= MIN_MARKETS else "#e74c3c" for v in mc]
            fig.add_trace(go.Bar(
                x=df["date"], y=mc, name="활성 경매장", marker_color=mkt_colors,
                hovertemplate="%{x|%Y-%m-%d}<br>경매장: <b>%{y}개</b><extra></extra>",
            ), row=2, col=2)
            fig.add_hline(y=MIN_MARKETS, line_dash="dash", line_color="#e67e22",
                          annotation_text="기준 %d개" % MIN_MARKETS,
                          annotation_position="top right", row=2, col=2)

        fig.update_layout(
            height=680, plot_bgcolor="white", paper_bgcolor="#f8f9fa",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            margin=dict(l=10, r=10, t=60, b=10), hovermode="x unified",
        )
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=True, gridcolor="#f0f0f0")
        st.plotly_chart(fig, use_container_width=True)

    else:
        # ── 연도별 비교 뷰 ────────────────────────────────────────────────────
        df_yr_src = df_all_raw  # 경매장 제한 없는 원본 데이터 사용

        year_colors = {2024: "#95a5a6", 2025: "#3498db", 2026: "#e74c3c"}
        year_width  = {2024: 1.5,       2025: 1.5,       2026: 2.5}

        fig2 = go.Figure()

        # 2024/2025 밴드 (고가/저가 범위)
        df_band = df_yr_src[df_yr_src["date"].dt.year.isin([2024, 2025]) & df_yr_src["price"].notna()].copy()
        df_band["mmdd"] = df_band["date"].dt.strftime("%m-%d")
        band = df_band.groupby("mmdd")["price"].agg(["min", "max"]).reset_index()
        band["x"] = pd.to_datetime("2026-" + band["mmdd"], errors="coerce")
        band = band.dropna(subset=["x"]).sort_values("x")

        fig2.add_trace(go.Scatter(
            x=pd.concat([band["x"], band["x"][::-1]]),
            y=pd.concat([band["max"], band["min"][::-1]]),
            fill="toself", fillcolor="rgba(149,165,166,0.15)",
            line=dict(color="rgba(0,0,0,0)"),
            name="2024~2025 범위", hoverinfo="skip",
        ))

        # 연도별 선
        for yr in [2024, 2025, 2026]:
            df_yr = df_yr_src[(df_yr_src["date"].dt.year == yr) & df_yr_src["price"].notna()].copy()
            if df_yr.empty:
                continue
            # x축을 2026년 기준 날짜로 통일
            df_yr["x_date"] = pd.to_datetime(
                "2026-" + df_yr["date"].dt.strftime("%m-%d"), errors="coerce"
            )
            df_yr = df_yr.dropna(subset=["x_date"]).sort_values("x_date")

            if show_ma:
                df_yr["ma3"] = df_yr["price"].rolling(3, min_periods=1).mean()
                fig2.add_trace(go.Scatter(
                    x=df_yr["x_date"], y=df_yr["ma3"],
                    name=f"{yr}년 3일평균",
                    mode="lines",
                    line=dict(color=year_colors[yr], width=year_width[yr], dash="dot"),
                    opacity=0.7,
                    hovertemplate=f"{yr}년 %{{x|%m-%d}}<br>3일평균: <b>%{{y:,.0f}}원/kg</b><extra></extra>",
                ))

            fig2.add_trace(go.Scatter(
                x=df_yr["x_date"], y=df_yr["price"],
                name=f"{yr}년",
                mode="lines+markers",
                line=dict(color=year_colors[yr], width=year_width[yr]),
                marker=dict(size=3 if yr != 2026 else 5),
                hovertemplate=f"{yr}년 %{{x|%m-%d}}<br>경락가: <b>%{{y:,.0f}}원/kg</b><extra></extra>",
            ))

        fig2.update_layout(
            title="연도별 경락가격 비교  (원/kg)",
            height=500, plot_bgcolor="white", paper_bgcolor="#f8f9fa",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            margin=dict(l=10, r=10, t=80, b=10),
            hovermode="x unified",
            xaxis=dict(showgrid=False, tickformat="%m월"),
            yaxis=dict(tickformat=",", showgrid=True, gridcolor="#f0f0f0",
                       range=[y_min, y_max]),
        )
        st.plotly_chart(fig2, use_container_width=True)

    with st.expander("📋 원본 데이터 보기"):
        show_df = df[["date", "price", "count", "market_cnt", "avg3"]].copy()
        show_df.columns = ["날짜", "경락가(원/kg)", "두수", "경매장수", "3일평균"]
        show_df["날짜"] = show_df["날짜"].dt.strftime("%Y-%m-%d")
        show_df = show_df.sort_values("날짜", ascending=False).reset_index(drop=True)
        st.dataframe(show_df, use_container_width=True, height=300)


# ════════════════════════════════════════════════════════════
# TAB 2: 출하물량 분석
# ════════════════════════════════════════════════════════════
with tab2:

    def supply_chart(df_supply: pd.DataFrame, title: str, is_week: bool = False) -> go.Figure:
        if df_supply.empty:
            return None

        year = date.today().year
        df_cur = df_supply[df_supply["year"] == year].copy()
        if df_cur.empty:
            return None

        # hover 기간 라벨 (숫자만)
        unit = "주차" if is_week else "월"
        period_label = [f"{int(p)}{unit}" for p in df_cur["period"]]

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # 막대: 평년 출하물량
        fig.add_trace(go.Bar(
            x=df_cur["period"], y=df_cur["avg_volume"],
            name="평년 출하두수", marker_color="#bdc3c7", opacity=0.8,
            customdata=period_label,
            hovertemplate="평년 %{customdata}: <b>%{y:,.0f}두</b><extra></extra>",
        ), secondary_y=False)

        # 막대: 전년 출하물량
        fig.add_trace(go.Bar(
            x=df_cur["period"], y=df_cur["prev_volume"],
            name=f"{year-1}년 출하두수", marker_color="#85c1e9", opacity=0.8,
            customdata=period_label,
            hovertemplate=f"{year-1}년 %{{customdata}}: <b>%{{y:,.0f}}두</b><extra></extra>",
        ), secondary_y=False)

        # 막대: 올해 출하물량
        v_cur = df_cur["curr_volume"].notna() & (df_cur["curr_volume"] > 10000)
        v_idx = df_cur.index[v_cur] - df_cur.index[0]
        fig.add_trace(go.Bar(
            x=df_cur.loc[v_cur, "period"], y=df_cur.loc[v_cur, "curr_volume"],
            name=f"{year}년 출하두수", marker_color="#2ecc71", opacity=0.9,
            customdata=[period_label[i] for i in v_idx],
            hovertemplate=f"{year}년 %{{customdata}}: <b>%{{y:,.0f}}두</b><extra></extra>",
        ), secondary_y=False)

        # 꺾은선: 올해 경락가격
        p_cur = df_cur["curr_price"].notna()
        p_idx = df_cur.index[p_cur] - df_cur.index[0]
        fig.add_trace(go.Scatter(
            x=df_cur.loc[p_cur, "period"], y=df_cur.loc[p_cur, "curr_price"],
            name=f"{year}년 경락가격", mode="lines+markers",
            line=dict(color="#e74c3c", width=2.5), marker=dict(size=6),
            customdata=[period_label[i] for i in p_idx],
            hovertemplate=f"{year}년 경락가 %{{customdata}}: <b>%{{y:,.0f}}원/kg</b><extra></extra>",
        ), secondary_y=True)

        fig.update_layout(
            title=title, height=480,
            plot_bgcolor="white", paper_bgcolor="#f8f9fa",
            barmode="group",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            margin=dict(l=10, r=10, t=80, b=10),
            hovermode="x unified",
            xaxis=dict(
                showgrid=False,
                tickmode="array",
                tickvals=df_cur["period"].tolist(),
                ticktext=[str(int(p)) for p in df_cur["period"].tolist()],
            ),
        )
        fig.update_yaxes(
            title_text="출하두수 (두)", tickformat=",", secondary_y=False,
            showgrid=True, gridcolor="#f0f0f0"
        )
        fig.update_yaxes(
            title_text="경락가격 (원/kg)", tickformat=",", secondary_y=True,
            showgrid=False
        )
        return fig

    st.subheader("📦 출하물량 & 경락가격 분석")
    st.caption(f"출처: ekapepia.com | 매주 월요일 자동 업데이트")

    df_month = get_supply_month()
    df_week  = get_supply_week()

    if df_month.empty and df_week.empty:
        st.warning("출하물량 데이터가 없습니다. GitHub Actions에서 weekly-supply 워크플로우를 먼저 실행해주세요.")
    else:
        # 월별 차트
        if not df_month.empty:
            fig_m = supply_chart(df_month, "월별 출하두수 & 경락가격", is_week=False)
            if fig_m:
                st.plotly_chart(fig_m, use_container_width=True)

        st.divider()

        # 주별 차트
        if not df_week.empty:
            fig_w = supply_chart(df_week, f"{date.today().year}년 주별 출하두수 & 경락가격", is_week=True)
            if fig_w:
                st.plotly_chart(fig_w, use_container_width=True)

        # 원본 데이터
        with st.expander("📋 출하물량 원본 데이터 보기"):
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**월별**")
                if not df_month.empty:
                    show_m = df_month[df_month["year"] == date.today().year].copy()
                    show_m.columns = ["연도","월","평년가격","전년가격","올해가격","평년물량","전년물량","올해물량"]
                    st.dataframe(show_m.drop(columns=["연도"]), use_container_width=True, hide_index=True)
            with col_b:
                st.markdown("**주별**")
                if not df_week.empty:
                    show_w = df_week[df_week["year"] == date.today().year].copy()
                    show_w.columns = ["연도","주차","평년가격","전년가격","올해가격","평년물량","전년물량","올해물량"]
                    st.dataframe(show_w.drop(columns=["연도"]), use_container_width=True, hide_index=True)
