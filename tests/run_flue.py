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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--save-reference", type=Path, help="Save the reference scene instead of running tests")
    mode.add_argument("--reference-only", action="store_true", help="Run only the full reference asset suite")
    parser.add_argument("--settings-scanner", type=Path, help="Optional CS2 Settings Generator CLI binary")
    args = parser.parse_args()
    if args.save_reference and args.settings_scanner:
        parser.error("--settings-scanner applies only to test runs")
    if args.save_reference:
        args.save_reference = args.save_reference.resolve()
        if args.save_reference.suffix != ".blend" or args.save_reference.exists():
            parser.error("--save-reference must be a new .blend file")
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
assert bpy.app.version >= (4, 2, 0) and not bpy.data.filepath
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
            scanner = str(args.settings_scanner.resolve()) if args.settings_scanner else None
            action = (f"runpy.run_path({str(suite)!r}, run_name='__main__', "
                      f"init_globals={{'settings_scanner': {scanner!r}}})")
            marker = "MW_CS2_BATCH_EXPORTER_TEST_OK"
            if args.reference_only:
                reference = suite.with_name("test_reference_asset.py")
                marker = "MW_CS2_REFERENCE_ASSET_TEST_OK"
                action = f"""
import sys
sys.path.insert(0, {str(suite.parent.parent)!r})
import mw_cs2_batch_exporter as addon
addon.register()
try:
    runpy.run_path({str(reference)!r})["run"](addon, {scanner!r})
finally:
    addon.unregister()
print({marker!r})
"""
            if args.save_reference:
                fixture = suite.with_name("reference_scene.py")
                marker = "MW_CS2_REFERENCE_SAVED"
                action = f"""
for obj in list(bpy.context.scene.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
for mesh in list(bpy.data.meshes):
    if not mesh.users:
        bpy.data.meshes.remove(mesh)
bpy.context.scene.name = 'CS2 Reference'
runpy.run_path({str(fixture)!r}, run_name='__main__')
assert bpy.ops.wm.save_as_mainfile(filepath={str(args.save_reference)!r}, copy=True, compress=True) == {{'FINISHED'}}
print({marker!r})
"""
            script = f"""
import os, runpy, bpy
assert os.getpid() == {process.pid}
assert bpy.app.version >= (4, 2, 0) and not bpy.data.filepath
{action}
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
            if not reply.get("ok") or marker not in reply.get("stdout", ""):
                raise RuntimeError("Flue suite failed; see suite.log")
            print(f"{reply['result']}: {marker}")
            if scanner:
                assert "MW_CS2_SETTINGS_REFERENCE_SCAN_OK" in reply["stdout"]
                print("MW_CS2_SETTINGS_REFERENCE_SCAN_OK")
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
