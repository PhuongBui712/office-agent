"""Structured payloads exchanged between the agent and the UI layer.

These are deliberately serializable plain dataclasses so the same shapes can flow
over a websocket to a web frontend later, not just to the CLI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# --------------------------------------------------------------------------- #
# AskUserQuestion
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Option:
    label: str
    description: str = ""


@dataclass(slots=True)
class Question:
    question: str
    header: str  # short label shown as the tab (e.g. "Role", "Output")
    options: list[Option]
    multi_select: bool = False
    allow_other: bool = True  # offer a free-text "Type something" choice

    @classmethod
    def from_dict(cls, d: dict) -> "Question":
        return cls(
            question=d["question"],
            header=d.get("header") or d["question"][:16],
            options=[Option(o["label"], o.get("description", "")) for o in d.get("options", [])],
            multi_select=bool(d.get("multiSelect", False)),
            allow_other=bool(d.get("allowOther", True)),
        )


@dataclass(slots=True)
class QuestionRequest:
    questions: list[Question]

    @classmethod
    def from_tool_input(cls, args: dict) -> "QuestionRequest":
        return cls(questions=[Question.from_dict(q) for q in args.get("questions", [])])


@dataclass(slots=True)
class Answer:
    header: str
    selected: list[str] = field(default_factory=list)
    other_text: str | None = None

    def values(self) -> list[str]:
        out = list(self.selected)
        if self.other_text:
            out.append(self.other_text)
        return out


@dataclass(slots=True)
class QuestionResponse:
    answers: list[Answer]

    def to_model_text(self) -> str:
        """Render the user's choices as the tool result the model reads back."""
        lines = []
        for a in self.answers:
            vals = ", ".join(a.values()) or "(no selection)"
            lines.append(f"{a.header}: {vals}")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Plan approval
# --------------------------------------------------------------------------- #
class PlanVerdict(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


@dataclass(slots=True)
class PlanDecision:
    verdict: PlanVerdict
    feedback: str | None = None

    @property
    def approved(self) -> bool:
        return self.verdict is PlanVerdict.APPROVE
