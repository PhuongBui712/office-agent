"""Permission handling.

The `can_use_tool` callback is the SDK's gate before a tool runs. We use it for the
two built-in tools that need a human:

- **AskUserQuestion**: the model surfaces a multiple-choice question; we drive our own
  UI, then return the user's selections to the model via `updated_input.answers`.
- **ExitPlanMode**: when the agent finishes planning we surface the plan for approval
  and, on accept, relax the permission mode.

Everything else is allowed (this is a trusted, single-user local tool; all steps are
still shown in the TUI for transparency).
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from claude_agent_sdk import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from .events import PlanDecision, QuestionRequest, QuestionResponse

# Called when a plan is approved, so the runner can relax the permission mode.
OnPlanApproved = Callable[[], Awaitable[None]]
AskPlan = Callable[[str], Awaitable[PlanDecision]]
AskQuestion = Callable[[QuestionRequest], Awaitable[QuestionResponse]]


def make_can_use_tool(
    ask_plan: AskPlan,
    on_approved: OnPlanApproved,
    ask_question: AskQuestion,
):
    async def can_use_tool(
        tool_name: str,
        tool_input: dict[str, Any],
        context: ToolPermissionContext,
    ):
        if tool_name == "AskUserQuestion":
            return await _handle_ask_user_question(tool_input, ask_question)
        if tool_name == "ExitPlanMode":
            return await _handle_exit_plan_mode(tool_input, ask_plan, on_approved)
        return PermissionResultAllow()

    return can_use_tool


async def _handle_ask_user_question(
    tool_input: dict[str, Any],
    ask_question: AskQuestion,
) -> PermissionResultAllow:
    """Drive the UI for the model's questions and return answers via `updated_input`.

    The built-in AskUserQuestion tool reads `updated_input.answers` (a mapping of
    question text -> selected label string) as the user's response, so the SDK can
    short-circuit its own prompt and pass the answer straight to the model.
    """
    raw_questions = list(tool_input.get("questions") or [])
    request = QuestionRequest.from_tool_input(tool_input)
    response = await ask_question(request)

    answers: dict[str, str] = {}
    for i, q_dict in enumerate(raw_questions):
        key = q_dict.get("question") or q_dict.get("header") or f"Q{i + 1}"
        if i < len(response.answers):
            ans = response.answers[i]
            answers[key] = ", ".join(ans.values())
        else:
            answers[key] = ""

    return PermissionResultAllow(
        updated_input={"questions": raw_questions, "answers": answers}
    )


async def _handle_exit_plan_mode(
    tool_input: dict[str, Any],
    ask_plan: AskPlan,
    on_approved: OnPlanApproved,
):
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
