from typing import Type, cast

from dotenv import load_dotenv

from .agent import Agent, Playback
from .recorder import Recorder
from .swarm import Swarm
from .templates.random_agent import Random

load_dotenv()

AVAILABLE_AGENTS: dict[str, Type[Agent]] = {
    "random": Random,
}

# add all the recording files as valid agent names
for rec in Recorder.list():
    AVAILABLE_AGENTS[rec] = Playback

# 우리 에이전트는 아래에서 등록
try:
    from .templates.our_agent import OurAgent
    AVAILABLE_AGENTS["ouragent"] = OurAgent
except ImportError:
    pass

__all__ = [
    "Swarm",
    "Random",
    "Agent",
    "Recorder",
    "Playback",
    "AVAILABLE_AGENTS",
]
