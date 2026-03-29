"""데이터 모델."""

from dataclasses import dataclass


@dataclass
class StepRecord:
    step: int
    action: str
    state: str
    levels_completed: int
    grid: list[str]
    reasoning: str | None = None
    observation: str | None = None
    hypothesis: str | None = None
    challenge: str | None = None
    goal: str | None = None
    llm_phase: str | None = None
    report: dict | None = None
    prompts: dict | None = None
    responses: dict | None = None
    images: dict | None = None
    world_model: dict | None = None

    def to_dict(self) -> dict:
        d = {
            "step": self.step,
            "action": self.action,
            "state": self.state,
            "levels_completed": self.levels_completed,
            "grid": self.grid,
            "reasoning": self.reasoning,
            "observation": self.observation,
            "hypothesis": self.hypothesis,
            "challenge": self.challenge,
            "goal": self.goal,
            "llm_phase": self.llm_phase,
        }
        if self.report:
            d["report"] = self.report
        if self.prompts:
            d["prompts"] = self.prompts
        if self.responses:
            d["responses"] = self.responses
        if self.images:
            d["images"] = self.images
        if self.world_model:
            d["world_model"] = self.world_model
        return d
