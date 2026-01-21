"""
TradingAgents 한국 시장 테스트 스크립트

삼성전자(005930)를 대상으로 한국 시장 분석 및 모의투자 테스트
"""

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import KOREA_CONFIG, get_korea_config
from tradingagents.execution.korea_investment import KoreaInvestmentExecutor
from datetime import datetime


def test_korea_data_sources():
    """한국 데이터 소스 테스트"""
    print("=" * 60)
    print("한국 데이터 소스 테스트")
    print("=" * 60)

    # 주가 데이터 테스트
    print("\n[1] 삼성전자 주가 데이터 테스트...")
    try:
        from tradingagents.dataflows.korea_stock import get_korea_stock_data
        result = get_korea_stock_data("005930", "2025-01-14", "2025-01-21")
        print(result[:500] + "..." if len(result) > 500 else result)
        print("✅ 주가 데이터 조회 성공")
    except Exception as e:
        print(f"❌ 주가 데이터 조회 실패: {e}")

    # 네이버 뉴스 테스트
    print("\n[2] 삼성전자 뉴스 테스트...")
    try:
        from tradingagents.dataflows.korea_news import get_korea_news
        result = get_korea_news("005930", "2025-01-14", "2025-01-21")
        print(result[:500] + "..." if len(result) > 500 else result)
        print("✅ 뉴스 조회 성공")
    except Exception as e:
        print(f"❌ 뉴스 조회 실패: {e}")

    # DART 공시 테스트 (API 키 필요)
    print("\n[3] DART 전자공시 테스트...")
    try:
        from tradingagents.dataflows.korea_dart import get_korea_fundamentals
        result = get_korea_fundamentals("005930", "2025-01-21")
        print(result[:500] + "..." if len(result) > 500 else result)
        print("✅ DART 조회 성공")
    except Exception as e:
        print(f"❌ DART 조회 실패: {e}")


def run_analysis(ticker: str = "005930", trade_date: str = None):
    """
    한국 주식 분석 실행

    Args:
        ticker: 종목코드 (기본값: 삼성전자 005930)
        trade_date: 거래 기준일 (기본값: 오늘)
    """
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    print("=" * 60)
    print(f"TradingAgents 한국 시장 분석")
    print(f"종목: {ticker}")
    print(f"기준일: {trade_date}")
    print("=" * 60)

    # 한국 시장 설정 로드
    config = get_korea_config()

    # TradingAgentsGraph 생성
    print("\n에이전트 초기화 중...")
    ta = TradingAgentsGraph(debug=True, config=config)

    # 분석 실행
    print(f"\n{ticker} 분석 시작...")
    final_state, decision = ta.propagate(ticker, trade_date)

    print("\n" + "=" * 60)
    print("분석 완료")
    print("=" * 60)
    print(f"\n최종 결정: {decision}")

    return final_state, decision


def run_with_execution(ticker: str = "005930", trade_date: str = None):
    """
    분석 + 모의투자 실행

    주의: 한국투자증권 API 키가 설정되어 있어야 함
    """
    # 분석 실행
    final_state, decision = run_analysis(ticker, trade_date)

    # 모의투자 실행
    print("\n" + "=" * 60)
    print("모의투자 실행")
    print("=" * 60)

    config = get_korea_config()
    executor = KoreaInvestmentExecutor(config)

    # 결정에 따른 주문 실행
    result = executor.execute(ticker, decision)
    print(f"\n실행 결과: {result}")

    # 포트폴리오 현황
    print("\n" + executor.get_portfolio_summary())

    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "test":
            # 데이터 소스만 테스트
            test_korea_data_sources()

        elif command == "analyze":
            # 분석만 실행
            ticker = sys.argv[2] if len(sys.argv) > 2 else "005930"
            run_analysis(ticker)

        elif command == "trade":
            # 분석 + 모의투자
            ticker = sys.argv[2] if len(sys.argv) > 2 else "005930"
            run_with_execution(ticker)

        else:
            print(f"""
TradingAgents 한국 시장 테스트

사용법:
    python main_korea.py test      # 데이터 소스 테스트
    python main_korea.py analyze   # 삼성전자 분석
    python main_korea.py analyze 035720  # 특정 종목 분석
    python main_korea.py trade     # 분석 + 모의투자 실행
""")
    else:
        # 기본: 데이터 소스 테스트
        test_korea_data_sources()
