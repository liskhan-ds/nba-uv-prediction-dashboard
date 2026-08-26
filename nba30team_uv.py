import pandas as pd
from nba_api.stats.endpoints import leaguedashplayerstats

# 웅쓰의 오리지널 V1 개인 UV 계산기 (그대로 복사)
def calculate_individual_uv_v1(pie):
    # 웅쓰의 V1 공식: 1.0 + (pie - 0.10) * 20
    uv = 1.0 + (pie - 0.10) * 20
    # 웅쓰의 V1 상한선: 3.5
    return max(0.1, min(uv, 3.5))

def get_30_teams_current_uv():
    print("🏀 [V1 로직] 30개 팀 현재 UV 합 산출 중 (홈 이점 제외)...")
    
    # 1. 현재 시즌 전체 데이터 수집
    stats = leaguedashplayerstats.LeagueDashPlayerStats(
        season='2025-26',
        measure_type_detailed_defense='Advanced',
        per_mode_detailed='PerGame'
    )
    df = stats.get_data_frames()[0]
    
    # 2. 최소 기준 필터링 (트레이드 선수 반영: GP >= 1, MIN >= 10)
    df = df[(df['GP'] >= 1) & (df['MIN'] >= 10)].copy()
    
    # 3. 개인별 UV 및 기여도(Contribution) 계산
    df['unit_value'] = df['PIE'].apply(calculate_individual_uv_v1)
    df['contribution'] = df['unit_value'] * df['MIN']
    
    # 4. 팀별 가중 평균 합산 (웅쓰의 240분 환산 로직)
    team_results = []
    
    for team_abbr in df['TEAM_ABBREVIATION'].unique():
        roster = df[df['TEAM_ABBREVIATION'] == team_abbr].copy()
        
        total_minutes = roster['MIN'].sum()
        total_contribution = roster['contribution'].sum()
        
        # 웅쓰의 부족 시간(240분 미만) 보정 로직
        if total_minutes < 240:
            missing = 240 - total_minutes
            total_contribution += (0.5 * missing)
            total_minutes = 240
            
        # 웅쓰의 최종 팀 스코어 공식 (홈 이점 0.15 제외)
        raw_score = (total_contribution / total_minutes) * 5
        
        # 패널티 로직은 개별 매치업 상황이 아니므로 여기서는 기본 UV합만 추출
        team_results.append({
            'TEAM': team_abbr,
            'V1_TEAM_UV': round(raw_score, 3)
        })

    # 5. 결과 정리 및 출력
    result_df = pd.DataFrame(team_results).sort_values(by='V1_TEAM_UV', ascending=False)
    
    print("\n" + "="*40)
    print("📊 NBA 30개 팀 현재 UV 리포트 (V1)")
    print("="*40)
    print(result_df.to_string(index=False))
    print("="*40)
    
    # 파일 저장
    result_df.to_csv('nba_30_teams_v1_uv.csv', index=False, encoding='utf-8-sig')
    print(f"\n💾 결과가 'nba_30_teams_v1_uv.csv'로 저장되었습니다.")

if __name__ == "__main__":
    get_30_teams_current_uv()