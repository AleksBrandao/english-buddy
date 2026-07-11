from django.test import SimpleTestCase

from .evaluators import (
    build_spoken_feedback,
    detect_target_phrases,
    extract_json_object,
    fallback_feedback,
    normalize_feedback,
)


TARGET_PHRASES = (
    "I usually...",
    "After that...",
    "Most of the time...",
    "It depends on the day.",
)


class EvaluatorHelpersTests(SimpleTestCase):
    def test_extract_json_accepts_markdown_fence(self):
        parsed = extract_json_object(
            '```json\n{"clarity": 4, "strengths": ["Clear answers"]}\n```'
        )

        self.assertEqual(parsed["clarity"], 4)

    def test_detect_target_phrases_uses_student_answers(self):
        used = detect_target_phrases(
            [
                "I usually wake up at seven.",
                "After that I have breakfast.",
            ],
            TARGET_PHRASES,
        )

        self.assertEqual(used, ["I usually...", "After that..."])

    def test_normalize_feedback_clamps_scores_and_limits_items(self):
        feedback = normalize_feedback(
            {
                "task_completion": 9,
                "clarity": 0,
                "fluency": 4,
                "organization": 3,
                "interaction": 5,
                "strengths": ["One", "Two", "Three"],
                "priority_improvements": [
                    {"issue": "Issue one", "suggestion": "Suggestion one"},
                    {"issue": "Issue two", "suggestion": "Suggestion two"},
                    {"issue": "Issue three", "suggestion": "Suggestion three"},
                ],
                "improved_example": "I usually wake up early.",
            },
            ["I usually wake up early."],
            TARGET_PHRASES,
        )

        self.assertEqual(feedback["task_completion"], 5)
        self.assertEqual(feedback["clarity"], 1)
        self.assertEqual(len(feedback["strengths"]), 2)
        self.assertEqual(len(feedback["priority_improvements"]), 2)
        self.assertEqual(feedback["target_phrases_score"], 1)

    def test_fallback_feedback_is_complete_and_speakable(self):
        feedback = fallback_feedback(
            [
                "I usually wake up at seven.",
                "After that I drink coffee and start working.",
                "Most of the time I work until five.",
                "It depends on the day.",
            ],
            TARGET_PHRASES,
        )
        spoken = build_spoken_feedback(feedback)

        self.assertEqual(feedback["target_phrases_score"], 4)
        self.assertTrue(feedback["strengths"])
        self.assertTrue(feedback["priority_improvements"])
        self.assertIn("Let's try again", spoken)
