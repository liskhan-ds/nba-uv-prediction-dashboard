"""
================================================================================
[파일명: predictor.py] - 승부 예언가 V2.5 (KST Localization)
================================================================================
[업데이트 내역]
1. Fuzzy Matching 도입: 'Jokic' vs 'Jokić' 같은 특수문자 불일치 문제 해결
2. 홈/원정(Home/Away) 어드밴티지 로직 유지
3. 상세 스코어링 리포트 및 검증 기능 유지
================================================================================
[업데이트]
1. '농구 도사' 라인업 로직 적용:
   - 단순 Top 5가 아니라, 포지션(G, F, C) 밸런스를 고려하여 주전 5명을 선발합니다.
   - 예: 에이튼(C)이 뽑히면 헤이즈(C)는 벤치로 이동.
2. 상대 팀 데이터 수집 시 포지션 정보도 함께 수집하도록 개선.
================================================================================
[업데이트]
1. 경기 일정 자동 감지 (Auto-Schedule):
   - NBA API(Scoreboard)를 통해 오늘 레이커스 경기가 있는지 확인합니다.
   - 경기가 있다면 '홈/원정 여부'와 '상대 팀'을 자동으로 설정합니다.
   - 경기가 없는 날에만 수동 입력 모드로 전환됩니다.
2. 기존 로직(포지션 라인업, Fuzzy Matching) 모두 유지.
================================================================================
[업데이트 내역]
1. 시차 보정 (Timezone Fix):
   - 한국 시간(KST) 기준으로 실행해도, 미국 현지(ET) 경기 날짜를 자동으로 계산합니다.
   - 공식: 현재시간 - 14시간 = NBA Game Date
2. 기존 기능 통합 유지:
   - 포지션 기반 라인업 (G-G-F-F-C)
   - Fuzzy Matching (Jokic 특수문자 처리)
   - 홈/원정 자동 감지
================================================================================
"""
import pandas as pd
import requests
import sqlite3
import os
from bs4 import BeautifulSoup
from nba_api.stats.endpoints import leaguedashplayerstats, commonteamroster, scoreboardv2
from datetime import datetime, timedelta # [NEW] 시간 계산용 모듈
from thefuzz import fuzz

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nba_data.db")
SEASON = '2025-26'
LAKERS_ID = '1610612747'

TEAMS = {
    'ATL': {'id': '1610612737', 'slug': 'atl/atlanta-hawks'},
    'BOS': {'id': '1610612738', 'slug': 'bos/boston-celtics'},
    'BKN': {'id': '1610612751', 'slug': 'bkn/brooklyn-nets'},
    'CHA': {'id': '1610612766', 'slug': 'cha/charlotte-hornets'},
    'CHI': {'id': '1610612741', 'slug': 'chi/chicago-bulls'},
    'CLE': {'id': '1610612739', 'slug': 'cle/cleveland-cavaliers'},
    'DAL': {'id': '1610612742', 'slug': 'dal/dallas-mavericks'},
    'DEN': {'id': '1610612743', 'slug': 'den/denver-nuggets'},
    'DET': {'id': '1610612765', 'slug': 'det/detroit-pistons'},
    'GSW': {'id': '1610612744', 'slug': 'gs/golden-state-warriors'},
    'HOU': {'id': '1610612745', 'slug': 'hou/houston-rockets'},
    'IND': {'id': '1610612754', 'slug': 'ind/indiana-pacers'},
    'LAC': {'id': '1610612746', 'slug': 'lac/los-angeles-clippers'},
    'LAL': {'id': '1610612747', 'slug': 'lal/los-angeles-lakers'},
    'MEM': {'id': '1610612763', 'slug': 'mem/memphis-grizzlies'},
    'MIA': {'id': '1610612748', 'slug': 'mia/miami-heat'},
    'MIL': {'id': '1610612749', 'slug': 'mil/milwaukee-bucks'},
    'MIN': {'id': '1610612750', 'slug': 'min/minnesota-timberwolves'},
    'NOP': {'id': '1610612740', 'slug': 'no/new-orleans-pelicans'},
    'NYK': {'id': '1610612752', 'slug': 'ny/new-york-knicks'},
    'OKC': {'id': '1610612760', 'slug': 'okc/oklahoma-city-thunder'},
    'ORL': {'id': '1610612753', 'slug': 'orl/orlando-magic'},
    'PHI': {'id': '1610612755', 'slug': 'phi/philadelphia-76ers'},
    'PHX': {'id': '1610612756', 'slug': 'phx/phoenix-suns'},
    'POR': {'id': '1610612757', 'slug': 'por/portland-trail-blazers'},
    'SAC': {'id': '1610612758', 'slug': 'sac/sacramento-kings'},
    'SAS': {'id': '1610612759', 'slug': 'sa/san-antonio-spurs'},
    'TOR': {'id': '1610612761', 'slug': 'tor/toronto-raptors'},
    'UTA': {'id': '1610612762', 'slug': 'utah/utah-jazz'},
    'WAS': {'id': '1610612764', 'slug': 'wsh/washington-wizards'},
}

ID_TO_ABBR = {v['id']: k for k, v in TEAMS.items()}

def calculate_individual_uv(pie):
    uv = 1.0 + (pie - 0.10) * 20
    return max(0.1, min(uv, 3.5))

def select_best_lineup(roster):
    sorted_players = roster.sort_values(by='contribution', ascending=False)
    starters = []
    bench = []
    
    guards = sorted_players[sorted_players['pos'].str.contains('G', na=False)]
    forwards = sorted_players[sorted_players['pos'].str.contains('F', na=False)]
    centers = sorted_players[sorted_players['pos'].str.contains('C', na=False)]
    
    selected_indices = set()
    
    def pick_player(pool, count):
        picked = 0
        for idx, row in pool.iterrows():
            if picked >= count: break
            if idx not in selected_indices:
                starters.append(row)
                selected_indices.add(idx)
                picked += 1
    
    pick_player(centers, 1)
    pick_player(guards, 2)
    pick_player(forwards, 2)
    
    if len(starters) < 5:
        for idx, row in sorted_players.iterrows():
            if len(starters) >= 5: break
            if idx not in selected_indices:
                starters.append(row)
                selected_indices.add(idx)

    for idx, row in sorted_players.iterrows():
        if idx not in selected_indices:
            bench.append(row)
            
    return pd.DataFrame(starters), pd.DataFrame(bench)

def calculate_team_power(df, is_home=False):
    roster = df[df['availability'] != 'Out'].copy()
    if roster.empty: return 0.0, 0.0, "데이터 없음", []

    for col in ['pie', 'min', 'usg_pct']:
        roster[col] = pd.to_numeric(roster[col])

    roster['unit_value'] = roster['pie'].apply(calculate_individual_uv)
    roster['contribution'] = roster['unit_value'] * roster['min']
    
    total_minutes = roster['min'].sum()
    total_contribution = roster['contribution'].sum()
    
    if total_minutes < 240:
        missing = 240 - total_minutes
        total_contribution += (0.5 * missing)
        total_minutes = 240
        
    raw_score = (total_contribution / total_minutes) * 5
    if is_home: raw_score += 0.15

    top_2_usg = roster.nlargest(2, 'usg_pct')['usg_pct'].sum()
    penalty = 0.0
    if top_2_usg > 0.60:
        penalty = (top_2_usg - 0.60) * 3.0
        
    final_score = raw_score - penalty

    starters_df, bench_df = select_best_lineup(roster)
    
    detail_parts = []
    for _, row in starters_df.iterrows():
        pos_str = row['pos'] if row['pos'] else '?'
        detail_parts.append(f"{row['player_name']}({pos_str}/{row['unit_value']:.1f})")
    
    if not bench_df.empty:
        detail_parts.append(f"벤치({len(bench_df)}명)")
        
    if is_home: detail_parts.append("홈이점(+0.15)")
        
    return final_score, penalty, " + ".join(detail_parts), roster

def get_opponent_data(abbr):
    team_info = TEAMS.get(abbr)
    if not team_info: return None
    print(f"\n🔄 [{abbr}] 데이터 및 포지션 수집 중...")
    
    try:
        stats = leaguedashplayerstats.LeagueDashPlayerStats(
            season=SEASON,
            team_id_nullable=team_info['id'],
            measure_type_detailed_defense='Advanced',
            per_mode_detailed='PerGame'
        )
        stats_df = stats.get_data_frames()[0]
        stats_df = stats_df[ (stats_df['GP'] >= 5) & (stats_df['MIN'] >= 10) ].copy()
        
        roster = commonteamroster.CommonTeamRoster(season=SEASON, team_id=team_info['id'])
        roster_df = roster.get_data_frames()[0]
        df = pd.merge(stats_df, roster_df[['PLAYER', 'POSITION']], left_on='PLAYER_NAME', right_on='PLAYER', how='left')
        
        df = df[['PLAYER_NAME', 'MIN', 'PIE', 'USG_PCT', 'POSITION']].copy()
        df.columns = ['player_name', 'min', 'pie', 'usg_pct', 'pos']
        df['pos'] = df['pos'].fillna('F')

    except Exception as e:
        print(f"❌ 데이터 수집 에러: {e}")
        return None

    injury_url = f"https://www.espn.com/nba/team/injuries/_/name/{team_info['slug']}"
    out_players = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(injury_url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        for tag in soup.find_all('span', class_='Athlete__PlayerName'):
            name = tag.text.strip()
            parent_text = tag.parent.parent.get_text(" ", strip=True).lower()
            if "out" in parent_text:
                out_players.append(name)
    except: pass

    df['availability'] = 'OK'
    for idx, row in df.iterrows():
        nba_name = row['player_name']
        for out_name in out_players:
            if fuzz.partial_ratio(out_name.lower(), nba_name.lower()) >= 80:
                df.at[idx, 'availability'] = 'Out'
                break

    return df, out_players

def detect_todays_game_kst():
    """ 
    [NEW] KST 기준 일정 자동 감지 로직 
    - 한국 시간에서 14시간을 빼서 '미국 현지 경기 날짜'를 추산합니다.
    """
    print("📅 [KST 기준] 오늘의 경기 일정을 확인하는 중입니다...")
    
    try:
        # 1. 날짜 계산 (KST -> US Game Date)
        now_kst = datetime.now()
        us_game_date = now_kst - timedelta(hours=14)
        game_date_str = us_game_date.strftime("%Y-%m-%d")
        
        print(f"   (한국시간: {now_kst.strftime('%m-%d %H:%M')} -> 미국경기일: {game_date_str})")

        # 2. 해당 날짜의 스코어보드 조회
        board = scoreboardv2.ScoreboardV2(game_date=game_date_str)
        games = board.game_header.get_data_frame()
        
        # 3. 레이커스 경기 찾기
        lal_game = games[ (games['HOME_TEAM_ID'] == int(LAKERS_ID)) | (games['VISITOR_TEAM_ID'] == int(LAKERS_ID)) ]
        
        if lal_game.empty:
            return None, None 

        game_row = lal_game.iloc[0]
        
        # 4. 홈/원정 및 상대팀 식별
        if int(game_row['HOME_TEAM_ID']) == int(LAKERS_ID):
            is_home = True
            opp_id = str(game_row['VISITOR_TEAM_ID'])
        else:
            is_home = False
            opp_id = str(game_row['HOME_TEAM_ID'])
            
        opp_abbr = ID_TO_ABBR.get(opp_id, 'UNKNOWN')
        return is_home, opp_abbr
        
    except Exception as e:
        print(f"⚠️ 일정 조회 실패 (수동 모드 전환): {e}")
        return None, None

def main():
    print("=== [Unit Value] NBA 승부 예측기 V2.5 (KST Patch) ===")
    
    # [변경된 함수 호출]
    detected_home, detected_opp = detect_todays_game_kst()
    
    lal_is_home = False
    opp_input_needed = True
    
    if detected_opp:
        print(f"\n🚀 [자동 감지 성공] 오늘 경기가 발견되었습니다!")
        loc = "홈(Home)" if detected_home else "원정(Away)"
        print(f"   ▶ 장소: {loc}")
        print(f"   ▶ 상대: {detected_opp}")
        
        lal_is_home = detected_home
        target_opp = detected_opp
        opp_input_needed = False
    else:
        print("\n📭 오늘 예정된 레이커스 경기가 없습니다.")
        print("   (시뮬레이션을 위해 수동으로 설정합니다.)\n")
        is_home_input = input("🏟️  레이커스 홈 경기입니까? (Y/N): ").strip().upper()
        lal_is_home = (is_home_input == 'Y')

    if not os.path.exists(DB_PATH):
        print("❌ DB 없음. nbaapi.py 실행 필요.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        lakers_df = pd.read_sql("SELECT * FROM daily_stats WHERE date = ?", conn, params=(today,))
    except:
        print("❌ DB 에러. nbaapi.py를 다시 실행하세요.")
        return
    conn.close()
    
    if lakers_df.empty:
        print("❌ LAL 데이터 없음. nbaapi.py 실행 필요.")
        return

    while True:
        if opp_input_needed:
            print("\n" + "-"*60)
            opp_abbr = input("🥊 상대 팀 약어 (예: DEN, GSW) / 종료(Q): ").strip().upper()
            if opp_abbr == 'Q': break
        else:
            opp_abbr = target_opp
            
        if opp_abbr not in TEAMS:
            print("❌ 팀 정보를 찾을 수 없습니다.")
            if not opp_input_needed: break 
            continue
        
        opp_data = get_opponent_data(opp_abbr)
        if not opp_data: 
            if not opp_input_needed: break
            continue
            
        opp_df, opp_out_list = opp_data
        
        l_score, l_penalty, l_detail, l_roster = calculate_team_power(lakers_df, is_home=lal_is_home)
        o_score, o_penalty, o_detail, o_roster = calculate_team_power(opp_df, is_home=(not lal_is_home))
        
        l_out_list = lakers_df[lakers_df['availability'] == 'Out']['player_name'].tolist()

        print("\n" + "="*60)
        print(f"⚔️  MATCHUP: LAL vs {opp_abbr}")
        print("="*60)
        
        print(f"🟣 LAL 점수: {l_score:.3f}")
        print(f"🟣 LAL 점수(상세): {l_detail}")
        print(f"🚑 LAL 주요 결장: {', '.join(l_out_list) if l_out_list else '없음'}")
        print("-" * 60)
        print(f"⚪ {opp_abbr} 점수: {o_score:.3f} (패널티: {o_penalty:.3f})")
        print(f"⚪ {opp_abbr} 점수(상세): {o_detail}")
        print(f"🚑 {opp_abbr} 주요 결장: {', '.join(opp_out_list) if opp_out_list else '없음'}")
        
        diff = l_score - o_score
        print("\n[🔮 AI 예측 결과]")
        if diff > 0:
            print(f"🎉 레이커스 승리 예상 (격차: +{diff:.2f})")
            print("   👉 추천: 레이커스 승")
        else:
            print(f"💀 레이커스 패배 위기 (격차: {diff:.2f})")
            print(f"   👉 {opp_abbr}의 전력이 더 강합니다.")
            
        if not opp_input_needed:
            break

if __name__ == "__main__":
    main()