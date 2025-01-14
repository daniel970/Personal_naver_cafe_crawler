import gradio as gr
import re
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup

from apscheduler.schedulers.background import BackgroundScheduler
import threading

# -------------------------
# 전역 변수: 게시물 저장
# -------------------------
posts_data = []

# -------------------------
# 네이버 로그인 함수
# -------------------------
def naver_login(driver, user_id, user_pw):
    driver.get("https://nid.naver.com/nidlogin.login")
    time.sleep(1)
    
    id_input = driver.find_element(By.ID, "id")
    id_input.clear()
    id_input.send_keys(user_id)

    pw_input = driver.find_element(By.ID, "pw")
    pw_input.clear()
    pw_input.send_keys(user_pw)

    login_button = driver.find_element(By.ID, "log.login")
    login_button.click()
    time.sleep(2)

    # 추가 인증(CAPTCHA 등) 발생 시 직접 해결해야 할 수도 있음

# -------------------------
# 특정 카페 "중고[이어폰]" 크롤링 함수
# -------------------------
def crawl_middle_earphone(driver):
    """ 
    driver: 네이버 로그인 상태여야 함 
    returns: [{'title': ..., 'content': ...}, ...] 리스트
    """
    cafe_url = "https://cafe.naver.com/drhp"
    driver.get(cafe_url)
    time.sleep(2)

    # 실제 "중고[이어폰]" 게시판의 메뉴ID를 확인해 수정
    menu_id = 999  # 예시. 실제 menuId 확인 후 수정 필요!
    board_url = f"{cafe_url}?iframe_url=/ArticleList.nhn?search.menuid={menu_id}&search.boardtype=L"
    driver.get(board_url)
    time.sleep(2)

    # iframe 전환
    driver.switch_to.frame("cafe_main")

    page_html = driver.page_source
    soup = BeautifulSoup(page_html, "html.parser")

    # 게시글 목록에서 a 태그 찾기 (카페마다 구조가 다를 수 있으므로 실제로 확인 필요)
    article_links = soup.select("a.article")  # 가령 class='article'인 링크

    temp_data = []
    for link in article_links:
        title = link.get_text(strip=True)
        post_href = link.get("href")

        try:
            # Selenium으로 해당 게시글 클릭
            driver.find_element(By.CSS_SELECTOR, f"a.article[href='{post_href}']").click()
            time.sleep(2)

            # 게시글로 넘어간 뒤, iframe 변화가 없으면 그대로 / 있으면 다시 switch_to.frame(...)
            post_html = driver.page_source
            post_soup = BeautifulSoup(post_html, "html.parser")

            # 본문 파싱 (카페 마다 구조 다름, 여기서는 예시)
            content_tag = post_soup.select_one("div.se-viewer")
            if content_tag:
                content = content_tag.get_text("\n", strip=True)
            else:
                content = "본문 추출 실패"

            temp_data.append({"title": title, "content": content})

            # 뒤로가기
            driver.back()
            time.sleep(2)
            driver.switch_to.frame("cafe_main")

        except Exception as e:
            print("게시글 파싱 오류:", e)
            # 혹시 문제가 생기면 다시 게시판 목록으로 돌아가기
            driver.get(board_url)
            time.sleep(2)
            driver.switch_to.frame("cafe_main")

    return temp_data

# -------------------------
# 전체 크롤링 로직
# -------------------------
def crawl_cafe_posts(user_id, user_pw):
    """ 
    user_id, user_pw를 받아서 크롤링 실행 후 posts_data 업데이트 
    """
    global posts_data

    # 1) 드라이버 세팅
    chrome_options = webdriver.ChromeOptions()
    # 필요하다면 headless 설정
    # chrome_options.add_argument("--headless")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # 2) 네이버 로그인
    try:
        naver_login(driver, user_id, user_pw)
    except Exception as e:
        driver.quit()
        return f"네이버 로그인 실패: {str(e)}"

    # 3) 크롤링
    try:
        new_posts = crawl_middle_earphone(driver)
        posts_data = new_posts
        msg = f"크롤링 완료: {len(new_posts)}개 게시글"
    except Exception as e:
        msg = f"크롤링 중 오류 발생: {str(e)}"
    finally:
        driver.quit()

    return msg

# -------------------------
# 검색 함수
# -------------------------
def search_posts(keyword):
    global posts_data
    if not keyword:
        return posts_data
    
    # 부분 일치 (대소문자 구분X)
    pattern = re.compile(keyword, re.IGNORECASE)
    filtered = []
    for p in posts_data:
        if pattern.search(p["title"]):
            filtered.append(p)
    return filtered

# -------------------------
# Gradio용 이벤트 함수
# -------------------------
def run_crawl(user_id, user_pw):
    """그라디오에서 '크롤링 실행' 버튼 클릭 시 수행"""
    result_msg = crawl_cafe_posts(user_id, user_pw)
    # 크롤링 후, 화면에 결과 메시지와 함께 현재 posts_data 반환
    return result_msg, posts_data

def run_search(keyword):
    """그라디오에서 '검색' 버튼 클릭 시 수행"""
    results = search_posts(keyword)
    return results

# -------------------------
# (선택) 5분마다 자동 크롤링
# Hugging Face Spaces 무료 플랜은 앱이 슬립될 수 있어 항상 보장되진 않음
# -------------------------
scheduler = BackgroundScheduler()

def scheduled_crawl():
    # 아이디/비번 하드코딩 or 환경변수로 가져오거나 etc...
    # 유의: 절대 public repo에 민감정보 커밋 금지
    user_id = "YOUR_ID"
    user_pw = "YOUR_PW"
    print("[스케줄러] 5분마다 크롤링 시도...")
    crawl_cafe_posts(user_id, user_pw)

# 5분(300초) 간격
scheduler.add_job(scheduled_crawl, 'interval', minutes=5)
# 별도의 스레드에서 스케줄러 동작
scheduler_thread = threading.Thread(target=scheduler.start)
scheduler_thread.start()

# -------------------------
# Gradio 인터페이스 구성
# -------------------------
def make_interface():
    with gr.Blocks() as demo:
        gr.Markdown("## 네이버 카페 (중고[이어폰]) 게시글 크롤링 데모 - Gradio")

        with gr.Row():
            user_id = gr.Textbox(label="네이버 ID", placeholder="아이디 입력")
            user_pw = gr.Textbox(label="네이버 PW", placeholder="비밀번호 입력", type="password")
            crawl_btn = gr.Button("크롤링 실행")

        result_msg = gr.Textbox(label="크롤링 상태", interactive=False)
        
        with gr.Accordion("게시글 목록", open=True):
            # 게시글 정보를 표시할 컴포넌트
            posts_view = gr.Dataframe(
                headers=["Title", "Content"], 
                datatype=["str", "str"], 
                row_count=(0, "dynamic"),
                col_count=2
            )

        with gr.Row():
            keyword = gr.Textbox(label="제목 검색", placeholder="검색어 입력")
            search_btn = gr.Button("검색 실행")

        # 이벤트 연결
        crawl_btn.click(
            fn=run_crawl, 
            inputs=[user_id, user_pw],
            outputs=[result_msg, posts_view]  # 결과 메시지 + 전체 게시글
        )
        search_btn.click(
            fn=run_search,
            inputs=[keyword],
            outputs=[posts_view]  # 필터링된 게시글 리스트
        )

    return demo


if __name__ == "__main__":
    demo = make_interface()
    demo.launch()
