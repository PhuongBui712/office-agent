"""The `ask_user_question` tool.

Implemented as an in-process SDK MCP tool rather than relying on the built-in
client-side tool, so we fully own the round-trip: when the model calls it, our handler
drives the UI's interactive picker and returns the user's selections as the tool result.

The tool is bound to a UI *provider* (a zero-arg callable) instead of a fixed UI
instance, so the same server definition works if the active UI is swapped (e.g. CLI
vs. a web session) without rebuilding the agent.
"""
from __future__ import annotations

from typing import Any, Callable

from claude_agent_sdk import create_sdk_mcp_server, tool

from ..ui.base import AgentUI
from .events import QuestionRequest

SERVER_NAME = "interaction"
TOOL_NAME = "ask_user_question"
QUALIFIED_TOOL_NAME = f"mcp__{SERVER_NAME}__{TOOL_NAME}"

_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "description": "1-4 related questions to ask the user at once.",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question text."},
                    "header": {
                        "type": "string",
                        "description": "Very short label (<=12 chars) used as the tab title.",
                    },
                    "multiSelect": {
                        "type": "boolean",
                        "description": "Allow selecting more than one option.",
                    },
                    "allowOther": {
                        "type": "boolean",
                        "description": "Offer a free-text 'Type something' option.",
                    },
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": ["label"],
                        },
                    },
                },
                "required": ["question", "header", "options"],
            },
        }
    },
    "required": ["questions"],
}


def build_ask_tool(ui_provider: Callable[[], AgentUI]):
    """Return the `ask_user_question` SdkMcpTool bound to a UI provider."""

    @tool(
        TOOL_NAME,
        "Ask the user one or more multiple-choice questions to clarify requirements "
        "(e.g. where output should go) before proceeding. Returns the user's selections.",
        _INPUT_SCHEMA,
    )
    async def ask_user_question(args: dict[str, Any]) -> dict[str, Any]:
        request = QuestionRequest.from_tool_input(args)
        response = await ui_provider().ask_question(request)
        return {"content": [{"type": "text", "text": response.to_model_text()}]}

    return ask_user_question


def build_interaction_server(ui_provider: Callable[[], AgentUI]):
    """Return an McpSdkServerConfig exposing `ask_user_question`."""
    return create_sdk_mcp_server(SERVER_NAME, "1.0.0", [build_ask_tool(ui_provider)])
