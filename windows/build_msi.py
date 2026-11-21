"""Build on 64-bit Windows with CPython 3.13 and cx-Freeze 8.7.4."""

import os
from pathlib import Path
import sys
import tomllib

from cx_Freeze import Executable, setup

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
os.chdir(HERE)
sys.path.insert(0, str(ROOT))
version = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]
assets = [(ROOT / name, name) for name in ("LICENSE", "AUTHORS.txt", "THIRD_PARTY_NOTICES.md")]
assets.extend([
    (ROOT / "examples/fatigue.jsonl", "examples/fatigue.jsonl"),
    (ROOT / "eyeseeyou_edge/replay_config.json", "lib/eyeseeyou_edge/replay_config.json"),
    (Path(sys.base_prefix) / "LICENSE.txt", "licenses/Python.txt"),
])
setup(
    name="EyeSeeYou Edge", version=version, author="EyeSeeYou Team",
    description="Local study planner, focus timer and replay viewer",
    options={
        "build_exe": {"include_files": assets, "include_msvcr": True},
        "bdist_msi": {
            "all_users": False,
            "initial_target_dir": r"[LocalAppDataFolder]Programs\EyeSeeYou Edge",
            "directories": [("ProgramMenuFolder", "TARGETDIR", ".")],
            "upgrade_code": "{6996DB74-FBF2-42A1-BA8A-CC0D4F6D8A50}",
            "output_name": f"EyeSeeYou-Edge-{version}-Windows-x64.msi",
        },
    },
    executables=[Executable("launcher.py", base="gui", target_name="EyeSeeYouEdge",
                            shortcut_name="EyeSeeYou Edge", shortcut_dir="ProgramMenuFolder")],
)
