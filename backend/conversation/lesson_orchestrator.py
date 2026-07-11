from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from .scenarios import DAILY_ROUTINE, ScenarioDefinition


class LessonStage(str, Enum):
    INTRODUCTION = "introduction"
    PHRASE_PREPARATION = "phrase_preparation"
    FIRST_ATTEMPT = "first_attempt"
    FIRST_FEEDBACK = "first_feedback"
    SECOND_ATTEMPT = "second_attempt"
    FINAL_RESULT = "final_result"
    COMPLETED = "completed"


class LessonTransitionError(ValueError):
    """Raised when a command is incompatible with the current lesson stage."""


@dataclass
class LessonState:
    stage: LessonStage = LessonStage.INTRODUCTION
    first_attempt: list[str] = field(default_factory=list)
    second_attempt: list[str] = field(default_factory=list)
    intermediate_feedback: dict[str, Any] = field(default_factory=dict)
    final_result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["stage"] = self.stage.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "LessonState":
        if not data:
            return cls()
        return cls(
            stage=LessonStage(data.get("stage", LessonStage.INTRODUCTION.value)),
            first_attempt=list(data.get("first_attempt") or []),
            second_attempt=list(data.get("second_attempt") or []),
            intermediate_feedback=dict(data.get("intermediate_feedback") or {}),
            final_result=dict(data.get("final_result") or {}),
        )


class LessonOrchestrator:
    """Controls deterministic lesson stages without calling STT, LLM, or TTS.

    The consumer remains responsible for transporting audio and invoking the
    pipeline. This class only decides which pedagogical step is active, records
    user utterances, and enforces minimum/maximum turn counts.
    """

    def __init__(
        self,
        scenario: ScenarioDefinition = DAILY_ROUTINE,
        state: LessonState | None = None,
    ):
        self.scenario = scenario
        self.state = state or LessonState()

    def snapshot(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario.scenario_id,
            "scenario_title": self.scenario.title,
            **self.state.to_dict(),
        }

    def start(self) -> dict[str, Any]:
        self._require_stage(LessonStage.INTRODUCTION)
        return {
            "type": "lesson_started",
            "scenario_id": self.scenario.scenario_id,
            "title": self.scenario.title,
            "objective": self.scenario.objective,
            "estimated_duration_minutes": self.scenario.estimated_duration_minutes,
            "stage": self.state.stage.value,
            "messages": list(self.scenario.introduction),
        }

    def continue_lesson(self) -> dict[str, Any]:
        if self.state.stage == LessonStage.INTRODUCTION:
            self.state.stage = LessonStage.PHRASE_PREPARATION
            return {
                "type": "target_phrases",
                "stage": self.state.stage.value,
                "phrases": list(self.scenario.target_phrases),
                "optional_phrases": list(self.scenario.optional_phrases),
            }

        if self.state.stage == LessonStage.PHRASE_PREPARATION:
            self.state.stage = LessonStage.FIRST_ATTEMPT
            return {
                "type": "lesson_stage_changed",
                "stage": self.state.stage.value,
                "question": self.scenario.opening_question,
            }

        raise LessonTransitionError(
            f"continue_lesson is not valid during {self.state.stage.value}"
        )

    def register_user_utterance(self, text: str) -> dict[str, Any]:
        normalized = text.strip()
        if not normalized:
            raise ValueError("The user utterance cannot be empty.")

        if self.state.stage == LessonStage.FIRST_ATTEMPT:
            utterances = self.state.first_attempt
            questions = self.scenario.first_attempt_questions
            minimum = self.scenario.min_first_attempt_turns
            maximum = self.scenario.max_first_attempt_turns
        elif self.state.stage == LessonStage.SECOND_ATTEMPT:
            utterances = self.state.second_attempt
            questions = self.scenario.second_attempt_questions
            minimum = self.scenario.min_second_attempt_turns
            maximum = self.scenario.max_second_attempt_turns
        else:
            raise LessonTransitionError(
                "User utterances can only be registered during an attempt."
            )

        utterances.append(normalized)
        answer_count = len(utterances)
        reached_maximum = answer_count >= maximum
        can_finish = answer_count >= minimum

        if reached_maximum:
            transition = self.finish_current_attempt()
            return {
                "type": "attempt_turn_recorded",
                "stage": self.state.stage.value,
                "answer_count": answer_count,
                "can_finish": True,
                "attempt_complete": True,
                "next_question": None,
                "transition": transition,
            }

        question_index = (
            answer_count - 1
            if self.state.stage == LessonStage.FIRST_ATTEMPT
            else answer_count
        )
        next_question = (
            questions[question_index]
            if question_index < len(questions)
            else None
        )
        return {
            "type": "attempt_turn_recorded",
            "stage": self.state.stage.value,
            "answer_count": answer_count,
            "can_finish": can_finish,
            "attempt_complete": False,
            "next_question": next_question,
        }

    def finish_current_attempt(self, force: bool = False) -> dict[str, Any]:
        if self.state.stage == LessonStage.FIRST_ATTEMPT:
            answer_count = len(self.state.first_attempt)
            minimum = self.scenario.min_first_attempt_turns
            next_stage = LessonStage.FIRST_FEEDBACK
        elif self.state.stage == LessonStage.SECOND_ATTEMPT:
            answer_count = len(self.state.second_attempt)
            minimum = self.scenario.min_second_attempt_turns
            next_stage = LessonStage.FINAL_RESULT
        else:
            raise LessonTransitionError("There is no active attempt to finish.")

        if not force and answer_count < minimum:
            raise LessonTransitionError(
                f"At least {minimum} answers are required before finishing "
                f"this attempt; received {answer_count}."
            )

        self.state.stage = next_stage
        return {
            "type": "lesson_stage_changed",
            "stage": self.state.stage.value,
            "answer_count": answer_count,
        }

    def set_intermediate_feedback(
        self,
        feedback: dict[str, Any],
    ) -> dict[str, Any]:
        self._require_stage(LessonStage.FIRST_FEEDBACK)
        self.state.intermediate_feedback = dict(feedback)
        return {
            "type": "intermediate_feedback",
            "stage": self.state.stage.value,
            "feedback": self.state.intermediate_feedback,
        }

    def start_second_attempt(self) -> dict[str, Any]:
        self._require_stage(LessonStage.FIRST_FEEDBACK)
        if not self.state.intermediate_feedback:
            raise LessonTransitionError(
                "Intermediate feedback must be stored before the second attempt."
            )

        self.state.stage = LessonStage.SECOND_ATTEMPT
        return {
            "type": "lesson_stage_changed",
            "stage": self.state.stage.value,
            "question": self.scenario.second_attempt_questions[0],
        }

    def set_final_result(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        self._require_stage(LessonStage.FINAL_RESULT)
        self.state.final_result = dict(result)
        final_event = {
            "type": "final_result",
            "stage": self.state.stage.value,
            "result": self.state.final_result,
        }
        self.state.stage = LessonStage.COMPLETED
        completed_event = {
            "type": "lesson_completed",
            "stage": self.state.stage.value,
            "scenario_id": self.scenario.scenario_id,
        }
        return [final_event, completed_event]

    def _require_stage(self, expected: LessonStage) -> None:
        if self.state.stage != expected:
            raise LessonTransitionError(
                f"Expected stage {expected.value}, got {self.state.stage.value}."
            )
