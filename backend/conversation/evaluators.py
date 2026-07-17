import json
import re
import time
from typing import Any


SCORE_FIELDS = (
    "task_completion",
    "clarity",
    "fluency",
    "organization",
    "interaction",
)


def _clamp_score(value: Any, default: int = 3) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        score = default
    return max(1, min(5, score))


def _clean_text_list(value: Any, limit: int = 2) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        if len(result) >= limit:
            break
    return result


def _phrase_key(phrase: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", phrase.lower()).strip()


def detect_target_phrases(
    answers: list[str],
    target_phrases: tuple[str, ...] | list[str],
) -> list[str]:
    combined = " ".join(answers).lower()
    combined = re.sub(r"\s+", " ", combined)
    used = []
    for phrase in target_phrases:
        key = _phrase_key(phrase)
        if key and key in re.sub(r"[^a-z0-9 ]", "", combined):
            used.append(phrase)
    return used


def extract_json_object(raw_text: str) -> dict[str, Any]:
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Evaluator response did not contain a JSON object.")
        parsed = json.loads(text[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("Evaluator response must be a JSON object.")
    return parsed


def normalize_feedback(
    raw: dict[str, Any],
    answers: list[str],
    target_phrases: tuple[str, ...] | list[str],
) -> dict[str, Any]:
    feedback = {
        field: _clamp_score(raw.get(field))
        for field in SCORE_FIELDS
    }

    detected_phrases = detect_target_phrases(answers, target_phrases)
    feedback["target_phrases_used"] = detected_phrases
    feedback["target_phrases_score"] = min(4, len(detected_phrases))

    strengths = _clean_text_list(raw.get("strengths"), limit=2)
    if not strengths:
        strengths = ["You completed the conversation and communicated your routine."]
    feedback["strengths"] = strengths

    priorities = []
    raw_priorities = raw.get("priority_improvements")
    if isinstance(raw_priorities, list):
        for item in raw_priorities:
            if not isinstance(item, dict):
                continue
            issue = str(item.get("issue", "")).strip()
            suggestion = str(item.get("suggestion", "")).strip()
            if issue and suggestion:
                priorities.append({"issue": issue, "suggestion": suggestion})
            if len(priorities) >= 2:
                break

    if not priorities:
        priorities = [
            {
                "issue": "The answers can be connected more clearly.",
                "suggestion": "Use connectors such as 'after that' and 'then'.",
            }
        ]
    feedback["priority_improvements"] = priorities

    improved_example = str(raw.get("improved_example", "")).strip()
    if not improved_example:
        improved_example = (
            "I usually wake up at seven. After that, I have breakfast "
            "and start working."
        )
    feedback["improved_example"] = improved_example
    return feedback


def build_spoken_feedback(feedback: dict[str, Any]) -> str:
    strength = feedback["strengths"][0]
    priority = feedback["priority_improvements"][0]["suggestion"]
    example = feedback["improved_example"]
    return (
        f"Good job. {strength} In the next attempt, {priority} "
        f"For example: {example} Let's try again."
    )


def fallback_feedback(
    answers: list[str],
    target_phrases: tuple[str, ...] | list[str],
) -> dict[str, Any]:
    word_counts = [len(answer.split()) for answer in answers if answer.strip()]
    average_words = sum(word_counts) / max(len(word_counts), 1)
    combined = " ".join(answers).lower()
    connectors = ("after that", "then", "because", "but", "so", "most of the time")
    connector_count = sum(1 for connector in connectors if connector in combined)

    raw = {
        "task_completion": min(5, max(1, round(len(answers) / 6 * 5))),
        "clarity": 4 if average_words >= 7 else 3,
        "fluency": 4 if average_words >= 10 else 3,
        "organization": 4 if connector_count >= 2 else 2,
        "interaction": 4 if len(answers) >= 4 else 3,
        "strengths": [
            "You answered the questions and described important parts of your day."
        ],
        "priority_improvements": [
            {
                "issue": "Some activities may sound like separate ideas.",
                "suggestion": "connect your activities using 'after that' or 'then'.",
            },
            {
                "issue": "Some answers may be very short.",
                "suggestion": "add one extra detail to each answer.",
            },
        ],
        "improved_example": (
            "I usually wake up at seven. After that, I have coffee, "
            "get ready, and start working at eight."
        ),
    }
    return normalize_feedback(raw, answers, target_phrases)


def evaluate_first_attempt(
    answers: list[str],
    target_phrases: tuple[str, ...] | list[str],
    objective: str,
    level: str,
) -> tuple[dict[str, Any], float]:
    start = time.time()
    transcript = "\n".join(
        f"{index + 1}. {answer}" for index, answer in enumerate(answers)
    )
    phrase_list = "\n".join(f"- {phrase}" for phrase in target_phrases)

    system_prompt = """You evaluate a short spoken-English practice session for an A2/B1 learner.
Return ONLY a valid JSON object, without Markdown.
Be encouraging, specific, and concise. Do not give a grammar lecture.
Do not punish probable speech-to-text punctuation or capitalization errors.
Scores must be integers from 1 to 5.
Use at most two strengths and two priority improvements.
The JSON must use exactly this structure:
{
  "task_completion": 1,
  "clarity": 1,
  "fluency": 1,
  "organization": 1,
  "interaction": 1,
  "strengths": ["..."],
  "priority_improvements": [
    {"issue": "...", "suggestion": "..."}
  ],
  "improved_example": "..."
}"""

    user_prompt = f"""Learner level: {level}
Task objective: {objective}
Target phrases:
{phrase_list}

Student answers:
{transcript}

Evaluate only these answers. The improved example must be natural, short, and suitable for speaking aloud."""

    try:
        from . import pipeline

        response = pipeline.groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=700,
            reasoning_effort="low",
        )
        raw_text = response.choices[0].message.content or ""
        feedback = normalize_feedback(
            extract_json_object(raw_text),
            answers,
            target_phrases,
        )
        feedback["source"] = "model"
    except Exception as exc:
        print(f"[evaluator] Falling back to local feedback: {exc}")
        feedback = fallback_feedback(answers, target_phrases)
        feedback["source"] = "fallback"

    feedback["spoken_feedback"] = build_spoken_feedback(feedback)
    return feedback, time.time() - start
