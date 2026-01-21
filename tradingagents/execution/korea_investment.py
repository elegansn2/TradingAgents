"""
한국투자증권 OpenAPI 연동 모듈

모의투자 및 실전투자 주문 실행을 위한 API 클라이언트
참고: https://github.com/koreainvestment/open-trading-api

API 속도 제한:
- 모의투자: 초당 5건 (250ms 간격)
- 실전투자: 초당 20건 (67ms 간격)
- 슬라이딩 윈도우 방식으로 제한
- 에러 코드: EGW00201 (초당 거래건수 초과)
"""

import os
import json
import requests
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from collections import deque

from tradingagents.dataflows.config import get_config


class RateLimiter:
    """
    슬라이딩 윈도우 기반 API 속도 제한기

    한국투자증권 API는 슬라이딩 윈도우 방식으로 초당 요청 수를 제한합니다.
    - 모의투자: 5 calls/sec
    - 실전투자: 20 calls/sec
    """

    def __init__(self, max_calls: int = 5, period: float = 1.0):
        """
        Args:
            max_calls: 기간 내 최대 호출 수
            period: 제한 기간 (초)
        """
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()
        self.lock = threading.Lock()

    def wait(self):
        """
        API 호출 전 필요시 대기

        슬라이딩 윈도우 내 호출 수가 제한에 도달하면
        가장 오래된 호출이 윈도우를 벗어날 때까지 대기
        """
        with self.lock:
            now = time.time()

            # 만료된 호출 기록 제거
            while self.calls and self.calls[0] <= now - self.period:
                self.calls.popleft()

            # 제한에 도달한 경우 대기
            if len(self.calls) >= self.max_calls:
                sleep_time = self.calls[0] - (now - self.period) + 0.05  # 50ms 여유
                if sleep_time > 0:
                    time.sleep(sleep_time)
                # 다시 만료된 기록 제거
                now = time.time()
                while self.calls and self.calls[0] <= now - self.period:
                    self.calls.popleft()

            # 현재 호출 기록
            self.calls.append(time.time())

    def get_status(self) -> Dict[str, Any]:
        """현재 속도 제한 상태 반환"""
        with self.lock:
            now = time.time()
            # 만료된 호출 기록 제거
            while self.calls and self.calls[0] <= now - self.period:
                self.calls.popleft()

            return {
                "current_calls": len(self.calls),
                "max_calls": self.max_calls,
                "period": self.period,
                "available": self.max_calls - len(self.calls),
            }


class KoreaInvestmentExecutor:
    """
    한국투자증권 OpenAPI 실행기

    모의투자(paper) 또는 실전투자(live) 모드로 주문 실행
    """

    # API 엔드포인트
    BASE_URL_PAPER = "https://openapivts.koreainvestment.com:29443"  # 모의투자
    BASE_URL_LIVE = "https://openapi.koreainvestment.com:9443"       # 실전투자

    # 속도 제한 설정
    RATE_LIMIT_PAPER = 4   # 모의투자: 초당 4건 (여유분 포함, 공식 5건)
    RATE_LIMIT_LIVE = 15   # 실전투자: 초당 15건 (여유분 포함, 공식 20건)

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
            self.rate_limiter = RateLimiter(max_calls=self.RATE_LIMIT_PAPER, period=1.0)
        else:
            self.base_url = self.BASE_URL_LIVE
            self.app_key = self.config.get("kis_app_key_live") or os.getenv("KIS_APP_KEY_LIVE")
            self.app_secret = self.config.get("kis_app_secret_live") or os.getenv("KIS_APP_SECRET_LIVE")
            self.account = self.config.get("kis_account_live") or os.getenv("KIS_ACCOUNT_LIVE")
            self.rate_limiter = RateLimiter(max_calls=self.RATE_LIMIT_LIVE, period=1.0)

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

    def _api_call(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        API 호출 (속도 제한 적용)

        Args:
            method: HTTP 메서드 ("get" 또는 "post")
            url: API URL
            **kwargs: requests 인자

        Returns:
            Response 객체
        """
        # 속도 제한 대기
        self.rate_limiter.wait()

        if method.lower() == "get":
            return requests.get(url, **kwargs)
        elif method.lower() == "post":
            return requests.post(url, **kwargs)
        else:
            raise ValueError(f"Unknown HTTP method: {method}")

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
        response = self._api_call("post", url, headers=headers, json=data)
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

        response = self._api_call("post", url, json=data)

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

        response = self._api_call("get", url, headers=headers, params=params)

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

        response = self._api_call("get", url, headers=headers, params=params)

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

        response = self._api_call("get", url, headers=headers, params=params)

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

        response = self._api_call("post", url, headers=headers, json=data)

        if response.status_code == 200:
            result = response.json()

            # API 응답 확인
            if result.get("rt_cd") == "0":
                return {
                    "status": "success",
                    "order_type": order_type,
                    "ticker": ticker,
                    "quantity": quantity,
                    "price": price,
                    "order_no": result.get("output", {}).get("ODNO"),
                    "response": result,
                }
            else:
                return {
                    "status": "failed",
                    "error": result.get("msg1", "Unknown error"),
                    "error_code": result.get("msg_cd"),
                    "ticker": ticker,
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

            # 안전한 숫자 변환
            def safe_int(value, default=0):
                try:
                    # 소수점이 있는 문자열 처리
                    return int(float(value)) if value else default
                except (ValueError, TypeError):
                    return default

            result = f"""## 포트폴리오 현황

### 계좌 요약
| 항목 | 금액 |
|------|------|
| 예수금 | {safe_int(summary.get('dnca_tot_amt')):,}원 |
| 평가금액 | {safe_int(summary.get('scts_evlu_amt')):,}원 |
| 총 평가손익 | {safe_int(summary.get('evlu_pfls_smtl_amt')):,}원 |

### 보유 종목
| 종목코드 | 종목명 | 수량 | 평균단가 | 현재가 | 평가손익 |
|---------|--------|------|---------|--------|---------|
"""
            for item in holdings:
                if safe_int(item.get("hldg_qty")) > 0:
                    result += f"| {item.get('pdno')} | {item.get('prdt_name')} | {item.get('hldg_qty')} | {safe_int(item.get('pchs_avg_pric')):,} | {safe_int(item.get('prpr')):,} | {safe_int(item.get('evlu_pfls_amt')):,} |\n"

            result += f"\n*모드: {'모의투자' if self.mode == 'paper' else '실전투자'}*"
            result += f"\n*조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
            result += f"\n*API 상태: {self.rate_limiter.get_status()}*"

            return result

        except Exception as e:
            return f"포트폴리오 조회 실패: {e}"

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """현재 API 속도 제한 상태 반환"""
        return {
            "mode": self.mode,
            "max_calls_per_second": self.RATE_LIMIT_PAPER if self.mode == "paper" else self.RATE_LIMIT_LIVE,
            **self.rate_limiter.get_status()
        }

    def check_positions(
        self,
        stop_loss_pct: float = -5.0,
        take_profit_pct: float = 10.0,
    ) -> list[Dict[str, Any]]:
        """
        보유 종목의 손절/익절 조건 확인

        Args:
            stop_loss_pct: 손절 기준 수익률 (%, 음수) - 기본값 -5%
            take_profit_pct: 익절 기준 수익률 (%) - 기본값 +10%

        Returns:
            각 종목의 상태 및 액션 리스트
        """
        try:
            balance = self.get_balance()
            holdings = balance.get("output1", [])

            results = []

            for item in holdings:
                qty = int(item.get("hldg_qty", 0))
                if qty <= 0:
                    continue

                ticker = item.get("pdno", "")
                name = item.get("prdt_name", "")
                avg_price = float(item.get("pchs_avg_pric", 0))
                current_price = float(item.get("prpr", 0))
                profit_loss = float(item.get("evlu_pfls_amt", 0))

                # 수익률 계산
                if avg_price > 0:
                    profit_rate = ((current_price - avg_price) / avg_price) * 100
                else:
                    profit_rate = 0.0

                # 액션 결정
                action = "HOLD"
                reason = ""

                if profit_rate <= stop_loss_pct:
                    action = "SELL"
                    reason = f"손절 ({profit_rate:.2f}% <= {stop_loss_pct}%)"
                elif profit_rate >= take_profit_pct:
                    action = "SELL"
                    reason = f"익절 ({profit_rate:.2f}% >= {take_profit_pct}%)"
                else:
                    reason = f"보유 유지 ({stop_loss_pct}% < {profit_rate:.2f}% < {take_profit_pct}%)"

                results.append({
                    "ticker": ticker,
                    "name": name,
                    "quantity": qty,
                    "avg_price": int(avg_price),
                    "current_price": int(current_price),
                    "profit_loss": int(profit_loss),
                    "profit_rate": round(profit_rate, 2),
                    "action": action,
                    "reason": reason,
                })

            return results

        except Exception as e:
            return [{"error": str(e)}]

    def execute_stop_loss_take_profit(
        self,
        stop_loss_pct: float = -5.0,
        take_profit_pct: float = 10.0,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """
        손절/익절 전략 실행

        Args:
            stop_loss_pct: 손절 기준 수익률 (%, 음수) - 기본값 -5%
            take_profit_pct: 익절 기준 수익률 (%) - 기본값 +10%
            dry_run: True면 시뮬레이션만, False면 실제 매도 실행

        Returns:
            실행 결과
        """
        positions = self.check_positions(stop_loss_pct, take_profit_pct)

        if not positions or "error" in positions[0]:
            return {
                "status": "error",
                "message": "포지션 조회 실패",
                "positions": positions,
            }

        sell_targets = [p for p in positions if p.get("action") == "SELL"]
        hold_targets = [p for p in positions if p.get("action") == "HOLD"]

        results = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "dry_run": dry_run,
            "total_positions": len(positions),
            "sell_targets": len(sell_targets),
            "hold_targets": len(hold_targets),
            "positions": positions,
            "executed_orders": [],
        }

        if dry_run:
            results["message"] = "시뮬레이션 모드 - 실제 주문 없음"
            return results

        # 실제 매도 실행
        for target in sell_targets:
            ticker = target["ticker"]
            quantity = target["quantity"]

            order_result = self.place_order(ticker, "sell", quantity, price=0)

            results["executed_orders"].append({
                "ticker": ticker,
                "name": target["name"],
                "quantity": quantity,
                "reason": target["reason"],
                "order_result": order_result,
            })

        results["message"] = f"{len(sell_targets)}개 종목 매도 주문 실행 완료"
        return results

    def monitor_positions(
        self,
        stop_loss_pct: float = -5.0,
        take_profit_pct: float = 10.0,
        interval_seconds: int = 60,
        max_iterations: int = 0,
        auto_execute: bool = False,
        callback: callable = None,
    ):
        """
        포지션 모니터링 루프

        Args:
            stop_loss_pct: 손절 기준 수익률 (%)
            take_profit_pct: 익절 기준 수익률 (%)
            interval_seconds: 체크 간격 (초)
            max_iterations: 최대 반복 횟수 (0이면 무한)
            auto_execute: True면 자동 매도, False면 알림만
            callback: 매도 조건 충족 시 호출할 함수 (positions를 인자로 받음)

        Note:
            이 함수는 블로킹 함수입니다. 별도 스레드에서 실행하세요.
        """
        iteration = 0

        print(f"\n{'='*60}")
        print(f"포지션 모니터링 시작")
        print(f"손절: {stop_loss_pct}% | 익절: {take_profit_pct}%")
        print(f"체크 간격: {interval_seconds}초 | 자동 매도: {auto_execute}")
        print(f"{'='*60}\n")

        while max_iterations == 0 or iteration < max_iterations:
            iteration += 1

            try:
                positions = self.check_positions(stop_loss_pct, take_profit_pct)

                sell_targets = [p for p in positions if p.get("action") == "SELL"]

                # 상태 출력
                now = datetime.now().strftime("%H:%M:%S")
                print(f"[{now}] 체크 #{iteration}: {len(positions)}개 종목, 매도 대상 {len(sell_targets)}개")

                for p in positions:
                    status_icon = "🔴" if p.get("action") == "SELL" else "🟢"
                    print(f"  {status_icon} {p.get('name', 'N/A')} ({p.get('ticker')}): "
                          f"{p.get('profit_rate', 0):+.2f}% | {p.get('reason', '')}")

                # 매도 대상이 있을 경우
                if sell_targets:
                    if callback:
                        callback(sell_targets)

                    if auto_execute:
                        print(f"\n⚠️  자동 매도 실행 중...")
                        for target in sell_targets:
                            result = self.place_order(
                                target["ticker"],
                                "sell",
                                target["quantity"],
                                price=0
                            )
                            status = "✅" if result.get("status") == "success" else "❌"
                            print(f"  {status} {target['name']}: {result.get('status')} - {result.get('error', result.get('order_no', ''))}")

            except Exception as e:
                print(f"[ERROR] 모니터링 에러: {e}")

            # 대기
            if max_iterations == 0 or iteration < max_iterations:
                time.sleep(interval_seconds)

        print(f"\n모니터링 종료 (총 {iteration}회 체크)")

    def get_position_summary(
        self,
        stop_loss_pct: float = -5.0,
        take_profit_pct: float = 10.0,
    ) -> str:
        """
        포지션 요약 문자열 반환 (손절/익절 상태 포함)
        """
        positions = self.check_positions(stop_loss_pct, take_profit_pct)

        if not positions or "error" in positions[0]:
            return f"포지션 조회 실패: {positions}"

        result = f"""## 포지션 모니터링 현황

### 설정
| 항목 | 값 |
|------|-----|
| 손절 기준 | {stop_loss_pct}% |
| 익절 기준 | {take_profit_pct}% |
| 모드 | {'모의투자' if self.mode == 'paper' else '실전투자'} |

### 보유 종목 현황
| 종목 | 수량 | 평균단가 | 현재가 | 수익률 | 상태 |
|------|------|---------|--------|--------|------|
"""
        total_profit_loss = 0
        for p in positions:
            if "error" not in p:
                status_icon = "🔴 매도" if p.get("action") == "SELL" else "🟢 보유"
                result += f"| {p.get('name', 'N/A')} | {p.get('quantity')} | {p.get('avg_price', 0):,} | {p.get('current_price', 0):,} | {p.get('profit_rate', 0):+.2f}% | {status_icon} |\n"
                total_profit_loss += p.get("profit_loss", 0)

        sell_count = len([p for p in positions if p.get("action") == "SELL"])

        result += f"""
### 요약
- 총 보유 종목: {len(positions)}개
- 매도 대상: {sell_count}개
- 총 평가손익: {total_profit_loss:,}원

*조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        return result
