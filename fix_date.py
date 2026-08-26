"""
================================================================================
[파일명: fix_date.py] - rowid(숨겨진 ID)를 사용하여 날짜 보정하기
================================================================================
"""
import sqlite3
from datetime import datetime, timedelta

DB_PATH = "nba_data.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("🔄 DB 날짜 변환 시작 (KST -> US Date)...")
    
    # [수정] id 컬럼이 없으므로, SQLite 내부의 숨겨진 'rowid'를 사용합니다.
    cursor.execute("SELECT rowid, date FROM predictions")
    rows = cursor.fetchall()
    
    count = 0
    for row in rows:
        r_id = row[0] # rowid (숨겨진 고유번호)
        old_date_str = row[1]
        
        try:
            # 날짜 포맷 파싱 후 하루 빼기 (-1일)
            old_date = datetime.strptime(old_date_str, "%Y-%m-%d")
            new_date = old_date - timedelta(days=1)
            new_date_str = new_date.strftime("%Y-%m-%d")
            
            # 업데이트 (WHERE 조건에 rowid 사용)
            cursor.execute("UPDATE predictions SET date = ? WHERE rowid = ?", (new_date_str, r_id))
            count += 1
        except Exception as e:
            print(f"⚠️ 날짜 파싱 오류 (Skip): {old_date_str}")
        
    conn.commit()
    conn.close()
    print(f"✅ 총 {count}개 데이터의 날짜를 하루 전(미국 기준)으로 변경했습니다.")

if __name__ == "__main__":
    main()