from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news, get_global_news
from tradingagents.dataflows.config import get_config
from tradingagents.agents.prompts_ko import get_prompt, get_common_prefix


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        # 설정에서 프롬프트 언어 확인
        config = get_config()
        prompt_language = config.get("prompt_language", "en")

        tools = [
            get_news,
            get_global_news,
        ]

        # 한국어 또는 영어 프롬프트 선택
        ko_prompt = get_prompt("news_analyst", prompt_language)
        if ko_prompt:
            system_message = ko_prompt
        else:
            system_message = (
                "You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for company-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."
                + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            )

        # 공통 프롬프트 prefix
        common_prefix = get_common_prefix(prompt_language)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    common_prefix,
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node
