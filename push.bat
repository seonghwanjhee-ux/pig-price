@echo off
chcp 65001 > nul

echo ===== 돼지 경락가격 자동 업데이트 =====

REM 1. 데이터 수집
cd /d "C:\Users\DW-PC\Desktop\코워크 시각화\ekape-auction"
echo [1/4] 데이터 수집 중...
C:\Users\DW-PC\AppData\Local\Programs\Python\Python314\python.exe pig_dashboard.py

REM 2. CSV 복사
echo [2/4] CSV 복사 중...
copy /Y pig_price_history.csv "C:\Users\DW-PC\Desktop\git_repository\pig price\pig_price_history.csv"

REM 3. GitHub 푸시
cd /d "C:\Users\DW-PC\Desktop\git_repository\pig price"
echo [3/4] Git 커밋 중...
git add pig_price_history.csv
git commit -m "Auto update: %date% %time%"

echo [4/4] GitHub 푸시 중...
git push

echo ===== 완료 =====
