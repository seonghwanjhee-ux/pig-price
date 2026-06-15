"""
돼지 출하물량 & 경락가격 수집
- 출처: ekapepia.com
- 월별 / 주별 데이터 수집
- 매주 월요일 자동 실행
"""

import requests
import pandas as pd
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import date

SCRAPE_URL = "https://www.ekapepia.com/v3/supplyTrend/statistics/auctionPrice/pigExcel.do"
CSV_MONTH  = Path(__file__).parent / "pig_supply_month.csv"
CSV_WEEK   = Path(__file__).parent / "pig_supply_week.csv"

# searchCondition1: 시장 구분 — '057016' = 전국(제주제외)
# (제주산 돼지는 고가라 경락가격 산정에서 제외. '' 으로 두면 제주 포함되어 가격이 왜곡됨)
REGION_EXCL_JEJU = "057016"


def fetch_supply(search_type: str, year: int) -> pd.DataFrame:
    params = {
        "searchType"      : search_type,
        "searchYear"      : str(year),
        "searchCondition1": REGION_EXCL_JEJU,   # 전국(제주제외)
        "searchCondition2": "",
        "searchCondition3": "",
        "searchCondition4": "",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer"   : "https://www.ekapepia.com/",
    }
    r = requests.get(SCRAPE_URL, params=params, headers=headers, timeout=15)
    r.raise_for_status()

    soup  = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table")
    if not table:
        return pd.DataFrame()

    rows = table.find_all("tr")
    data = []
    for tr in rows:
        cells = [td.get_text(strip=True).replace(",", "") for td in tr.find_all(["td", "th"])]
        if len(cells) >= 7 and cells[0].isdigit():
            def to_num(v):
                try: return float(v)
                except: return None
            data.append({
                "year"        : year,
                "period"      : int(cells[0]),
                "avg_price"   : to_num(cells[1]),
                "prev_price"  : to_num(cells[2]),
                "curr_price"  : to_num(cells[3]),
                "avg_volume"  : to_num(cells[4]),
                "prev_volume" : to_num(cells[5]),
                "curr_volume" : to_num(cells[6]),
            })
    return pd.DataFrame(data)


def load_csv(path: Path) -> pd.DataFrame:
    if path.exists():
        try:
            return pd.read_csv(path, encoding="utf-8-sig")
        except Exception:
            pass
    return pd.DataFrame()


def save_csv(df: pd.DataFrame, path: Path):
    df.to_csv(path, index=False, encoding="utf-8-sig")


def update_supply(search_type: str, csv_path: Path):
    year = date.today().year
    print(f"  [{search_type}] {year}년 수집 중...")
    df_new = fetch_supply(search_type, year)
    if df_new.empty:
        print(f"  [{search_type}] 데이터 없음")
        return

    # 기존 데이터 로드 후 현재 연도 갱신
    df_old = load_csv(csv_path)
    if not df_old.empty:
        df_old = df_old[df_old["year"] != year]
        df_combined = pd.concat([df_old, df_new], ignore_index=True).sort_values(["year", "period"])
    else:
        df_combined = df_new

    save_csv(df_combined, csv_path)
    print(f"  [{search_type}] 저장 완료 → {len(df_combined)}행")


if __name__ == "__main__":
    print("=" * 50)
    print(" 돼지 출하물량 수집")
    print("=" * 50)
    update_supply("month", CSV_MONTH)
    update_supply("week",  CSV_WEEK)
    print("\n[완료]")
