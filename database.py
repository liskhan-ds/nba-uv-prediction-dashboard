"""
================================================================================
[파일명: database.py] - 금고지기 V2.1 (포지션 추가)
================================================================================

[역할]
1. 데이터 저장소(SQLite) 관리:
   - 수집된 선수 데이터와 분석 결과를 'nba_data.db' 파일에 영구 저장합니다.
   
2. 경로 고정 (Path Fixing):
   - 코드를 어디서 실행하든, DB 파일이 항상 파이썬 파일과 같은 폴더에 생성되도록 
     경로를 강제로 고정합니다. (파일 실종 방지)

3. 테이블 스키마 관리:
   - V1.1/V2.0 공식 적용을 위해 'MIN(출전시간)', 'PIE', 'USG%' 등의 
     컬럼을 가진 테이블을 생성합니다.

[주요 함수]
- init_db(): DB 파일과 테이블을 초기화합니다.
- save_daily_stats(df): 데이터프레임을 받아 DB에 저장(Insert/Replace)합니다.
================================================================================
[변경사항]
- 테이블에 'pos' (포지션) 컬럼 추가
================================================================================
[파일명: database.py] - 금고지기 V3.0 (예측 저장소 추가)
================================================================================
[업데이트]
- predictions 테이블 추가: 아침에 AI가 예측한 내용을 저장해두는 공간
================================================================================
"""
import sqlite3
import pandas as pd
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nba_data.db")

def init_db():
    print(f"📁 DB 경로 확인: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. 선수 스탯 테이블 (기존)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS daily_stats (
        date TEXT,
        player_name TEXT,
        availability TEXT,
        pos TEXT,          
        min REAL,          
        pie REAL,
        off_rating REAL,
        def_rating REAL,
        usg_pct REAL,
        ts_pct REAL,
        note TEXT,
        PRIMARY KEY (date, player_name)
    )
    ''')
    
    # 2. [NEW] 승부 예측 저장 테이블
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS predictions (
        game_id TEXT PRIMARY KEY,
        date TEXT,
        home_team TEXT,
        visit_team TEXT,
        predicted_winner TEXT,
        predicted_gap REAL,
        actual_winner TEXT,
        is_correct INTEGER
    )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ DB 테이블 준비 완료 (Schema: Stats + Predictions).")

def save_daily_stats(df):
    if df.empty: return
    conn = sqlite3.connect(DB_PATH)
    today = datetime.now().strftime("%Y-%m-%d")
    cursor = conn.cursor()
    
    for _, row in df.iterrows():
        try:
            cursor.execute('''
            INSERT OR REPLACE INTO daily_stats 
            (date, player_name, availability, pos, min, pie, off_rating, def_rating, usg_pct, ts_pct, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (today, row['PLAYER_NAME'], row['AVAILABILITY'], row['POS'], row['MIN'], 
                  row['PIE'], row['OFF_RATING'], row['DEF_RATING'], row['USG_PCT'], row['TS_PCT'], row['NOTE']))
        except: pass
    conn.commit()
    conn.close()

def save_prediction_to_db(game_id, date, home, visit, pred_winner, gap):
    """ [NEW] 아침의 예측 결과를 DB에 저장 """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
        INSERT OR REPLACE INTO predictions 
        (game_id, date, home_team, visit_team, predicted_winner, predicted_gap, actual_winner, is_correct)
        VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
        ''', (game_id, date, home, visit, pred_winner, gap))
        conn.commit()
    except Exception as e:
        print(f"⚠️ 예측 저장 실패: {e}")
    finally:
        conn.close()