"""New memory-driven KB ingestion pipeline.

Replaces `da_agent.kb` as the active ingestion path. The legacy module is
retained on disk (for tests + historical context) but is no longer imported
by the route layer or registered in `AppState`.

Public surface:

- `IngestionMeta` / `IngestionStatus`  — registry row dataclass + status enum.
- `IngestionRegistry`                  — atomic-rename JSON registry, replaces
                                         `kb.KbRegistry` and reuses the same
                                         on-disk file (`kb/registry.json`).
- `KbProfiler` / `ProfileResult`       — opus-driven subagent invocation.
- `build_kb_profiler_definition`       — factory for the AgentDefinition;
                                         exposed so tests can assert shape.
- `run_pipeline`                       — async orchestrator, fire-and-forget
                                         from the upload handler.
"""

from .profiler import KbProfiler, ProfileResult, build_kb_profiler_definition
from .registry import IngestionMeta, IngestionRegistry, IngestionStatus
from .runner import run_pipeline

__all__ = [
    "IngestionMeta",
    "IngestionRegistry",
    "IngestionStatus",
    "KbProfiler",
    "ProfileResult",
    "build_kb_profiler_definition",
    "run_pipeline",
]
