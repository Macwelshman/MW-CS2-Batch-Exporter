"""Run the Blender suite via a private Flue bridge on macOS."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, default=Path("/Applications/Blender.app/Contents/MacOS/Blender"))
    args = parser.parse_args()
    site = Path(subprocess.check_output(["flue", "where"], text=True).splitlines()[0])
    adapter = site / "adapters/blender_adapter"
    bridge = adapter / "blender_bridge.py"
    addon = adapter / "addon/creative_adapter_bridge.py"
    if not all(path.is_file() for path in (args.blender, bridge, addon)):
        parser.error("Blender executable or Flue Blender adapter missing")
    suite = Path(__file__).with_name("test_blender.py").resolve()
    root = Path(tempfile.mkdtemp(prefix="mw-flue-"))
    print(f"Logs: {root}", flush=True)
    bootstrap = root / "bootstrap.py"
    bootstrap.write_text(f"""
import os, runpy, bpy
from pathlib import Path
assert bpy.app.version == (5, 2, 3) and not bpy.data.filepath
adapter = runpy.run_path({str(addon)!r})
adapter['register'].__globals__['_session_dir'] = lambda: {str(root)!r}
adapter['register']()
Path({str(root / 'pid')!r}).write_text(str(os.getpid()))
""")
    env = dict(os.environ, BLENDER_USER_RESOURCES=str(root / "profile"), TMPDIR=str(root))
    with (root / "blender.log").open("w") as log:
        process = subprocess.Popen(
            [str(args.blender), "--factory-startup", "--python-exit-code", "1", "--python", str(bootstrap)],
            env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 60
            while not (root / "pid").exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Disposable Blender failed to start its private bridge")
                time.sleep(0.1)
            if int((root / "pid").read_text()) != process.pid:
                raise RuntimeError("Private bridge PID does not match the launched process")
            script = f"""
import os, runpy, bpy
assert os.getpid() == {process.pid}
assert bpy.app.version == (5, 2, 3) and not bpy.data.filepath
runpy.run_path({str(suite)!r}, run_name='__main__')
_result = bpy.app.version_string
"""
            result = subprocess.run(
                [sys.executable, str(bridge), "--session-file", str(root / "blender.json"), "--stdin"],
                input=script, text=True, capture_output=True, timeout=45,
            )
            (root / "suite.log").write_text(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError("Flue suite failed; see suite.log")
            reply = json.loads(result.stdout)
            if not reply.get("ok") or "MW_CS2_BATCH_EXPORTER_TEST_OK" not in reply.get("stdout", ""):
                raise RuntimeError("Flue suite failed; see suite.log")
            print(f"{reply['result']}: MW_CS2_BATCH_EXPORTER_TEST_OK")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            (root / "blender.json").unlink(missing_ok=True)
            for report in root.glob("*.crash.txt"):
                print(f"Crash report: {report}", file=sys.stderr)


if __name__ == "__main__":
    main()
