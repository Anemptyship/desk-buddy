"""Install a pinned DA3 checkout with a small macOS import compatibility patch.

The unused COLMAP exporter otherwise eagerly loads a second OpenMP runtime.
Defer that import until an actual COLMAP export is requested; model math is unchanged.
"""
from pathlib import Path
import os
import subprocess
import sys

REVISION = "3d835ec1a5802d64a8b8b15f817a1ab54809bfe4"
ROOT = Path(__file__).resolve().parents[1]
source = ROOT / ".cache" / "Depth-Anything-3"
source.parent.mkdir(exist_ok=True)
if not source.exists():
    subprocess.run(["git", "clone", "https://github.com/ByteDance-Seed/Depth-Anything-3.git", str(source)], check=True)
subprocess.run(["git", "checkout", REVISION], cwd=source, check=True)
target = source / "src/depth_anything_3/utils/export/__init__.py"
text = target.read_text()
eager = "from .colmap import export_to_colmap\n"
if "\n" + eager in text:
    text = text.replace("\n" + eager, "\n")
    text = text.replace('elif export_format == "colmap":\n', 'elif export_format == "colmap":\n        from .colmap import export_to_colmap\n')
    target.write_text(text)
subprocess.run(["uv", "pip", "install", "--python", sys.executable, "--no-deps", "-e", str(source)], check=True)
print(f"DA3 {REVISION}; only patch: lazy COLMAP exporter import")
