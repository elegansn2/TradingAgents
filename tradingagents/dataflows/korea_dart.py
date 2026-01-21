"""
DART 전자공시 데이터 소스 모듈

dart-fss 라이브러리를 활용한 한국 기업 재무제표 및 공시 정보 제공
"""

from typing import Annotated
from datetime import datetime, timedelta
import os
import pandas as pd

try:
    import dart_fss as dart
    DART_AVAILABLE = True
except ImportError:
    DART_AVAILABLE = False
    print("Warning: dart-fss not installed. Install with: pip install dart-fss")

from .config import get_config


# 주요 종목코드 → 기업코드 매핑 (캐싱용)
CORP_CODE_CACHE = {}
CORP_LIST_CACHE = None


def init_dart_api():
    """DART API 초기화"""
    if not DART_AVAILABLE:
        return False

    config = get_config()
    api_key = config.get("dart_api_key") or os.getenv("DART_API_KEY")

    if not api_key:
        print("Warning: DART_API_KEY not set")
        return False

    try:
        dart.set_api_key(api_key)
        return True
    except Exception as e:
        print(f"DART API 초기화 실패: {e}")
        return False


def get_corp_list_cached():
    """캐싱된 기업 목록 반환"""
    global CORP_LIST_CACHE
    if CORP_LIST_CACHE is None:
        CORP_LIST_CACHE = dart.get_corp_list()
    return CORP_LIST_CACHE


def get_corp_code(stock_code: str) -> str:
    """
    종목코드(6자리)로 기업 고유번호 조회

    Args:
        stock_code: 6자리 종목코드 (예: "005930")

    Returns:
        DART 기업 고유번호
    """
    global CORP_CODE_CACHE

    # 캐시 확인
    if stock_code in CORP_CODE_CACHE:
        return CORP_CODE_CACHE[stock_code]

    if not init_dart_api():
        return None

    try:
        # 전체 기업 목록에서 검색
        corp_list = get_corp_list_cached()
        corp = corp_list.find_by_stock_code(stock_code)

        if corp:
            CORP_CODE_CACHE[stock_code] = corp.corp_code
            return corp.corp_code

    except Exception as e:
        print(f"기업코드 조회 실패: {e}")

    return None


def normalize_stock_code(ticker: str) -> str:
    """종목코드 정규화 (6자리)"""
    if ticker.endswith(".KS") or ticker.endswith(".KQ"):
        ticker = ticker.split(".")[0]
    return ticker.zfill(6)


def get_korea_fundamentals(
    ticker: Annotated[str, "종목코드 (예: 005930)"],
    curr_date: Annotated[str, "기준일 (YYYY-MM-DD 형식)"],
) -> str:
    """
    한국 기업 기본 재무정보 조회

    기업개요, 주요 재무비율, 최근 공시 정보 등 포함
    """
    stock_code = normalize_stock_code(ticker)

    if not init_dart_api():
        return "DART API를 사용할 수 없습니다. DART_API_KEY를 설정해주세요."

    try:
        corp_list = get_corp_list_cached()
        corp = corp_list.find_by_stock_code(stock_code)

        if not corp:
            return f"종목코드 '{stock_code}'에 해당하는 기업을 찾을 수 없습니다."

        # 기업 개요
        result = f"""## {corp.corp_name} ({stock_code}) 기업 분석

### 기업 개요

| 항목 | 내용 |
|------|------|
| 회사명 | {corp.corp_name} |
| 영문명 | {getattr(corp, 'corp_eng_name', 'N/A')} |
| 종목코드 | {stock_code} |
| 법인등록번호 | {getattr(corp, 'corp_code', 'N/A')} |
| 업종 | {getattr(corp, 'sector', 'N/A')} |
| 시장구분 | {getattr(corp, 'market_type', 'N/A')} |

"""

        # 최근 공시 조회 (최근 30일)
        end_date = datetime.strptime(curr_date, "%Y-%m-%d")
        start_date = end_date - timedelta(days=30)

        try:
            reports = corp.search_filings(
                bgn_de=start_date.strftime("%Y%m%d"),
                end_de=end_date.strftime("%Y%m%d"),
                page_count=20
            )

            if reports and len(reports) > 0:
                result += "### 최근 공시 (최근 30일)\n\n"
                result += "| 날짜 | 보고서명 |\n"
                result += "|------|----------|\n"

                for report in reports[:10]:  # 최대 10개
                    rcept_dt = getattr(report, 'rcept_dt', 'N/A')
                    report_nm = getattr(report, 'report_nm', 'N/A')
                    result += f"| {rcept_dt} | {report_nm} |\n"

                result += "\n"
            else:
                result += "*최근 30일간 공시가 없습니다.*\n\n"
        except Exception as e:
            result += f"*최근 공시 조회 실패: {e}*\n\n"

        result += f"\n*조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
        return result

    except Exception as e:
        return f"기업 정보 조회 실패: {e}"


def get_korea_balance_sheet(
    ticker: Annotated[str, "종목코드 (예: 005930)"],
    freq: Annotated[str, "조회 주기: 'annual' 또는 'quarterly'"] = "annual",
    curr_date: Annotated[str, "기준일"] = None,
) -> str:
    """
    한국 기업 재무상태표 조회
    """
    stock_code = normalize_stock_code(ticker)

    if not init_dart_api():
        return "DART API를 사용할 수 없습니다."

    try:
        corp_list = get_corp_list_cached()
        corp = corp_list.find_by_stock_code(stock_code)

        if not corp:
            return f"종목코드 '{stock_code}'에 해당하는 기업을 찾을 수 없습니다."

        # 최근 3년간 재무제표 추출
        report_tp = "annual" if freq == "annual" else "quarter"
        bgn_de = (datetime.now() - timedelta(days=1100)).strftime("%Y%m%d")

        try:
            fs = corp.extract_fs(
                bgn_de=bgn_de,
                fs_tp=('bs',),  # 재무상태표만
                report_tp=report_tp,
                progressbar=False
            )

            if fs is None or fs.bs is None:
                return f"'{corp.corp_name}'의 재무상태표를 찾을 수 없습니다."

            bs_df = fs.bs

            result = f"""## {corp.corp_name} ({stock_code}) 재무상태표

### 주요 재무상태 항목

"""
            # DataFrame을 마크다운 테이블로 변환
            if not bs_df.empty:
                # 주요 항목만 선택
                key_items = ['자산총계', '부채총계', '자본총계', '유동자산', '비유동자산', '유동부채', '비유동부채']

                result += "| 항목 | " + " | ".join(bs_df.columns[-3:].astype(str)) + " |\n"
                result += "|------" + "|------" * len(bs_df.columns[-3:]) + "|\n"

                for idx, row in bs_df.iterrows():
                    label = str(idx[1]) if isinstance(idx, tuple) else str(idx)
                    if any(key in label for key in key_items):
                        values = [str(v) for v in row.values[-3:]]
                        result += f"| {label} | " + " | ".join(values) + " |\n"

            result += f"\n*조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
            return result

        except Exception as e:
            return f"재무상태표 추출 실패: {e}"

    except Exception as e:
        return f"재무상태표 조회 실패: {e}"


def get_korea_cashflow(
    ticker: Annotated[str, "종목코드 (예: 005930)"],
    freq: Annotated[str, "조회 주기: 'annual' 또는 'quarterly'"] = "annual",
    curr_date: Annotated[str, "기준일"] = None,
) -> str:
    """
    한국 기업 현금흐름표 조회
    """
    stock_code = normalize_stock_code(ticker)

    if not init_dart_api():
        return "DART API를 사용할 수 없습니다."

    try:
        corp_list = get_corp_list_cached()
        corp = corp_list.find_by_stock_code(stock_code)

        if not corp:
            return f"종목코드 '{stock_code}'에 해당하는 기업을 찾을 수 없습니다."

        report_tp = "annual" if freq == "annual" else "quarter"
        bgn_de = (datetime.now() - timedelta(days=1100)).strftime("%Y%m%d")

        try:
            fs = corp.extract_fs(
                bgn_de=bgn_de,
                fs_tp=('cf',),  # 현금흐름표만
                report_tp=report_tp,
                progressbar=False
            )

            if fs is None or fs.cf is None:
                return f"'{corp.corp_name}'의 현금흐름표를 찾을 수 없습니다."

            cf_df = fs.cf

            result = f"""## {corp.corp_name} ({stock_code}) 현금흐름표

### 주요 현금흐름 항목

"""
            if not cf_df.empty:
                key_items = ['영업활동', '투자활동', '재무활동', '현금및현금성자산']

                result += "| 항목 | " + " | ".join(cf_df.columns[-3:].astype(str)) + " |\n"
                result += "|------" + "|------" * len(cf_df.columns[-3:]) + "|\n"

                for idx, row in cf_df.iterrows():
                    label = str(idx[1]) if isinstance(idx, tuple) else str(idx)
                    if any(key in label for key in key_items):
                        values = [str(v) for v in row.values[-3:]]
                        result += f"| {label} | " + " | ".join(values) + " |\n"

            result += f"\n*조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
            return result

        except Exception as e:
            return f"현금흐름표 추출 실패: {e}"

    except Exception as e:
        return f"현금흐름표 조회 실패: {e}"


def get_korea_income_statement(
    ticker: Annotated[str, "종목코드 (예: 005930)"],
    freq: Annotated[str, "조회 주기: 'annual' 또는 'quarterly'"] = "annual",
    curr_date: Annotated[str, "기준일"] = None,
) -> str:
    """
    한국 기업 손익계산서 조회
    """
    stock_code = normalize_stock_code(ticker)

    if not init_dart_api():
        return "DART API를 사용할 수 없습니다."

    try:
        corp_list = get_corp_list_cached()
        corp = corp_list.find_by_stock_code(stock_code)

        if not corp:
            return f"종목코드 '{stock_code}'에 해당하는 기업을 찾을 수 없습니다."

        report_tp = "annual" if freq == "annual" else "quarter"
        bgn_de = (datetime.now() - timedelta(days=1100)).strftime("%Y%m%d")

        try:
            fs = corp.extract_fs(
                bgn_de=bgn_de,
                fs_tp=('is',),  # 손익계산서만
                report_tp=report_tp,
                progressbar=False
            )

            if fs is None:
                return f"'{corp.corp_name}'의 손익계산서를 찾을 수 없습니다."

            # is 또는 cis (포괄손익계산서) 확인
            is_df = fs.is_
            if is_df is None or is_df.empty:
                is_df = fs.cis if hasattr(fs, 'cis') else None

            if is_df is None or is_df.empty:
                return f"'{corp.corp_name}'의 손익계산서를 찾을 수 없습니다."

            result = f"""## {corp.corp_name} ({stock_code}) 손익계산서

### 주요 손익 항목

"""
            key_items = ['매출', '영업이익', '당기순이익', '법인세']

            result += "| 항목 | " + " | ".join(is_df.columns[-3:].astype(str)) + " |\n"
            result += "|------" + "|------" * len(is_df.columns[-3:]) + "|\n"

            for idx, row in is_df.iterrows():
                label = str(idx[1]) if isinstance(idx, tuple) else str(idx)
                if any(key in label for key in key_items):
                    values = [str(v) for v in row.values[-3:]]
                    result += f"| {label} | " + " | ".join(values) + " |\n"

            result += f"\n*조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
            return result

        except Exception as e:
            return f"손익계산서 추출 실패: {e}"

    except Exception as e:
        return f"손익계산서 조회 실패: {e}"


def get_korea_insider_transactions(
    ticker: Annotated[str, "종목코드 (예: 005930)"],
) -> str:
    """
    한국 기업 임원/대주주 지분 변동 공시 조회
    """
    stock_code = normalize_stock_code(ticker)

    if not init_dart_api():
        return "DART API를 사용할 수 없습니다."

    try:
        corp_list = get_corp_list_cached()
        corp = corp_list.find_by_stock_code(stock_code)

        if not corp:
            return f"종목코드 '{stock_code}'에 해당하는 기업을 찾을 수 없습니다."

        # 최근 90일간 주요사항보고서 조회
        bgn_de = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
        end_de = datetime.now().strftime("%Y%m%d")

        reports = corp.search_filings(
            bgn_de=bgn_de,
            end_de=end_de,
            pblntf_ty="B",  # 주요사항보고
            page_count=30
        )

        result = f"""## {corp.corp_name} ({stock_code}) 내부자 거래 및 주요 공시

### 최근 90일간 주요사항보고서

"""
        if reports and len(reports) > 0:
            result += "| 날짜 | 보고서명 |\n"
            result += "|------|----------|\n"

            for report in reports[:15]:  # 최대 15개
                rcept_dt = getattr(report, 'rcept_dt', 'N/A')
                report_nm = getattr(report, 'report_nm', 'N/A')
                result += f"| {rcept_dt} | {report_nm} |\n"
        else:
            result += "*최근 주요사항보고서가 없습니다.*\n"

        result += f"\n*조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
        return result

    except Exception as e:
        return f"내부자 거래 조회 실패: {e}"
