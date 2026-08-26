"""
================================================================================
[파일명: nbaapi.py] - 수집가 V2.1 (포지션 크롤링 탑재)
================================================================================

[역할]
1. 데이터 수집 (Data Collection):
   - NBA 공식 API에서 시즌 평균 스탯(PerGame)을 가져옵니다.
   - ESPN 웹사이트에서 실시간 부상자 명단(Out/Day-To-Day)을 크롤링합니다.

2. 데이터 정제 (Data Cleaning):
   - 'Austin Reaves'와 'Austin Reaves ' 같은 미세한 이름 차이를 
     Fuzzy Matching 기술로 연결합니다.
   - 부상자 상태(Out)를 식별하여 데이터에 라벨링합니다.

3. 저장 명령:
   - 수집이 끝나면 database.py를 호출하여 DB에 저장을 요청합니다.

[실행 방법]
- 터미널에서 실행하면 데이터 수집 -> 정제 -> DB 저장까지 한 번에 수행됩니다.
================================================================================

[변경사항]
- get_team_roster_positions(): 선수들의 포지션(G, F, C) 정보를 가져오는 함수 추가
- 수집된 스탯 데이터에 포지션 정보를 병합(Merge)
================================================================================
"""
import pandas as pd
import requests
from bs4 import BeautifulSoup
from nba_api.stats.endpoints import leaguedashplayerstats, commonteamroster
from thefuzz import fuzz
from database import init_db, save_daily_stats

TEAM_ID = '1610612747'  # LA Lakers
SEASON = '2025-26'
ESPN_INJURY_URL = "https://www.espn.com/nba/team/injuries/_/name/lal/los-angeles-lakers"

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

def get_team_roster_positions():
    """ [NEW] 팀 로스터에서 포지션 정보 가져오기 """
    print("🔄 선수 포지션 정보 조회 중...")
    try:
        roster = commonteamroster.CommonTeamRoster(season=SEASON, team_id=TEAM_ID)
        df = roster.get_data_frames()[0]
        # 필요한 컬럼만 추출 (이름, 포지션)
        # NBA API는 보통 'G', 'F', 'C', 'G-F' 등으로 줌
        return df[['PLAYER', 'POSITION']].rename(columns={'PLAYER': 'PLAYER_NAME', 'POSITION': 'POS'})
    except Exception as e:
        print(f"⚠️ 포지션 조회 실패: {e}")
        return pd.DataFrame()

def get_advanced_stats():
    print(f"🔄 NBA 서버에서 {SEASON} 시즌 스탯 조회 중 (PerGame)...")
    try:
        stats = leaguedashplayerstats.LeagueDashPlayerStats(
            season=SEASON,
            measure_type_detailed_defense='Advanced',
            team_id_nullable=TEAM_ID,
            per_mode_detailed='PerGame' 
        )
        df = stats.get_data_frames()[0]
        active_df = df[ (df['GP'] >= 1) & (df['MIN'] >= 10) ].copy()
        cols = ['PLAYER_NAME', 'GP', 'MIN', 'PIE', 'OFF_RATING', 'DEF_RATING', 'USG_PCT', 'TS_PCT']
        return active_df[cols]
    except Exception as e:
        print(f"❌ 스탯 조회 실패: {e}")
        return pd.DataFrame()

def get_espn_injury_report():
    print("🔄 ESPN 부상자 크롤링 중...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(ESPN_INJURY_URL, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        injured_list = []
        # ESPN 구조 변경 대응 (div or span)
        name_tags = soup.find_all('span', class_='Athlete__PlayerName')
        
        for tag in name_tags:
            name = tag.text.strip()
            parent_text = tag.parent.parent.get_text(" ", strip=True).lower()
            
            status = "Unknown"
            if "out" in parent_text: status = "Out"
            elif "day-to-day" in parent_text: status = "Day-To-Day"
            elif "questionable" in parent_text: status = "Questionable"
            
            injured_list.append({'PLAYER': name, 'STATUS': status, 'NOTE': parent_text})

        return pd.DataFrame(injured_list)

    except Exception as e:
        print(f"❌ ESPN 크롤링 실패: {e}")
        return pd.DataFrame()

def main():
    print("=== [Unit Value V2.1] Data Collector ===\n")

    init_db()

    # 1. 스탯 수집
    stats_df = get_advanced_stats()
    if stats_df.empty: return

    # 2. [NEW] 포지션 정보 수집 및 병합
    pos_df = get_team_roster_positions()
    if not pos_df.empty:
        # 이름 기준으로 병합 (Left Join)
        stats_df = pd.merge(stats_df, pos_df, on='PLAYER_NAME', how='left')
        stats_df['POS'] = stats_df['POS'].fillna('F') # 포지션 누락시 기본값 F
    else:
        stats_df['POS'] = 'F'

    # 3. 부상자 매칭
    injury_df = get_espn_injury_report()
    stats_df['AVAILABILITY'] = 'OK'
    stats_df['NOTE'] = '-'

    if not injury_df.empty:
        for idx, row in stats_df.iterrows():
            nba_name = row['PLAYER_NAME']
            for _, inj_row in injury_df.iterrows():
                espn_name = inj_row['PLAYER']
                if fuzz.partial_ratio(nba_name.lower(), espn_name.lower()) >= 80:
                    stats_df.at[idx, 'AVAILABILITY'] = inj_row['STATUS']
                    stats_df.at[idx, 'NOTE'] = inj_row['NOTE'][:50] + "..."

    # 4. 저장
    stats_df = stats_df.sort_values(by='PIE', ascending=False)
    print(f"\n✅ [최종 수집 데이터] 총 {len(stats_df)}명")
    print(stats_df[['PLAYER_NAME', 'POS', 'AVAILABILITY', 'MIN', 'PIE']])
    
    print("-" * 60)
    save_daily_stats(stats_df)
    print("-" * 60)

if __name__ == "__main__":
    main()