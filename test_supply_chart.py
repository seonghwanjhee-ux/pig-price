"""
출하물량 탭 테스트 이미지 생성
"""
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.font_manager as fm
from bs4 import BeautifulSoup
from io import StringIO

# ── 폰트 ──
def set_font():
    for font in ["Malgun Gothic", "NanumGothic", "AppleGothic", "Gulim"]:
        if font in {f.name for f in fm.fontManager.ttflist}:
            plt.rcParams["font.family"] = font
            break
    plt.rcParams["axes.unicode_minus"] = False

# ── 데이터 수집 ──
def fetch_supply(search_type: str, year: int = 2026) -> pd.DataFrame:
    url = "https://www.ekapepia.com/v3/supplyTrend/statistics/auctionPrice/pigExcel.do"
    params = {
        "searchType": search_type,
        "searchYear": str(year),
        "searchCondition1": "",
        "searchCondition2": "",
        "searchCondition3": "",
        "searchCondition4": "",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.ekapepia.com/",
    }
    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table")
    rows = table.find_all("tr")

    data = []
    for tr in rows:  # 전체 행 순회, 숫자 구분값인 행만 파싱
        cells = [td.get_text(strip=True).replace(",", "") for td in tr.find_all(["td", "th"])]
        if len(cells) >= 7 and cells[0].isdigit():
            def to_num(v):
                try: return float(v)
                except: return None
            data.append({
                "구분":     int(cells[0]),
                "평년_가격": to_num(cells[1]),
                "2025_가격": to_num(cells[2]),
                "2026_가격": to_num(cells[3]),
                "평년_물량": to_num(cells[4]),
                "2025_물량": to_num(cells[5]),
                "2026_물량": to_num(cells[6]),
            })
    return pd.DataFrame(data)

# ── 차트 그리기 ──
def draw_chart(df_month: pd.DataFrame, df_week: pd.DataFrame):
    set_font()
    fig = plt.figure(figsize=(16, 12), facecolor="#f8f9fa")
    fig.suptitle("돼지 출하물량 & 경락가격 분석", fontsize=15, fontweight="bold", y=0.98, color="#2c3e50")
    gs = gridspec.GridSpec(2, 1, figure=fig, hspace=0.45)

    for idx, (df, title, unit) in enumerate([
        (df_month, "월별 출하두수 & 경락가격", "월"),
        (df_week,  "주별 출하두수 & 경락가격", "주차"),
    ]):
        ax1 = fig.add_subplot(gs[idx])
        ax2 = ax1.twinx()
        ax1.set_facecolor("white")

        x = df["구분"]
        w = 0.28

        # 막대: 평년 / 2025 / 2026 출하물량
        valid = df["평년_물량"].notna()
        ax1.bar(x - w, df["평년_물량"], width=w, color="#bdc3c7", label="평년 출하두수", alpha=0.85)
        ax1.bar(x,     df["2025_물량"], width=w, color="#85c1e9", label="2025 출하두수", alpha=0.85)

        v26 = df["2026_물량"].notna()
        ax1.bar(x[v26] + w, df.loc[v26, "2026_물량"], width=w,
                color="#2ecc71", label="2026 출하두수", alpha=0.9)

        # 꺾은선: 2026 경락가격
        p26 = df["2026_가격"].notna()
        ax2.plot(x[p26], df.loc[p26, "2026_가격"],
                 color="#e74c3c", linewidth=2.5, marker="o", markersize=5,
                 label="2026 경락가격", zorder=5)

        # 축 설정
        ax1.set_ylabel("출하두수 (두)", fontsize=9)
        ax2.set_ylabel("경락가격 (원/kg)", fontsize=9)
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))
        ax1.set_xlabel(unit, fontsize=9)
        ax1.set_title(title, fontsize=11, fontweight="bold", pad=8)
        ax1.grid(axis="y", linestyle="--", alpha=0.3)

        # 범례 합치기
        h1, l1 = ax1.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax1.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=8, ncol=2)

    fig.text(0.99, 0.005, "출처: ekapepia.com", ha="right", fontsize=7, color="#aaa")

    out = "supply_test.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="#f8f9fa")
    print(f"[완료] 이미지 저장: {out}")
    plt.show()
    plt.close()


if __name__ == "__main__":
    print("월별 데이터 수집 중...")
    df_month = fetch_supply("month", 2026)
    print(f"  → {len(df_month)}행")

    print("주별 데이터 수집 중...")
    df_week = fetch_supply("week", 2026)
    # 2026 데이터 있는 주차만
    df_week = df_week[df_week["2026_물량"].notna() & (df_week["2026_물량"] > 10000)].reset_index(drop=True)
    print(f"  → {len(df_week)}행")

    draw_chart(df_month, df_week)
