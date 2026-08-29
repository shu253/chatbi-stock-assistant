"""Qwen Agent assembly and Tavily MCP integration."""

from __future__ import annotations

import logging
import re
import shutil

import dashscope
from qwen_agent.agents import Assistant

from . import tools as registered_tools  # noqa: F401  # register Qwen tools on import
from .config import PROJECT_ROOT, get_settings
from .prompts import SYSTEM_PROMPT

LOGGER = logging.getLogger(__name__)
IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\([^)]+\)")


def _extract_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content
        )
    return str(content or "")


class StockQueryAssistant(Assistant):
    """Ensure table and image outputs from tools remain visible in the final answer."""

    def run(self, messages, lang: str = "zh", **kwargs):
        for response in super().run(messages, lang=lang, **kwargs):
            yield self._ensure_tool_outputs(response)

    @staticmethod
    def _ensure_tool_outputs(response):
        if not response or response[-1].get("role") != "assistant":
            return response
        final_message = dict(response[-1])
        final_text = _extract_text(final_message.get("content"))
        append_blocks: list[str] = []

        for message in response:
            if message.get("role") != "function":
                continue
            tool_text = _extract_text(message.get("content"))
            table_lines = [line for line in tool_text.splitlines() if line.strip().startswith("|")]
            if table_lines and "|" not in final_text:
                append_blocks.append("\n".join(table_lines))
            for image in IMAGE_PATTERN.findall(tool_text):
                if image not in final_text and image not in append_blocks:
                    append_blocks.append(image)

        if append_blocks:
            suffix = "\n\n" + "\n\n".join(append_blocks)
            if isinstance(final_message.get("content"), list):
                final_message["content"] = [*final_message["content"], {"text": suffix}]
            else:
                final_message["content"] = final_text + suffix
            response[-1] = final_message
        return response


def _build_function_list() -> list[object]:
    settings = get_settings()
    functions: list[object] = ["exc_sql", "arima_stock", "boll_detection"]
    if not settings.enable_web_search:
        LOGGER.info("Tavily 联网搜索已通过 CHATBI_ENABLE_WEB_SEARCH=false 关闭")
        return functions
    if not settings.tavily_api_key:
        raise RuntimeError("Tavily 已启用，但未配置 TAVILY_API_KEY")
    if not shutil.which("npx"):
        raise RuntimeError(
            "Tavily 已启用，但未找到 npx；请先安装 Node.js，或设置 CHATBI_ENABLE_WEB_SEARCH=false"
        )

    functions.append(
        {
            "mcpServers": {
                "tavily-mcp": {
                    "command": "npx",
                    "args": ["-y", "tavily-mcp@0.1.4"],
                    "env": {"TAVILY_API_KEY": settings.tavily_api_key},
                    "disabled": False,
                    "autoApprove": [],
                }
            }
        }
    )
    return functions


def create_agent() -> StockQueryAssistant:
    settings = get_settings()
    if not settings.dashscope_api_key:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY，请复制 .env.example 为 .env 后填写")
    if not settings.db_path.is_file():
        raise FileNotFoundError(
            f"数据库不存在：{settings.db_path}。请先运行 scripts/import_to_sqlite.py。"
        )

    dashscope.api_key = settings.dashscope_api_key
    dashscope.timeout = 30
    faq_path = PROJECT_ROOT / "knowledge" / "faq.txt"
    return StockQueryAssistant(
        llm={"model": settings.model, "timeout": 30, "retry_count": 3},
        name="证券 ChatBI 助手",
        description="证券行情查询、统计分析、ARIMA 价格预测与 BOLL 异常检测",
        system_message=SYSTEM_PROMPT,
        function_list=_build_function_list(),
        files=[str(faq_path)],
    )
