"""
돼지 가축시장 경락가격 대시보드
- 출처: ekapepia.com (가축시장 · 등외제외 · 전국 제주제외)
- 비제주 개별 경매장 5개 미만 → 경락가 없음
- 전일 단가 + 직전 3거래일 산술평균 시각화
- 매일 9시 자동 실행
"""

import requests
import re
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.gridspec as gridspec
from bs4 import BeautifulSoup
from typing import Optional, List, Tuple
from datetime import date, timedelta
from pathlib import Path
import sys

# ── 설정 ──────────────────────────────────────────────────────────────────────
SCRAPE_URL  = "https://www.ekapepia.com/v3/price/auction/period/pig/auctionPrice.do"
CSV_PATH    = Path(__file__).parent / "pig_price_history.csv"
CHART_OUT   = Path(__file__).parent / "pig_dashboard.png"
CHART_DAYS  = 60
MIN_MARKETS = 5   # 유효 경락가 인정 최소 개별 경매장 수


# ── 유틸 ──────────────────────────────────────────────────────────────────────
def prev_business_day(d: date = None) -> date:
    d = (d or date.today()) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d

def business_days_range(start: date, end: date) -> List[date]:
    days, d = [], start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days

def set_font():
    for font in ["Malgun Gothic", "NanumGothic", "AppleGothic", "Gulim"]:
        if font in {f.name for f in fm.fontManager.ttflist}:
            plt.rcParams["font.family"] = font
            break
    plt.rcParams["axes.unicode_minus"] = False

def fmt(n) -> str:
    return format(int(n), ",") if n is not None else "-"

def parse_price_cell(val: str) -> Tuple[Optional[float], Optional[int]]:
    """'5,838(160)' → (5838.0, 160)"""
    m = re.match(r'([\d,]+)\((\d[\d,]*)\)', val.strip())
    if m:
        return float(m.group(1).replace(',', '')), int(m.group(2).replace(',', ''))
    return None, None


# ── 1. ekapepia.com 스크래핑 ─────────────────────────────────────────────────
def scrape_pig_price(target_date: date) -> Optional[dict]:
    """
    ekapepia.com에서 가축시장 돼지 경락가격 스크래핑.
    - 전국(가축시장 제주제외) 등외제외 기준
    - 개별 경매장 MIN_MARKETS 미만 → price=None (경락가 없음)
    """
    date_str = target_date.strftime("%Y-%m-%d")
    ymd      = target_date.strftime("%Y%m%d")

    try:
        s = requests.Session()
        s.headers.update({
            "User-Agent"     : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer"        : SCRAPE_URL,
        })
        r = s.get(SCRAPE_URL, params={
            "searchStartDate" : date_str,
            "searchEndDate"   : date_str,
            "searchCondition" : "2",
            "searchCondition1": "",
            "searchCondition2": "1",
        }, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print("  [ERR] 요청 실패: %s" % e)
        return None

    soup  = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table")
    if not table:
        return None

    rows = table.find_all("tr")
    if len(rows) < 3:
        return None

    # 헤더 행(row1)에서 개별 경매장 컬럼 위치 파악 (colspan 처리)
    # row0 = 지역 대분류 (colspan), row1 = 개별 경매장명
    header_cells = rows[1].find_all(["td", "th"])
    # colspan을 펼쳐서 실제 컬럼 인덱스 매핑
    col_names = []
    for cell in header_cells:
        span = int(cell.get("colspan", 1))
        name = cell.get_text(strip=True)
        col_names.extend([name] * span)

    # row0에서 "합계" / "소계" 컬럼 위치 찾기
    row0_cells = rows[0].find_all(["td", "th"])
    row0_expanded = []
    for cell in row0_cells:
        span = int(cell.get("colspan", 1))
        name = cell.get_text(strip=True)
        row0_expanded.extend([name] * span)

    # 등외제외 행 파싱
    for tr in rows:
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if not cells or "등외제외" not in cells[0]:
            continue

        # col[1] = 전국(가축시장 제주제외) 합계
        nat_price, nat_cnt = parse_price_cell(cells[1]) if len(cells) > 1 else (None, None)
        if nat_cnt is None:
            return {"date": ymd, "price": None, "count": 0, "market_cnt": 0}

        # 개별 가축시장 컬럼 수
        # cols[2]~cols[-2] (도매시장 및 전체합계 제외) 에서 소계 자동 감지 후 제거
        # 소계 판별: count == sum(다른 임의의 두 개 cell count)
        mid_cells = cells[2:-2]   # 도매시장(col17), 합계(col18) 제외
        parsed = []
        for v in mid_cells:
            p, c = parse_price_cell(v)
            if p is not None and c is not None:
                parsed.append(c)

        # 중복 제거 후 소계 판별
        unique_counts = list(dict.fromkeys(parsed))   # 중복 제거 (순서 유지)
        subtotals = set()
        for i in range(len(unique_counts)):
            for j in range(len(unique_counts)):
                if i != j:
                    for k in range(j + 1, len(unique_counts)):
                        if i != k and unique_counts[i] == unique_counts[j] + unique_counts[k]:
                            subtotals.add(unique_counts[i])
        active_mkts = sum(1 for c in unique_counts if c not in subtotals)

        price = nat_price if active_mkts >= MIN_MARKETS else None

        return {
            "date"      : ymd,
            "price"     : price,
            "count"     : int(nat_cnt),
            "market_cnt": active_mkts,
        }

    return None


# ── 2. 공휴일 소급 탐색 ───────────────────────────────────────────────────────
def find_latest_data_day(max_lookback: int = 10) -> Tuple[Optional[date], Optional[dict]]:
    d = date.today()
    tried = 0
    while tried < max_lookback:
        d -= timedelta(days=1)
        if d.weekday() >= 5:
            continue
        row = scrape_pig_price(d)
        if row and row["count"] > 0:
            return d, row
        tried += 1
        print("  %s 데이터 없음 (공휴일/휴장) → 이전 날짜 재시도..." % d.strftime("%Y%m%d"))
    return None, None


# ── 3. CSV 누적 저장 ──────────────────────────────────────────────────────────
def load_history() -> pd.DataFrame:
    if CSV_PATH.exists():
        df = pd.read_csv(CSV_PATH, dtype={"date": str}, encoding="utf-8-sig")
        df["date"]  = pd.to_datetime(df["date"], format="%Y%m%d")
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        return df
    return pd.DataFrame(columns=["date", "price", "count", "market_cnt"])

def save_history(df: pd.DataFrame):
    out = df.copy()
    out["date"] = out["date"].dt.strftime("%Y%m%d")
    out.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")

def update_history(df: pd.DataFrame, new_rows: List[dict]) -> Tuple[pd.DataFrame, int]:
    if not new_rows:
        return df, 0
    new_df = pd.DataFrame(new_rows)
    new_df["date"] = pd.to_datetime(new_df["date"], format="%Y%m%d")
    existing = set(df["date"].dt.strftime("%Y%m%d")) if len(df) else set()
    added = new_df[~new_df["date"].dt.strftime("%Y%m%d").isin(existing)]
    if added.empty:
        return df, 0
    combined = pd.concat([df, added], ignore_index=True).sort_values("date").reset_index(drop=True)
    return combined, len(added)


# ── 4. 직전 3거래일 산술평균 ──────────────────────────────────────────────────
def calc_3day_avg(df: pd.DataFrame) -> pd.Series:
    prices = df["price"].tolist()
    avgs   = []
    for i in range(len(prices)):
        valid = [p for p in prices[:i] if pd.notna(p)]
        if len(valid) >= 3:
            avgs.append(round(sum(valid[-3:]) / 3, 1))
        elif len(valid) > 0:
            avgs.append(round(sum(valid) / len(valid), 1))
        else:
            avgs.append(None)
    return pd.Series(avgs, index=df.index)


# ── 5. 대시보드 시각화 ────────────────────────────────────────────────────────
def draw_dashboard(df: pd.DataFrame):
    set_font()
    df = df.sort_values("date").tail(CHART_DAYS).copy().reset_index(drop=True)
    df["avg3"] = calc_3day_avg(df)

    valid_df   = df[df["price"].notna()]
    latest     = valid_df.iloc[-1] if len(valid_df) else df.iloc[-1]
    prev_valid = valid_df.iloc[-2] if len(valid_df) >= 2 else None

    l_price = latest["price"] if pd.notna(latest["price"]) else None
    # KPI용 직전 3거래일 평균: 최근 거래일 포함 3개의 산술평균
    last3 = valid_df["price"].tail(3).tolist()
    l_avg3 = round(sum(last3) / len(last3), 1) if len(last3) >= 1 else None
    # 직전 3거래일 평균 등락: 현재 3거래일 평균 vs 그 이전 3거래일 평균
    prev3 = valid_df["price"].iloc[-6:-3].tolist()
    if l_avg3 and len(prev3) >= 1:
        prev_avg3 = round(sum(prev3) / len(prev3), 1)
        avg3_dv = l_avg3 - prev_avg3
        avg3_ds = "%+.0f원 (%+.1f%%)" % (avg3_dv, avg3_dv / prev_avg3 * 100)
        avg3_dc = "#e74c3c" if avg3_dv >= 0 else "#2980b9"
    else:
        avg3_ds, avg3_dc = None, "#7f8c8d"
    l_cnt   = int(latest["count"])
    l_mkt   = int(latest.get("market_cnt", 0))
    l_date  = latest["date"].strftime("%Y-%m-%d")
    l_dow   = latest["date"].strftime("%A").replace(
        "Monday","월").replace("Tuesday","화").replace("Wednesday","수").replace(
        "Thursday","목").replace("Friday","금")

    if l_price and prev_valid is not None and pd.notna(prev_valid["price"]):
        dv = l_price - prev_valid["price"]
        ds = "%+.0f원 (%+.1f%%)" % (dv, dv / prev_valid["price"] * 100)
        dc = "#e74c3c" if dv >= 0 else "#2980b9"
    else:
        ds, dc = "-", "#7f8c8d"

    fig = plt.figure(figsize=(16, 10), facecolor="#f8f9fa")
    gs  = gridspec.GridSpec(3, 3, figure=fig,
                            height_ratios=[0.8, 2.8, 2.2],
                            hspace=0.5, wspace=0.35)

    # ── KPI 카드 4개 ──────────────────────────────────────────────────────────
    kpi_gs = gridspec.GridSpecFromSubplotSpec(1, 4, subplot_spec=gs[0, :], wspace=0.3)
    # (label, value, color, sub_value, sub_color)  — sub_* 는 선택
    kpis = [
        ("전일 경락가격\n(가축시장·등외제외·전국제주제외)\n%s (%s)" % (l_date, l_dow),
         "%s원/kg" % fmt(l_price) if l_price else "경락가 없음",
         "#e74c3c" if not l_price else "#2c3e50", None, None),
        ("직전 3거래일\n산술평균",
         "%s원/kg" % fmt(l_avg3) if l_avg3 else "-",
         "#8e44ad", avg3_ds, avg3_dc),
        ("직전 거래일 대비\n등락",
         ds, dc, None, None),
        ("경매 두수 / 경매장\n%s (%s)" % (l_date, l_dow),
         "%s두 / %d개" % (fmt(l_cnt), l_mkt),
         "#27ae60" if l_mkt >= MIN_MARKETS else "#e67e22", None, None),
    ]
    for i, (label, value, color, sub_value, sub_color) in enumerate(kpis):
        ax = fig.add_subplot(kpi_gs[i])
        ax.set_facecolor("white"); ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")
        ax.text(0.5, 0.78, label, ha="center", va="center", fontsize=8,
                color="#7f8c8d", transform=ax.transAxes, linespacing=1.5)
        v_y = 0.35 if sub_value else 0.28
        ax.text(0.5, v_y, value, ha="center", va="center", fontsize=13,
                fontweight="bold", color=color, transform=ax.transAxes)
        if sub_value:
            ax.text(0.5, 0.12, sub_value, ha="center", va="center", fontsize=9,
                    color=sub_color, transform=ax.transAxes)
        for spine in ax.spines.values():
            spine.set_visible(True); spine.set_color("#dee2e6")

    # ── 경락가격 + 3거래일 평균 추이 ─────────────────────────────────────────
    ax1 = fig.add_subplot(gs[1, :])
    ax1.set_facecolor("white")
    valid_mask = df["price"].notna()

    ax1.plot(df.loc[valid_mask, "date"], df.loc[valid_mask, "price"],
             color="#3498db", linewidth=2, marker="o", markersize=4,
             label="전일 경락가격", zorder=3)
    if valid_mask.any():
        ax1.fill_between(df.loc[valid_mask, "date"],
                         df.loc[valid_mask, "price"], alpha=0.08, color="#3498db")

    avg_mask = df["avg3"].notna()
    ax1.plot(df.loc[avg_mask, "date"], df.loc[avg_mask, "avg3"],
             color="#e74c3c", linewidth=2, linestyle="--", marker="s", markersize=3,
             label="직전 3거래일 평균", zorder=3)

    # 경락가 없는 날 수직선
    no_price = df[~valid_mask & (df["count"] > 0)]
    y_min = 3500
    for _, nr in no_price.iterrows():
        ax1.axvline(nr["date"], color="#e67e22", linewidth=1, linestyle=":", alpha=0.7)
        ax1.text(nr["date"], y_min, "없음", rotation=90,
                 ha="center", va="bottom", fontsize=6, color="#e67e22")

    if valid_mask.any():
        idx_max = df.loc[valid_mask, "price"].idxmax()
        idx_min = df.loc[valid_mask, "price"].idxmin()
        ax1.annotate("%s원" % fmt(df.loc[idx_max, "price"]),
                     xy=(df.loc[idx_max, "date"], df.loc[idx_max, "price"]),
                     xytext=(0, 9), textcoords="offset points",
                     ha="center", fontsize=8, color="#c0392b", fontweight="bold")
        ax1.annotate("%s원" % fmt(df.loc[idx_min, "price"]),
                     xy=(df.loc[idx_min, "date"], df.loc[idx_min, "price"]),
                     xytext=(0, -14), textcoords="offset points",
                     ha="center", fontsize=8, color="#2980b9", fontweight="bold")

    ax1.set_title("돼지 가축시장 경락가격 추이  (등외제외 · 전국 제주제외)  단위: 원/kg",
                  fontsize=11, fontweight="bold", pad=8)
    ax1.set_ylabel("원/kg")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: fmt(x)))
    ax1.tick_params(axis="x", rotation=30, labelsize=8)
    ax1.legend(loc="upper left", fontsize=9)
    ax1.set_ylim(3500, 7500)
    ax1.grid(axis="y", linestyle="--", alpha=0.4)

    # ── 경매 두수 ─────────────────────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[2, :2])
    ax2.set_facecolor("white")
    mean_cnt = df.loc[valid_mask, "count"].mean() if valid_mask.any() else 0
    bar_colors = []
    for _, row in df.iterrows():
        if not pd.notna(row.get("price")):
            bar_colors.append("#f0b27a")
        elif row["count"] >= mean_cnt:
            bar_colors.append("#2ecc71")
        else:
            bar_colors.append("#95a5a6")
    ax2.bar(df["date"], df["count"], color=bar_colors, width=0.7, edgecolor="none")
    ax2.axhline(mean_cnt, color="#e74c3c", linestyle="--", linewidth=1,
                label="유효일 평균 %s두" % fmt(mean_cnt))
    ax2.set_title("일별 경매 두수  (초록: 평균이상 / 주황: 경락가없음)", fontsize=10, fontweight="bold")
    ax2.set_ylabel("두수"); ax2.legend(fontsize=8)
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: fmt(x)))
    ax2.tick_params(axis="x", rotation=30, labelsize=8)
    ax2.grid(axis="y", linestyle="--", alpha=0.4)

    # ── 경매장 수 추이 ────────────────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[2, 2])
    ax3.set_facecolor("white")
    if "market_cnt" in df.columns:
        mc = pd.to_numeric(df["market_cnt"], errors="coerce").fillna(0)
        mkt_colors = ["#27ae60" if v >= MIN_MARKETS else "#e74c3c" for v in mc]
        ax3.bar(df["date"], mc, color=mkt_colors, width=0.7, edgecolor="none")
        ax3.axhline(MIN_MARKETS, color="#e67e22", linestyle="--", linewidth=1.5,
                    label="기준 %d개" % MIN_MARKETS)
        ax3.set_title("일별 활성 경매장 수\n(빨강: %d개 미만 → 경락가없음)" % MIN_MARKETS,
                      fontsize=9, fontweight="bold")
        ax3.set_ylabel("경매장 수"); ax3.legend(fontsize=8)
        ax3.tick_params(axis="x", rotation=30, labelsize=8)
        ax3.grid(axis="y", linestyle="--", alpha=0.4)

    fig.suptitle("돼지 가축시장 경락가격 대시보드",
                 fontsize=15, fontweight="bold", y=0.99, color="#2c3e50")
    fig.text(0.99, 0.005,
             "기준: %s  |  출처: ekapepia.com  |  등외제외·가축시장·비제주 %d개 이상" % (
                 l_date, MIN_MARKETS),
             ha="right", fontsize=7, color="#aaa")

    fig.savefig(CHART_OUT, dpi=150, bbox_inches="tight", facecolor="#f8f9fa")
    print("[OK] 대시보드 저장: %s" % CHART_OUT)
    plt.show()
    plt.close()


# ── 6. 메인 실행 ──────────────────────────────────────────────────────────────
def run(fetch_days: int = 1):
    print("=" * 55)
    print(" 돼지 가축시장 경락가격 대시보드")
    print(" 출처: ekapepia.com")
    print("=" * 55)

    new_rows = []

    if fetch_days == 1:
        print("[1/3] 최근 데이터 탐색 중...")
        _, row = find_latest_data_day()
        if row:
            label = "경락가 없음 (%d개)" % row["market_cnt"] if row["price"] is None \
                    else "%s원" % fmt(row["price"])
            print("  %s  %s  두수=%s두  경매장=%d개" % (
                row["date"], label, fmt(row["count"]), row["market_cnt"]))
            new_rows.append(row)
        else:
            print("  최근 10 영업일 내 데이터 없음.")
    else:
        end   = prev_business_day()
        start = prev_business_day(date.today() - timedelta(days=fetch_days * 2))
        target_dates = business_days_range(start, end)[-fetch_days:]

        print("[1/3] 수집: %s ~ %s (%d일)" % (
            target_dates[0].strftime("%Y%m%d"),
            target_dates[-1].strftime("%Y%m%d"),
            len(target_dates)))

        for d in target_dates:
            row = scrape_pig_price(d)
            if row and row["count"] > 0:
                label = "경락가 없음 (%d개)" % row["market_cnt"] if row["price"] is None \
                        else "%s원" % fmt(row["price"])
                print("  %s  %s  두수=%s두  경매장=%d개" % (
                    row["date"], label, fmt(row["count"]), row["market_cnt"]))
                new_rows.append(row)
            else:
                print("  %s  데이터 없음 (공휴일/휴장)" % d.strftime("%Y%m%d"))

    print("[2/3] CSV 저장 중...")
    df = load_history()
    df, added = update_history(df, new_rows)
    save_history(df)
    print("  누적: 총 %d일  신규 %d건" % (len(df), added))

    if len(df) >= 2:
        print("[3/3] 대시보드 생성 중...")
        draw_dashboard(df)
    else:
        print("[3/3] 데이터 부족. --init 으로 초기 수집 먼저 실행하세요.")

    print("\n[완료]")


if __name__ == "__main__":
    if "--init" in sys.argv:
        run(fetch_days=90)
    else:
        run(fetch_days=1)
