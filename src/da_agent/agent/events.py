"""Structured payloads exchanged between the agent and the UI layer.

These are deliberately serializable plain dataclasses so the same shapes can flow
over a websocket to a web frontend later, not just to the CLI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
            options=[
                Option(o["label"], o.get("description", ""))
                for o in d.get("options", [])
            ],
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


# --------------------------------------------------------------------------- #
# Todo / Task tracking
# --------------------------------------------------------------------------- #
class TodoStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass(slots=True)
class TodoItem:
    """One row in the agent's task list, normalised across TodoWrite + Task* tools.

    `task_id` is the SDK-assigned id (only present for Task* tools; synthesised for the
    legacy TodoWrite path so the consumer always has a stable key).
    """

    task_id: str
    subject: str
    active_form: str
    status: TodoStatus = TodoStatus.PENDING
    description: str = ""

    @property
    def display_text(self) -> str:
        """Active text the UI shows (active_form when running, subject otherwise)."""
        if self.status is TodoStatus.IN_PROGRESS and self.active_form:
            return self.active_form
        return self.subject

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass(slots=True)
class TodoSnapshot:
    """An immutable list view of the current todos, in the order the agent emitted them."""

    items: list[TodoItem] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    @property
    def in_progress(self) -> TodoItem | None:
        for item in self.items:
            if item.status is TodoStatus.IN_PROGRESS:
                return item
        return None

    def counts(self) -> dict[str, int]:
        out = {s.value: 0 for s in TodoStatus}
        for item in self.items:
            out[item.status.value] += 1
        return out

    def to_dict(self) -> dict:
        return {"items": [item.to_dict() for item in self.items]}
