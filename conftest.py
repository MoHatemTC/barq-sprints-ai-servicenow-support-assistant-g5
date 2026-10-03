"""conftest.py

Root pytest configuration.
Ensures project root is on sys.path and resolves Windows filesystem case collision
where git tracks both 'Agent/agent.py' and 'agent/__init__.py'.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Ensure 'agent' package is properly registered in sys.modules
if "agent" not in sys.modules:
    agent_path = ROOT / "agent"
    if not agent_path.exists():
        agent_path = ROOT / "Agent"
    
    if agent_path.exists() and (agent_path / "__init__.py").exists():
        spec = importlib.util.spec_from_file_location(
            "agent",
            str(agent_path / "__init__.py"),
            submodule_search_locations=[str(agent_path)],
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules["agent"] = mod
            sys.modules["Agent"] = mod
            spec.loader.exec_module(mod)
