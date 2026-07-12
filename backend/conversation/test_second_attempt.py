from django.test import SimpleTestCase

from .lesson_orchestrator import (
    LessonOrchestrator,
    LessonStage,
    LessonTransitionError,
)


class SecondAttemptFlowTests(SimpleTestCase):
    def setUp(self):
        self.lesson = LessonOrchestrator()
        self.lesson.start()
        self.lesson.continue_lesson()
        self.lesson.continue_lesson()

        for index in range(4):
            self.lesson.register_user_utterance(
                f"First attempt answer {index + 1}."
            )
        self.lesson.finish_current_attempt()

    def test_second_attempt_requires_intermediate_feedback(self):
        with self.assertRaises(LessonTransitionError):
            self.lesson.start_second_attempt()

    def test_second_attempt_starts_with_a_new_opening_question(self):
        self.lesson.set_intermediate_feedback(
            {
                "strengths": ["The routine was understandable."],
                "priority_improvements": [
                    {
                        "issue": "Ideas were separated.",
                        "suggestion": "Use after that to connect activities.",
                    }
                ],
            }
        )

        event = self.lesson.start_second_attempt()

        self.assertEqual(self.lesson.state.stage, LessonStage.SECOND_ATTEMPT)
        self.assertEqual(
            event["question"],
            "Tell me about a typical weekday from the moment you wake up.",
        )
        self.assertNotEqual(
            event["question"],
            self.lesson.scenario.opening_question,
        )
        self.assertEqual(self.lesson.state.second_attempt, [])

    def test_second_attempt_can_finish_after_three_answers(self):
        self.lesson.set_intermediate_feedback(
            {"suggestion": "Connect the activities in sequence."}
        )
        self.lesson.start_second_attempt()

        for index in range(3):
            result = self.lesson.register_user_utterance(
                f"Second attempt answer {index + 1}."
            )

        self.assertTrue(result["can_finish"])
        transition = self.lesson.finish_current_attempt()

        self.assertEqual(transition["stage"], LessonStage.FINAL_RESULT.value)
        self.assertEqual(self.lesson.state.stage, LessonStage.FINAL_RESULT)
        self.assertEqual(len(self.lesson.state.second_attempt), 3)
