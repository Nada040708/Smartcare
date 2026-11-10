from pathlib import Path
import shutil
import subprocess

import pytest


def test_node_red_function_and_wiring():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the Node-RED flow unit tests")
    script = Path(__file__).resolve().parents[2] / "infra/node-red/flow.test.cjs"
    result = subprocess.run([node, "--test", str(script)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
