from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_id: str
    title: str
    category: str
    level: str
    estimated_duration_minutes: int
    assistant_role: str
    objective: str
    introduction: tuple[str, ...]
    target_phrases: tuple[str, ...]
    optional_phrases: tuple[str, ...]
    opening_question: str
    first_attempt_questions: tuple[str, ...]
    second_attempt_questions: tuple[str, ...]
    min_first_attempt_turns: int = 4
    max_first_attempt_turns: int = 6
    min_second_attempt_turns: int = 3
    max_second_attempt_turns: int = 5


DAILY_ROUTINE = ScenarioDefinition(
    scenario_id="daily-routine-01",
    title="Talking about your daily routine",
    category="daily_life",
    level="A2_B1",
    estimated_duration_minutes=15,
    assistant_role=(
        "A friendly acquaintance who is genuinely interested in understanding "
        "the student's typical day."
    ),
    objective=(
        "Help the student describe a typical weekday, connect activities in "
        "sequence, and sustain answers with more than one sentence."
    ),
    introduction=(
        "Today we are going to talk about your daily routine.",
        "You do not need to speak perfectly. Just try to explain your day naturally.",
    ),
    target_phrases=(
        "I usually...",
        "After that...",
        "Most of the time...",
        "It depends on the day.",
    ),
    optional_phrases=(
        "Then I...",
        "Before I start working...",
        "During the afternoon...",
        "At the end of the day...",
    ),
    opening_question="What time do you usually wake up?",
    first_attempt_questions=(
        "What do you usually do after you wake up?",
        "What time do you start working?",
        "What is your morning usually like?",
        "What do you normally do during the afternoon?",
        "What do you do after work?",
        "Is your routine the same every day?",
    ),
    second_attempt_questions=(
        "Tell me about a typical weekday from the moment you wake up.",
        "What is the busiest part of your day?",
        "What normally happens after lunch?",
        "How do you usually finish your day?",
        "What changes when you have a less busy day?",
    ),
)
