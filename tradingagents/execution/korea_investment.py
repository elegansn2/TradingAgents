"""
한국투자증권 OpenAPI 연동 모듈

모의투자 및 실전투자 주문 실행을 위한 API 클라이언트
참고: https://github.com/koreainvestment/open-trading-api
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import hashlib

from tradingagents.dataflows.config import get_config


class KoreaInvestmentExecutor:
    """
    한국투자증권 OpenAPI 실행기

    모의투자(paper) 또는 실전투자(live) 모드로 주문 실행
    """

    # API 엔드포인트
    BASE_URL_PAPER = "https://openapivts.koreainvestment.com:29443"  # 모의투자
    BASE_URL_LIVE = "https://openapi.koreainvestment.com:9443"       # 실전투자

    def __init__(self, config: Dict[str, Any] = None):
        """
        초기화

        Args:
            config: 설정 딕셔너리 (None이면 KOREA_CONFIG 사용)
        """
        self.config = config or get_config()
        self.mode = self.config.get("kis_mode", "paper")

        # 모드에 따른 설정 로드
        if self.mode == "paper":
            self.base_url = self.BASE_URL_PAPER
            self.app_key = self.config.get("kis_app_key_paper") or os.getenv("KIS_APP_KEY_PAPER")
            self.app_secret = self.config.get("kis_app_secret_paper") or os.getenv("KIS_APP_SECRET_PAPER")
            self.account = self.config.get("kis_account_paper") or os.getenv("KIS_ACCOUNT_PAPER")
        else:
            self.base_url = self.BASE_URL_LIVE
            self.app_key = self.config.get("kis_app_key_live") or os.getenv("KIS_APP_KEY_LIVE")
            self.app_secret = self.config.get("kis_app_secret_live") or os.getenv("KIS_APP_SECRET_LIVE")
            self.account = self.config.get("kis_account_live") or os.getenv("KIS_ACCOUNT_LIVE")

        # 계좌번호 파싱 (XXXXXXXX-XX 형식)
        if self.account and "-" in self.account:
            self.account_prefix = self.account.split("-")[0]
            self.account_suffix = self.account.split("-")[1]
        else:
            self.account_prefix = self.account[:8] if self.account else ""
            self.account_suffix = self.account[8:10] if self.account and len(self.account) >= 10 else "01"

        # 액세스 토큰
        self.access_token = None
        self.token_expires_at = None

        # 초기화 확인
        self._validate_config()

    def _validate_config(self):
        """설정 유효성 검증"""
        if not self.app_key:
            print(f"Warning: KIS_APP_KEY_{self.mode.upper()} not set")
        if not self.app_secret:
            print(f"Warning: KIS_APP_SECRET_{self.mode.upper()} not set")
        if not self.account:
            print(f"Warning: KIS_ACCOUNT_{self.mode.upper()} not set")

    def _get_headers(self, tr_id: str, hashkey: str = None) -> Dict[str, str]:
        """API 요청 헤더 생성"""
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }
        if hashkey:
            headers["hashkey"] = hashkey
        return headers

    def _get_hashkey(self, data: Dict) -> str:
        """Hashkey 생성 (주문 API용)"""
        url = f"{self.base_url}/uapi/hashkey"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json().get("HASH", "")
        return ""

    def get_access_token(self) -> str:
        """
        액세스 토큰 발급

        토큰은 24시간 유효하며, 만료 전 자동 갱신
        """
        # 토큰이 유효한지 확인
        if self.access_token and self.token_expires_at:
            if datetime.now() < self.token_expires_at - timedelta(hours=1):
                return self.access_token

        url = f"{self.base_url}/oauth2/tokenP"
        data = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }

        response = requests.post(url, json=data)

        if response.status_code == 200:
            result = response.json()
            self.access_token = result.get("access_token")
            # 토큰 만료 시간 설정 (24시간)
            self.token_expires_at = datetime.now() + timedelta(hours=23)
            return self.access_token
        else:
            raise Exception(f"토큰 발급 실패: {response.text}")

    def get_current_price(self, ticker: str) -> Dict[str, Any]:
        """
        현재가 조회

        Args:
            ticker: 종목코드 (6자리)

        Returns:
            현재가 정보 딕셔너리
        """
        self.get_access_token()

        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"

        # 모의투자/실전투자에 따른 tr_id
        tr_id = "FHKST01010100"

        headers = self._get_headers(tr_id)
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker.zfill(6),
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"현재가 조회 실패: {response.text}")

    def get_balance(self) -> Dict[str, Any]:
        """
        계좌 잔고 조회

        Returns:
            잔고 정보 딕셔너리
        """
        self.get_access_token()

        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"

        # 모의투자/실전투자에 따른 tr_id
        tr_id = "VTTC8434R" if self.mode == "paper" else "TTTC8434R"

        headers = self._get_headers(tr_id)
        params = {
            "CANO": self.account_prefix,
            "ACNT_PRDT_CD": self.account_suffix,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"잔고 조회 실패: {response.text}")

    def get_buyable_amount(self, ticker: str, price: int = 0) -> Dict[str, Any]:
        """
        매수 가능 금액/수량 조회

        Args:
            ticker: 종목코드
            price: 주문 가격 (0이면 시장가)

        Returns:
            매수 가능 정보
        """
        self.get_access_token()

        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-psbl-order"

        tr_id = "VTTC8908R" if self.mode == "paper" else "TTTC8908R"

        headers = self._get_headers(tr_id)
        params = {
            "CANO": self.account_prefix,
            "ACNT_PRDT_CD": self.account_suffix,
            "PDNO": ticker.zfill(6),
            "ORD_UNPR": str(price),
            "ORD_DVSN": "01" if price == 0 else "00",  # 01: 시장가, 00: 지정가
            "CMA_EVLU_AMT_ICLD_YN": "N",
            "OVRS_ICLD_YN": "N",
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"매수 가능 조회 실패: {response.text}")

    def place_order(
        self,
        ticker: str,
        order_type: str,
        quantity: int,
        price: int = 0,
    ) -> Dict[str, Any]:
        """
        주문 실행

        Args:
            ticker: 종목코드 (6자리)
            order_type: "buy" 또는 "sell"
            quantity: 주문 수량
            price: 주문 가격 (0이면 시장가)

        Returns:
            주문 결과 딕셔너리
        """
        self.get_access_token()

        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"

        # tr_id 설정
        if self.mode == "paper":
            tr_id = "VTTC0802U" if order_type == "buy" else "VTTC0801U"
        else:
            tr_id = "TTTC0802U" if order_type == "buy" else "TTTC0801U"

        # 주문 데이터
        data = {
            "CANO": self.account_prefix,
            "ACNT_PRDT_CD": self.account_suffix,
            "PDNO": ticker.zfill(6),
            "ORD_DVSN": "01" if price == 0 else "00",  # 01: 시장가, 00: 지정가
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price),
        }

        # Hashkey 생성
        hashkey = self._get_hashkey(data)
        headers = self._get_headers(tr_id, hashkey)

        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 200:
            result = response.json()
            return {
                "status": "success",
                "order_type": order_type,
                "ticker": ticker,
                "quantity": quantity,
                "price": price,
                "response": result,
            }
        else:
            return {
                "status": "failed",
                "error": response.text,
            }

    def execute(
        self,
        ticker: str,
        decision: str,
        quantity: int = 0,
        price: int = 0,
    ) -> Dict[str, Any]:
        """
        TradingAgents 결정에 따른 거래 실행

        Args:
            ticker: 종목코드
            decision: "BUY", "SELL", "HOLD"
            quantity: 주문 수량 (0이면 자동 계산)
            price: 주문 가격 (0이면 시장가)

        Returns:
            실행 결과
        """
        decision = decision.upper()

        if decision == "HOLD":
            return {
                "status": "HOLD",
                "message": "거래 보류 (HOLD)",
                "ticker": ticker,
            }

        try:
            # 현재가 조회
            price_info = self.get_current_price(ticker)
            current_price = int(price_info.get("output", {}).get("stck_prpr", 0))

            if decision == "BUY":
                if quantity == 0:
                    # 매수 가능 금액으로 수량 자동 계산
                    buyable = self.get_buyable_amount(ticker)
                    max_qty = int(buyable.get("output", {}).get("nrcvb_buy_qty", 0))
                    quantity = min(max_qty, 10)  # 최대 10주로 제한 (테스트용)

                if quantity > 0:
                    result = self.place_order(ticker, "buy", quantity, price)
                    result["current_price"] = current_price
                    result["decision"] = "BUY"
                    return result
                else:
                    return {
                        "status": "failed",
                        "error": "매수 가능 수량이 없습니다.",
                        "ticker": ticker,
                    }

            elif decision == "SELL":
                if quantity == 0:
                    # 보유 수량 조회
                    balance = self.get_balance()
                    holdings = balance.get("output1", [])
                    for item in holdings:
                        if item.get("pdno") == ticker.zfill(6):
                            quantity = int(item.get("hldg_qty", 0))
                            break

                if quantity > 0:
                    result = self.place_order(ticker, "sell", quantity, price)
                    result["current_price"] = current_price
                    result["decision"] = "SELL"
                    return result
                else:
                    return {
                        "status": "failed",
                        "error": "매도 가능 수량이 없습니다.",
                        "ticker": ticker,
                    }

        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
                "ticker": ticker,
                "decision": decision,
            }

        return {
            "status": "failed",
            "error": f"알 수 없는 결정: {decision}",
        }

    def get_portfolio_summary(self) -> str:
        """
        포트폴리오 요약 문자열 반환
        """
        try:
            balance = self.get_balance()
            holdings = balance.get("output1", [])
            summary = balance.get("output2", [{}])[0] if balance.get("output2") else {}

            result = f"""## 포트폴리오 현황

### 계좌 요약
| 항목 | 금액 |
|------|------|
| 예수금 | {int(summary.get('dnca_tot_amt', 0)):,}원 |
| 평가금액 | {int(summary.get('scts_evlu_amt', 0)):,}원 |
| 총 평가손익 | {int(summary.get('evlu_pfls_smtl_amt', 0)):,}원 |

### 보유 종목
| 종목코드 | 종목명 | 수량 | 평균단가 | 현재가 | 평가손익 |
|---------|--------|------|---------|--------|---------|
"""
            for item in holdings:
                if int(item.get("hldg_qty", 0)) > 0:
                    result += f"| {item.get('pdno')} | {item.get('prdt_name')} | {item.get('hldg_qty')} | {int(item.get('pchs_avg_pric', 0)):,} | {int(item.get('prpr', 0)):,} | {int(item.get('evlu_pfls_amt', 0)):,} |\n"

            result += f"\n*모드: {'모의투자' if self.mode == 'paper' else '실전투자'}*"
            result += f"\n*조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"

            return result

        except Exception as e:
            return f"포트폴리오 조회 실패: {e}"
