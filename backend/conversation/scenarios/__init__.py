from .daily_routine import DAILY_ROUTINE, ScenarioDefinition


SCENARIOS = {
    DAILY_ROUTINE.scenario_id: DAILY_ROUTINE,
}


def get_scenario(scenario_id: str) -> ScenarioDefinition:
    try:
        return SCENARIOS[scenario_id]
    except KeyError as exc:
        raise ValueError(f"Unknown lesson scenario: {scenario_id}") from exc


__all__ = [
    "DAILY_ROUTINE",
    "SCENARIOS",
    "ScenarioDefinition",
    "get_scenario",
]
