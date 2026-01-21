"""
한국 주식 데이터 소스 모듈

pykrx와 yfinance를 활용한 한국 주식 OHLCV 및 기술적 지표 데이터 제공
"""

from typing import Annotated
from datetime import datetime, timedelta
import pandas as pd
import os

try:
    from pykrx import stock as pykrx_stock
    PYKRX_AVAILABLE = True
except ImportError:
    PYKRX_AVAILABLE = False
    print("Warning: pykrx not installed. Install with: pip install pykrx")

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

from .stockstats_utils import StockstatsUtils


def normalize_korea_ticker(ticker: str) -> tuple[str, str]:
    """
    한국 종목코드 정규화

    Args:
        ticker: "005930", "005930.KS", "삼성전자" 등

    Returns:
        (6자리 코드, yfinance용 코드)
        예: ("005930", "005930.KS")
    """
    # 이미 6자리 숫자인 경우
    if ticker.isdigit() and len(ticker) == 6:
        return ticker, f"{ticker}.KS"

    # .KS 또는 .KQ 접미사가 있는 경우
    if ticker.endswith(".KS") or ticker.endswith(".KQ"):
        code = ticker.split(".")[0]
        return code, ticker

    # 숫자로만 구성되어 있지만 6자리가 아닌 경우 (앞에 0 채우기)
    if ticker.isdigit():
        code = ticker.zfill(6)
        return code, f"{code}.KS"

    # 종목명인 경우 (추후 종목명 → 코드 변환 기능 추가 가능)
    raise ValueError(f"알 수 없는 종목 형식: {ticker}")


def get_korea_stock_data(
    symbol: Annotated[str, "종목코드 (예: 005930, 005930.KS)"],
    start_date: Annotated[str, "시작일 (YYYY-MM-DD 형식)"],
    end_date: Annotated[str, "종료일 (YYYY-MM-DD 형식)"],
) -> str:
    """
    한국 주식 OHLCV 데이터 조회

    pykrx를 우선 사용하고, 실패 시 yfinance로 fallback
    """
    code, yf_ticker = normalize_korea_ticker(symbol)

    # 날짜 형식 검증
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    # pykrx로 먼저 시도
    if PYKRX_AVAILABLE:
        try:
            # pykrx는 YYYYMMDD 형식 사용
            start_pykrx = start_date.replace("-", "")
            end_pykrx = end_date.replace("-", "")

            data = pykrx_stock.get_market_ohlcv_by_date(
                start_pykrx, end_pykrx, code
            )

            if not data.empty:
                # 컬럼명 영문으로 변환
                data.columns = ["Open", "High", "Low", "Close", "Volume", "Value", "Change"]
                data = data[["Open", "High", "Low", "Close", "Volume"]]

                # 수치 반올림
                for col in ["Open", "High", "Low", "Close"]:
                    data[col] = data[col].round(0).astype(int)

                csv_string = data.to_csv()

                header = f"# {code} 주가 데이터 ({start_date} ~ {end_date})\n"
                header += f"# 총 {len(data)}개 레코드\n"
                header += f"# 데이터 소스: pykrx (한국거래소)\n"
                header += f"# 조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

                return header + csv_string

        except Exception as e:
            print(f"pykrx 조회 실패: {e}, yfinance로 fallback")

    # yfinance로 fallback
    if YFINANCE_AVAILABLE:
        try:
            ticker_obj = yf.Ticker(yf_ticker)
            data = ticker_obj.history(start=start_date, end=end_date)

            if not data.empty:
                if data.index.tz is not None:
                    data.index = data.index.tz_localize(None)

                # 기본 컬럼만 유지
                cols = ["Open", "High", "Low", "Close", "Volume"]
                data = data[[c for c in cols if c in data.columns]]

                for col in ["Open", "High", "Low", "Close"]:
                    if col in data.columns:
                        data[col] = data[col].round(0).astype(int)

                csv_string = data.to_csv()

                header = f"# {code} 주가 데이터 ({start_date} ~ {end_date})\n"
                header += f"# 총 {len(data)}개 레코드\n"
                header += f"# 데이터 소스: yfinance\n"
                header += f"# 조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

                return header + csv_string

        except Exception as e:
            return f"yfinance 조회 실패: {e}"

    return f"'{symbol}'에 대한 데이터를 찾을 수 없습니다. pykrx 또는 yfinance가 필요합니다."


def get_korea_stock_indicators(
    symbol: Annotated[str, "종목코드 (예: 005930)"],
    indicator: Annotated[str, "기술적 지표 (예: rsi, macd, boll)"],
    curr_date: Annotated[str, "기준일 (YYYY-MM-DD 형식)"],
    look_back_days: Annotated[int, "과거 조회 기간 (일)"] = 30,
) -> str:
    """
    한국 주식 기술적 지표 계산

    stockstats 라이브러리를 활용하여 지표 계산
    """
    from dateutil.relativedelta import relativedelta
    from stockstats import wrap

    code, yf_ticker = normalize_korea_ticker(symbol)

    # 지표 설명
    indicator_descriptions = {
        "close_50_sma": "50일 단순이동평균: 중기 추세 지표",
        "close_200_sma": "200일 단순이동평균: 장기 추세 지표",
        "close_10_ema": "10일 지수이동평균: 단기 모멘텀 지표",
        "macd": "MACD: 이동평균 수렴확산 지표",
        "macds": "MACD Signal: MACD 신호선",
        "macdh": "MACD Histogram: MACD 히스토그램",
        "rsi": "RSI: 상대강도지수 (과매수/과매도 판단)",
        "boll": "볼린저밴드 중심선 (20일 SMA)",
        "boll_ub": "볼린저밴드 상단",
        "boll_lb": "볼린저밴드 하단",
        "atr": "ATR: 평균진폭 (변동성 지표)",
        "vwma": "VWMA: 거래량가중이동평균",
        "mfi": "MFI: 자금흐름지수",
    }

    if indicator not in indicator_descriptions:
        return f"지원하지 않는 지표입니다. 지원 지표: {list(indicator_descriptions.keys())}"

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)

    # 지표 계산을 위해 더 많은 과거 데이터 필요 (최소 200일)
    data_start = curr_date_dt - relativedelta(days=365)

    try:
        # 데이터 가져오기 (pykrx 우선)
        if PYKRX_AVAILABLE:
            start_pykrx = data_start.strftime("%Y%m%d")
            end_pykrx = curr_date_dt.strftime("%Y%m%d")

            data = pykrx_stock.get_market_ohlcv_by_date(start_pykrx, end_pykrx, code)

            if not data.empty:
                data.columns = ["Open", "High", "Low", "Close", "Volume", "Value", "Change"]
                data = data[["Open", "High", "Low", "Close", "Volume"]]
                data = data.reset_index()
                data.columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
        else:
            # yfinance fallback
            ticker_obj = yf.Ticker(yf_ticker)
            data = ticker_obj.history(start=data_start.strftime("%Y-%m-%d"),
                                      end=curr_date_dt.strftime("%Y-%m-%d"))
            data = data.reset_index()
            data = data[["Date", "Open", "High", "Low", "Close", "Volume"]]

        # stockstats로 지표 계산
        df = wrap(data)
        df[indicator]  # 지표 계산 트리거

        # 날짜별 결과 추출
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        result_dict = {}
        for _, row in df.iterrows():
            date_str = row["Date"]
            value = row[indicator]
            if pd.isna(value):
                result_dict[date_str] = "N/A"
            else:
                result_dict[date_str] = f"{value:.4f}"

        # 결과 문자열 생성
        ind_string = ""
        current_dt = curr_date_dt
        while current_dt >= before:
            date_str = current_dt.strftime("%Y-%m-%d")
            value = result_dict.get(date_str, "N/A (휴장일)")
            ind_string += f"{date_str}: {value}\n"
            current_dt = current_dt - timedelta(days=1)

        result_str = (
            f"## {code} {indicator} 지표 ({before.strftime('%Y-%m-%d')} ~ {curr_date})\n\n"
            + ind_string
            + f"\n\n**지표 설명**: {indicator_descriptions.get(indicator, '')}"
        )

        return result_str

    except Exception as e:
        return f"기술적 지표 계산 실패: {e}"


def get_korea_stock_info(
    symbol: Annotated[str, "종목코드 (예: 005930)"],
) -> str:
    """
    한국 주식 기본 정보 조회

    종목명, 시가총액, PER, PBR 등 기본 정보 반환
    """
    code, yf_ticker = normalize_korea_ticker(symbol)

    try:
        if PYKRX_AVAILABLE:
            # 오늘 날짜 기준 정보 조회
            today = datetime.now().strftime("%Y%m%d")

            # 기본 시세 정보
            fundamental = pykrx_stock.get_market_cap_by_ticker(today)

            if code in fundamental.index:
                info = fundamental.loc[code]
                result = f"""## {code} 종목 기본 정보

| 항목 | 값 |
|------|-----|
| 시가총액 | {info['시가총액']:,.0f}원 |
| 거래량 | {info['거래량']:,.0f}주 |
| 거래대금 | {info['거래대금']:,.0f}원 |
| 상장주식수 | {info['상장주식수']:,.0f}주 |

*조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
                return result

        # yfinance fallback
        if YFINANCE_AVAILABLE:
            ticker_obj = yf.Ticker(yf_ticker)
            info = ticker_obj.info

            result = f"""## {code} 종목 기본 정보

| 항목 | 값 |
|------|-----|
| 종목명 | {info.get('shortName', 'N/A')} |
| 시가총액 | {info.get('marketCap', 'N/A'):,}원 |
| PER | {info.get('trailingPE', 'N/A')} |
| PBR | {info.get('priceToBook', 'N/A')} |
| 52주 최고 | {info.get('fiftyTwoWeekHigh', 'N/A'):,}원 |
| 52주 최저 | {info.get('fiftyTwoWeekLow', 'N/A'):,}원 |

*조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
            return result

    except Exception as e:
        return f"종목 정보 조회 실패: {e}"

    return f"'{symbol}'에 대한 정보를 찾을 수 없습니다."
