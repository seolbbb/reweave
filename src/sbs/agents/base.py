"""Base agent interface for pipeline stages."""

from __future__ import annotations

from abc import ABC, abstractmethod

from sbs.config import Config
from sbs.llm.client import LLMClient


class BaseAgent(ABC):
    """Abstract base class for pipeline agents."""

    def __init__(self, llm: LLMClient, config: Config):
        self.llm = llm
        self.config = config

    @abstractmethod
    async def run(self, *args, **kwargs):
        """Execute the agent's task."""
        ...
