"""Registry for discovering and loading evaluation flows."""

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import List

FLOWS_DIR = Path(__file__).parent / "flows"
RESULTS_DIR = Path(__file__).parent / "results"
EVALUATIONS_DIR = Path(__file__).parent


@dataclass
class FlowPaths:
    name: str
    conversations_dir: Path
    known_bad_dir: Path
    context_dir: Path
    results_conv_dir: Path
    results_eval_dir: Path
    results_known_bad_dir: Path


def list_flows() -> List[str]:
    """Return names of all registered flows (subdirs of flows/ containing flow.py)."""
    if not FLOWS_DIR.exists():
        return []
    return sorted(
        [d.name for d in FLOWS_DIR.iterdir() if d.is_dir() and (d / "flow.py").exists()]
    )


def get_flow_paths(name: str) -> FlowPaths:
    """Return all relevant directory paths for the named flow."""
    flow_dir = FLOWS_DIR / name
    return FlowPaths(
        name=name,
        conversations_dir=flow_dir / "conversations",
        known_bad_dir=flow_dir / "known_bad_conversations",
        context_dir=flow_dir / "context",
        results_conv_dir=RESULTS_DIR / name / "conversation_results",
        results_eval_dir=RESULTS_DIR / name / "deep_eval_results",
        results_known_bad_dir=RESULTS_DIR / name / "known_bad_results",
    )


def _load_module_from_path(module_name: str, file_path: Path) -> ModuleType:
    """Load a Python module from a file path, ensuring evaluations/ is on sys.path."""
    # Ensure the evaluations directory is on sys.path so that loaded modules
    # can import helpers, get_deepeval_metrics, etc.
    evaluations_dir = str(EVALUATIONS_DIR)
    if evaluations_dir not in sys.path:
        sys.path.insert(0, evaluations_dir)

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_flow(name: str) -> ModuleType:
    """Import and return the flow.py module for the given flow name."""
    flow_file = FLOWS_DIR / name / "flow.py"
    if not flow_file.exists():
        raise FileNotFoundError(f"No flow.py found for flow '{name}' at {flow_file}")
    return _load_module_from_path(f"flow_{name.replace('-', '_')}", flow_file)


def load_flow_metrics(name: str) -> ModuleType:
    """Import and return the metrics.py module for the given flow name."""
    metrics_file = FLOWS_DIR / name / "metrics.py"
    if not metrics_file.exists():
        raise FileNotFoundError(
            f"No metrics.py found for flow '{name}' at {metrics_file}"
        )
    return _load_module_from_path(f"metrics_{name.replace('-', '_')}", metrics_file)
