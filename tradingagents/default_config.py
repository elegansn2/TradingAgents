import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# ===========================================
# 기본 설정 (US 시장)
# ===========================================
DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_dir": "/Users/yluo/Documents/Code/ScAI/FR1-data",
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "o4-mini",
    "quick_think_llm": "gpt-4o-mini",
    "backend_url": "https://api.openai.com/v1",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: yfinance, alpha_vantage, local
        "technical_indicators": "yfinance",  # Options: yfinance, alpha_vantage, local
        "fundamental_data": "alpha_vantage", # Options: openai, alpha_vantage, local
        "news_data": "alpha_vantage",        # Options: openai, alpha_vantage, google, local
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
        # Example: "get_news": "openai",               # Override category default
    },
}

# ===========================================
# 한국 시장 설정
# ===========================================
KOREA_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),

    # 시장 설정
    "market": "korea",
    "market_timezone": "Asia/Seoul",

    # LLM 설정 (Google Gemini)
    "llm_provider": "google",
    "deep_think_llm": "gemini-2.5-flash",
    "quick_think_llm": "gemini-2.0-flash",
    "backend_url": None,  # Google Gemini는 backend_url 불필요

    # 토론 설정
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,

    # 한국 데이터 소스 설정
    "data_vendors": {
        "core_stock_apis": "korea",          # Options: korea, yfinance
        "technical_indicators": "korea",     # Options: korea, yfinance
        "fundamental_data": "korea_dart",    # Options: korea_dart
        "news_data": "korea_naver",          # Options: korea_naver
    },

    "tool_vendors": {},

    # 프롬프트 언어 설정
    "prompt_language": "ko",  # "ko" = 한국어, "en" = 영어

    # ===========================================
    # 한국투자증권 OpenAPI 설정
    # ===========================================
    "kis_mode": os.getenv("KIS_MODE", "paper"),  # "paper" = 모의투자, "live" = 실전

    # 모의투자 계정
    "kis_app_key_paper": os.getenv("KIS_APP_KEY_PAPER"),
    "kis_app_secret_paper": os.getenv("KIS_APP_SECRET_PAPER"),
    "kis_account_paper": os.getenv("KIS_ACCOUNT_PAPER"),

    # 실전투자 계정
    "kis_app_key_live": os.getenv("KIS_APP_KEY_LIVE"),
    "kis_app_secret_live": os.getenv("KIS_APP_SECRET_LIVE"),
    "kis_account_live": os.getenv("KIS_ACCOUNT_LIVE"),

    # DART API 설정
    "dart_api_key": os.getenv("DART_API_KEY"),
}


def get_korea_config():
    """한국 시장용 설정 반환"""
    return KOREA_CONFIG.copy()


def get_config(market: str = "us"):
    """
    시장에 따른 설정 반환

    Args:
        market: "us" (기본값) 또는 "korea"

    Returns:
        해당 시장의 설정 딕셔너리
    """
    if market == "korea":
        return get_korea_config()
    return DEFAULT_CONFIG.copy()
