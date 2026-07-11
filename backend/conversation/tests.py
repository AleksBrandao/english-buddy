from django.test import SimpleTestCase

from .lesson_orchestrator import (
    LessonOrchestrator,
    LessonStage,
    LessonState,
    LessonTransitionError,
)
from .scenarios import get_scenario


class ScenarioRegistryTests(SimpleTestCase):
    def test_daily_routine_scenario_is_available(self):
        scenario = get_scenario("daily-routine-01")

        self.assertEqual(
            scenario.title,
            "Talking about your daily routine",
        )
        self.assertEqual(len(scenario.target_phrases), 4)
        self.assertEqual(scenario.max_first_attempt_turns, 6)

    def test_unknown_scenario_raises_value_error(self):
        with self.assertRaises(ValueError):
            get_scenario("unknown-scenario")


class LessonOrchestratorTests(SimpleTestCase):
    def setUp(self):
        self.lesson = LessonOrchestrator()

    def _start_first_attempt(self):
        self.lesson.start()
        self.lesson.continue_lesson()
        self.lesson.continue_lesson()

    def test_intro_phrase_preparation_and_first_attempt(self):
        started = self.lesson.start()
        self.assertEqual(started["type"], "lesson_started")
        self.assertEqual(self.lesson.state.stage, LessonStage.INTRODUCTION)

        phrases = self.lesson.continue_lesson()
        self.assertEqual(phrases["type"], "target_phrases")
        self.assertEqual(
            self.lesson.state.stage,
            LessonStage.PHRASE_PREPARATION,
        )

        first_attempt = self.lesson.continue_lesson()
        self.assertEqual(
            first_attempt["question"],
            "What time do you usually wake up?",
        )
        self.assertEqual(
            self.lesson.state.stage,
            LessonStage.FIRST_ATTEMPT,
        )

    def test_first_attempt_cannot_finish_before_minimum(self):
        self._start_first_attempt()
        self.lesson.register_user_utterance("I wake up at seven.")

        with self.assertRaises(LessonTransitionError):
            self.lesson.finish_current_attempt()

    def test_first_attempt_auto_finishes_at_maximum(self):
        self._start_first_attempt()

        last_result = None
        for index in range(6):
            last_result = self.lesson.register_user_utterance(
                f"Answer number {index + 1}."
            )

        self.assertTrue(last_result["attempt_complete"])
        self.assertEqual(
            self.lesson.state.stage,
            LessonStage.FIRST_FEEDBACK,
        )
        self.assertEqual(len(self.lesson.state.first_attempt), 6)

    def test_second_attempt_requires_feedback(self):
        self._start_first_attempt()
        for index in range(4):
            self.lesson.register_user_utterance(
                f"First answer {index + 1}."
            )
        self.lesson.finish_current_attempt()

        with self.assertRaises(LessonTransitionError):
            self.lesson.start_second_attempt()

        self.lesson.set_intermediate_feedback(
            {"strength": "Clear answers."}
        )
        event = self.lesson.start_second_attempt()
        self.assertEqual(event["stage"], LessonStage.SECOND_ATTEMPT.value)

    def test_second_attempt_does_not_repeat_opening_question(self):
        self._start_first_attempt()
        for index in range(4):
            self.lesson.register_user_utterance(
                f"First answer {index + 1}."
            )
        self.lesson.finish_current_attempt()
        self.lesson.set_intermediate_feedback(
            {"suggestion": "Connect ideas."}
        )
        opening = self.lesson.start_second_attempt()

        next_turn = self.lesson.register_user_utterance(
            "I usually wake up at seven and start my day with coffee."
        )

        self.assertNotEqual(next_turn["next_question"], opening["question"])
        self.assertEqual(
            next_turn["next_question"],
            "What is the busiest part of your day?",
        )

    def test_full_flow_reaches_completed(self):
        self._start_first_attempt()
        for index in range(4):
            self.lesson.register_user_utterance(
                f"First attempt answer {index + 1}."
            )
        self.lesson.finish_current_attempt()
        self.lesson.set_intermediate_feedback(
            {"suggestion": "Use after that."}
        )
        self.lesson.start_second_attempt()

        for index in range(3):
            self.lesson.register_user_utterance(
                f"Second attempt answer {index + 1}."
            )
        self.lesson.finish_current_attempt()

        events = self.lesson.set_final_result({"improved": True})
        self.assertEqual(events[0]["type"], "final_result")
        self.assertEqual(events[1]["type"], "lesson_completed")
        self.assertEqual(self.lesson.state.stage, LessonStage.COMPLETED)

    def test_state_serialization_round_trip(self):
        state = LessonState(
            stage=LessonStage.SECOND_ATTEMPT,
            first_attempt=["First answer."],
            second_attempt=["Second answer."],
            intermediate_feedback={"suggestion": "Connect ideas."},
        )

        restored = LessonState.from_dict(state.to_dict())

        self.assertEqual(restored.stage, LessonStage.SECOND_ATTEMPT)
        self.assertEqual(restored.first_attempt, ["First answer."])
        self.assertEqual(restored.second_attempt, ["Second answer."])
        self.assertEqual(
            restored.intermediate_feedback,
            {"suggestion": "Connect ideas."},
        )
