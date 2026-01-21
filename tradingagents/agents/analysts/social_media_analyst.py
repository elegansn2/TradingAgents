from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news
from tradingagents.dataflows.config import get_config
from tradingagents.agents.prompts_ko import get_prompt, get_common_prefix


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        # 설정에서 프롬프트 언어 확인
        config = get_config()
        prompt_language = config.get("prompt_language", "en")

        tools = [
            get_news,
        ]

        # 한국어 또는 영어 프롬프트 선택
        ko_prompt = get_prompt("social_media_analyst", prompt_language)
        if ko_prompt:
            system_message = ko_prompt
        else:
            system_message = (
                "You are a social media and company specific news researcher/analyst tasked with analyzing social media posts, recent company news, and public sentiment for a specific company over the past week. You will be given a company's name your objective is to write a comprehensive long report detailing your analysis, insights, and implications for traders and investors on this company's current state after looking at social media and what people are saying about that company, analyzing sentiment data of what people feel each day about the company, and looking at recent company news. Use the get_news(query, start_date, end_date) tool to search for company-specific news and social media discussions. Try to look at all sources possible from social media to sentiment to news. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."
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
            "sentiment_report": report,
        }

    return social_media_analyst_node
