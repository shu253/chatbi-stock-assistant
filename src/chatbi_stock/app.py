"""Command-line and WebUI entry points."""

from __future__ import annotations

import argparse
import logging

from .agent import create_agent
from .config import get_settings


def run_cli() -> None:
    bot = create_agent()
    messages: list[dict[str, str]] = []
    print("证券 ChatBI 助手已启动。输入 quit 或 exit 退出。")
    while True:
        query = input("\n用户：").strip()
        if query.lower() in {"quit", "exit"}:
            return
        if not query:
            continue
        messages.append({"role": "user", "content": query})
        final_response = []
        for candidate in bot.run(messages):
            final_response = candidate
        if final_response:
            print("助手：", final_response[-1].get("content", ""))
            messages.extend(final_response)


def run_web() -> None:
    from qwen_agent.gui import WebUI

    bot = create_agent()
    config = {
        "prompt.suggestions": [
            "查询2025年全年上海九百的收盘价走势",
            "对比贵州茅台与五粮液2025年的涨跌幅",
            "使用ARIMA预测贵州茅台未来5个工作日的价格",
            "检测五粮液过去一年的BOLL上下轨突破",
        ]
    }
    WebUI(bot, chatbot_config=config).run()


def main() -> None:
    parser = argparse.ArgumentParser(description="证券 ChatBI 助手")
    parser.add_argument("--mode", choices=("web", "cli"), default="web")
    args = parser.parse_args()
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.mode == "cli":
        run_cli()
    else:
        run_web()


if __name__ == "__main__":
    main()
