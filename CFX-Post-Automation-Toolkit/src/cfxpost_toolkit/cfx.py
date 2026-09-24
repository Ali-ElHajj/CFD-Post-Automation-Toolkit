from pathlib import Path

from .config import CFXAutomationConfig
from .progress import ProgressCallback, emit


def execute_session(
    session_file: Path | str,
    completion_file: Path | str | None = None,
    completion_text: str = "Import is successful",
    description: str = "CFX-Post session",
    automation: CFXAutomationConfig | None = None,
    progress_callback: ProgressCallback | None = None,
) -> None:
    """Execute a session in the already-open CFX-Post Command Editor."""
    from . import _engine as engine
    from ._runtime import apply_automation_config

    automation = automation or CFXAutomationConfig()
    apply_automation_config(engine, automation)

    emit(progress_callback, "cfx", f"Executing {Path(session_file).name}")
    engine.execute_cfx_session(
        Path(session_file),
        completion_file=Path(completion_file) if completion_file else None,
        completion_text=completion_text,
        completion_description=description,
    )
    emit(progress_callback, "cfx", f"Completed {Path(session_file).name}")


def find_command_editor(automation: CFXAutomationConfig | None = None) -> int:
    from . import _engine as engine
    from ._runtime import apply_automation_config

    automation = automation or CFXAutomationConfig()
    apply_automation_config(engine, automation)
    return engine.find_command_editor()
