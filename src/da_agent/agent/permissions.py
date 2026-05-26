"""Permission handling.

The `can_use_tool` callback is the SDK's gate before a tool runs. We use it for one
thing that needs a human: when the agent finishes planning and calls `ExitPlanMode`,
we surface the plan for approval. Everything else is allowed (this is a trusted,
single-user local tool; all steps are still shown in the TUI for transparency).
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from claude_agent_sdk import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from .events import PlanDecision

# Called when a plan is approved, so the runner can relax the permission mode.
OnPlanApproved = Callable[[], Awaitable[None]]
AskPlan = Callable[[str], Awaitable[PlanDecision]]


def make_can_use_tool(ask_plan: AskPlan, on_approved: OnPlanApproved):
    async def can_use_tool(
        tool_name: str,
        tool_input: dict[str, Any],
        context: ToolPermissionContext,
    ):
        if tool_name == "ExitPlanMode":
            plan = tool_input.get("plan") or tool_input.get("plan_text") or ""
            decision = await ask_plan(plan)
            if decision.approved:
                await on_approved()
                return PermissionResultAllow()
            feedback = decision.feedback or "The user rejected the plan."
            return PermissionResultDeny(
                message=(
                    f"User did not approve the plan. Revise it based on this feedback "
                    f"and present an updated plan: {feedback}"
                ),
                interrupt=False,
            )
        return PermissionResultAllow()

    return can_use_tool
