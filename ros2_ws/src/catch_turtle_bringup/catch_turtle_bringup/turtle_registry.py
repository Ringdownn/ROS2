from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from . import utils


@dataclass
class TurtleEntry:
    name: str
    x: float = 0.0
    y: float = 0.0
    caught: bool = False
    has_pose: bool = False


class TurtleRegistry:
    def __init__(self) -> None:
        self._turtles: Dict[str, TurtleEntry] = {}

    def add(self, name: str) -> TurtleEntry:
        if name not in self._turtles:
            self._turtles[name] = TurtleEntry(name=name)
        return self._turtles[name]

    def update_pose(self, name: str, x: float, y: float) -> None:
        entry = self._turtles.get(name)
        if entry is None:
            entry = self.add(name)
        entry.x = x
        entry.y = y
        entry.has_pose = True

    def mark_caught(self, name: str) -> None:
        entry = self._turtles.get(name)
        if entry is not None:
            entry.caught = True

    def get(self, name: str) -> Optional[TurtleEntry]:
        return self._turtles.get(name)

    def uncaught_targets(self, exclude: Optional[List[str]] = None) -> List[TurtleEntry]:
        excluded = set(exclude or [])
        return [
            t for t in self._turtles.values()
            if t.has_pose and not t.caught and t.name not in excluded
        ]

    def nearest_to(self, x: float, y: float,
                   exclude: Optional[List[str]] = None) -> Optional[TurtleEntry]:
        candidates = self.uncaught_targets(exclude=exclude)
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda t: utils.distance(x, y, t.x, t.y),
        )
