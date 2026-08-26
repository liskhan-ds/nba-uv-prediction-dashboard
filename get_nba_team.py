import sqlite3
import sys
import os
import pandas as pd

DB_NAME = "nba_uv_2026_27.db"

def main():
    if len(sys.argv) < 2:
        print("⚠️ 사용법: python3 get_nba_team.py [팀 약어]")
        print("예시: python3 get_nba_team.py BOS 또는 python3 get_nba_team.py LAL")
        sys.exit(1)
        
    team_abbr = sys.argv[1].upper()
    
    if not os.path.exists(DB_NAME):
        print(f"❌ DB 파일('{DB_NAME}')이 없습니다. 먼저 python3 init_nba_db.py를 실행해 주세요.")
        sys.exit(1)
        
    conn = sqlite3.connect(DB_NAME)
    
    # 1. 팀 UV 데이터 쿼리
    team_df = pd.read_sql("SELECT * FROM teams_uv WHERE team_abbr = ?", conn, params=(team_abbr,))
    
    if team_df.empty:
        print(f"❌ '{team_abbr}' 팀 정보를 DB에서 찾을 수 없습니다. (올바른 팀 약어인지 확인하세요)")
        conn.close()
        sys.exit(1)
        
    t = team_df.iloc[0]
    
    # 2. 선수 목록 쿼리
    players_df = pd.read_sql("SELECT * FROM players_uv WHERE team_abbr = ? ORDER BY min_rank ASC", conn, params=(team_abbr,))
    conn.close()
    
    # 3. 출력 포맷 (55:40:5 가중치 반영)
    print("\n=========================================================================================")
    print(f"🏀 [2026-27 시즌 DB 즉시 조회] {t['team_name']} ({t['team_abbr']}) - UV 리포트")
    print("=========================================================================================")
    print(f"• 55:40:5 가중치 적용 최종 팀 UV : 🌟 {t['final_team_uv']:.2f} (5.0 기준)")
    print(f"  ├─ 1. 주전 5인 기여도 (55%)    : {t['starters_contrib']:.2f} (주전 UV 합산: {t['starters_uv_sum']:.2f})")
    print(f"  ├─ 2. 핵심 3인 기여도 (40%)    : {t['rotation_contrib']:.2f} (핵심 UV 평균: {t['rotation_uv_avg']:.2f})")
    print(f"  └─ 3. 딥 벤치 기여도 (5%)      : {t['bench_contrib']:.2f} (벤치 UV 평균: {t['bench_uv_avg']:.2f})")
    print("-----------------------------------------------------------------------------------------")
    print("📋 선수단 개별 UV 및 주요 스탯")
    print("-----------------------------------------------------------------------------------------")
    print(f"| 순위 | 역할군 | 선수명 | 포지션 | MIN | PTS | REB | AST | PIE | 개별 UV |")
    print(f"|---|---|---|---|---|---|---|---|---|---|")
    
    for idx, p in players_df.iterrows():
        print(f"| {p['min_rank']} | {p['role_group']} | {p['player_name']} | {p['position']} | {p['min_per_game']:.1f}m | {p['pts']:.1f} | {p['reb']:.1f} | {p['ast']:.1f} | {p['pie']*100:.1f}% | {p['individual_uv']:.2f} |")
        
    print("=========================================================================================\n")

if __name__ == "__main__":
    main()
