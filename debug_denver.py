import requests
from bs4 import BeautifulSoup

# ESPN 덴버 부상자 페이지
URL = "https://www.espn.com/nba/team/injuries/_/name/den/denver-nuggets"

def check_html_structure():
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(URL, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    print(f"=== [ESPN 덴버 부상자 원본 데이터 확인] ===\n")
    
    # 선수 이름 태그를 모두 찾습니다.
    players = soup.find_all('span', class_='Athlete__PlayerName')
    
    if not players:
        print("❌ 선수 이름 태그를 찾지 못했습니다. (ESPN 구조 변경 의심)")
        return

    for p in players:
        name = p.text.strip()
        # 부모의 부모 태그에 상태 텍스트가 숨어있는지 확인
        parent_text = p.parent.parent.get_text(" | ", strip=True)
        
        print(f"👤 선수명: {name}")
        print(f"📄 원본 텍스트: {parent_text}")
        print("-" * 50)

if __name__ == "__main__":
    check_html_structure()