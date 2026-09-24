from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class ProgressEvent:
    stage: str
    message: str
    current: int | None = None
    total: int | None = None


ProgressCallback = Callable[[ProgressEvent], None]


def emit(callback: ProgressCallback | None, stage: str, message: str,
         current: int | None = None, total: int | None = None) -> None:
    if callback is not None:
        callback(ProgressEvent(stage, message, current, total))
