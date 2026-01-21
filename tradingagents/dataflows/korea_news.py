"""
한국 뉴스 데이터 소스 모듈

네이버 금융 뉴스 스크래핑을 통한 종목별 뉴스 및 글로벌 경제 뉴스 제공
"""

from typing import Annotated
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import time


# HTTP 요청 헤더 (User-Agent)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def normalize_stock_code(ticker: str) -> str:
    """종목코드 정규화 (6자리)"""
    if ticker.endswith(".KS") or ticker.endswith(".KQ"):
        ticker = ticker.split(".")[0]
    return ticker.zfill(6)


def get_korea_news(
    ticker: Annotated[str, "종목코드 (예: 005930)"],
    start_date: Annotated[str, "시작일 (YYYY-MM-DD 형식)"],
    end_date: Annotated[str, "종료일 (YYYY-MM-DD 형식)"],
) -> str:
    """
    한국 주식 종목별 뉴스 조회

    네이버 금융의 종목 뉴스를 스크래핑하여 반환
    """
    stock_code = normalize_stock_code(ticker)

    # 네이버 금융 종목 뉴스 URL
    base_url = f"https://finance.naver.com/item/news_news.nhn?code={stock_code}&page=1"

    try:
        response = requests.get(base_url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # 뉴스 테이블 찾기
        news_table = soup.select_one("table.type5")

        if not news_table:
            return f"종목코드 '{stock_code}'의 뉴스를 찾을 수 없습니다."

        news_items = []
        rows = news_table.select("tr")

        for row in rows:
            # 제목과 날짜 추출
            title_elem = row.select_one("td.title a")
            date_elem = row.select_one("td.date")
            source_elem = row.select_one("td.info")

            if title_elem and date_elem:
                title = title_elem.get_text(strip=True)
                date_str = date_elem.get_text(strip=True)
                source = source_elem.get_text(strip=True) if source_elem else "N/A"
                link = "https://finance.naver.com" + title_elem.get("href", "")

                news_items.append({
                    "title": title,
                    "date": date_str,
                    "source": source,
                    "link": link
                })

        # 결과 포맷팅
        result = f"""## {stock_code} 종목 관련 뉴스

### 조회 기간: {start_date} ~ {end_date}

"""
        if news_items:
            result += "| 날짜 | 제목 | 출처 |\n"
            result += "|------|------|------|\n"

            for item in news_items[:20]:  # 최대 20개
                # 제목이 너무 길면 자르기
                title = item["title"][:50] + "..." if len(item["title"]) > 50 else item["title"]
                result += f"| {item['date']} | {title} | {item['source']} |\n"

            result += "\n### 뉴스 요약 분석\n\n"
            result += "*위 뉴스들을 종합하여 시장 심리와 기업 동향을 분석해주세요.*\n"
        else:
            result += "*해당 기간 동안 관련 뉴스가 없습니다.*\n"

        result += f"\n*조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
        return result

    except requests.RequestException as e:
        return f"네이버 금융 뉴스 조회 실패: {e}"
    except Exception as e:
        return f"뉴스 파싱 실패: {e}"


def get_korea_global_news(
    curr_date: Annotated[str, "기준일 (YYYY-MM-DD 형식)"],
    look_back_days: Annotated[int, "과거 조회 기간 (일)"] = 7,
    limit: Annotated[int, "최대 뉴스 개수"] = 20,
) -> str:
    """
    한국 글로벌 경제 뉴스 조회

    네이버 금융의 시장 뉴스를 스크래핑하여 반환
    """
    # 네이버 금융 시장 뉴스 URL
    news_urls = [
        ("국내 증시", "https://finance.naver.com/news/mainnews.nhn?type=1"),
        ("해외 증시", "https://finance.naver.com/news/mainnews.nhn?type=2"),
        ("경제 일반", "https://finance.naver.com/news/mainnews.nhn?type=3"),
    ]

    all_news = []

    for category, url in news_urls:
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")

            # 뉴스 리스트 찾기
            news_list = soup.select("ul.newsList li")

            for item in news_list[:10]:  # 각 카테고리 최대 10개
                title_elem = item.select_one("a")
                date_elem = item.select_one("span.wdate")

                if title_elem:
                    title = title_elem.get_text(strip=True)
                    date_str = date_elem.get_text(strip=True) if date_elem else "N/A"

                    all_news.append({
                        "category": category,
                        "title": title,
                        "date": date_str
                    })

            time.sleep(0.2)  # Rate limiting

        except Exception as e:
            print(f"{category} 뉴스 조회 실패: {e}")
            continue

    # 결과 포맷팅
    result = f"""## 글로벌 경제 뉴스

### 조회 기준일: {curr_date}
### 조회 기간: 최근 {look_back_days}일

"""

    if all_news:
        current_category = None
        for item in all_news[:limit]:
            if item["category"] != current_category:
                current_category = item["category"]
                result += f"\n### {current_category}\n\n"
                result += "| 날짜 | 제목 |\n"
                result += "|------|------|\n"

            title = item["title"][:60] + "..." if len(item["title"]) > 60 else item["title"]
            result += f"| {item['date']} | {title} |\n"

        result += "\n### 시장 동향 요약\n\n"
        result += "*위 뉴스들을 종합하여 거시경제 동향과 시장 심리를 분석해주세요.*\n"
    else:
        result += "*뉴스를 가져올 수 없습니다.*\n"

    result += f"\n*조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
    return result


def get_korea_insider_sentiment(
    ticker: Annotated[str, "종목코드 (예: 005930)"],
) -> str:
    """
    한국 주식 투자자 심리 데이터 조회

    네이버 금융 토론방 분석 (감성 분석용)
    """
    stock_code = normalize_stock_code(ticker)

    # 네이버 금융 종목 토론방 URL
    base_url = f"https://finance.naver.com/item/board.nhn?code={stock_code}"

    try:
        response = requests.get(base_url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # 토론방 게시글 테이블
        board_table = soup.select_one("table.type2")

        if not board_table:
            return f"종목코드 '{stock_code}'의 토론방을 찾을 수 없습니다."

        posts = []
        rows = board_table.select("tr")

        for row in rows:
            cells = row.select("td")
            if len(cells) >= 4:
                title_elem = cells[1].select_one("a")
                views_elem = cells[3]
                good_elem = cells[4] if len(cells) > 4 else None
                bad_elem = cells[5] if len(cells) > 5 else None

                if title_elem:
                    title = title_elem.get_text(strip=True)
                    views = views_elem.get_text(strip=True) if views_elem else "0"
                    good = good_elem.get_text(strip=True) if good_elem else "0"
                    bad = bad_elem.get_text(strip=True) if bad_elem else "0"

                    posts.append({
                        "title": title,
                        "views": views,
                        "good": good,
                        "bad": bad
                    })

        # 결과 포맷팅
        result = f"""## {stock_code} 투자자 심리 분석

### 종목 토론방 최근 게시글

"""
        if posts:
            result += "| 제목 | 조회 | 공감 | 비공감 |\n"
            result += "|------|------|------|--------|\n"

            for post in posts[:15]:  # 최대 15개
                title = post["title"][:40] + "..." if len(post["title"]) > 40 else post["title"]
                result += f"| {title} | {post['views']} | {post['good']} | {post['bad']} |\n"

            result += "\n### 심리 분석 요약\n\n"
            result += "*위 게시글들의 제목과 반응을 분석하여 투자자 심리를 파악해주세요.*\n"
            result += "*'공감' 대비 '비공감' 비율, 게시글 제목의 긍정/부정 어조 등을 고려하세요.*\n"
        else:
            result += "*토론방 게시글을 가져올 수 없습니다.*\n"

        result += f"\n*조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
        return result

    except requests.RequestException as e:
        return f"네이버 금융 토론방 조회 실패: {e}"
    except Exception as e:
        return f"토론방 파싱 실패: {e}"
