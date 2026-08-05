"""
The editor, run rather than read.

editor.js is browser code, so pytest cannot import it. It can run it: the
harness beside this file executes the real file against a stub DOM and
asserts what it draws and how block editing behaves.

Worth having as part of the ordinary suite rather than a thing to remember
to run, because the failure it catches is a quiet one. A missing function
is a runtime error, not a parse error - an edit once deleted half of
editor.js and every syntax check still passed.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent / "editor_harness.mjs"


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node is not installed")
def test_the_editor_runs_and_block_editing_behaves():
    result = subprocess.run(
        ["node", str(HARNESS)],
        capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 0, (
        f"the editor harness failed:\n{result.stdout}\n{result.stderr}"
    )
