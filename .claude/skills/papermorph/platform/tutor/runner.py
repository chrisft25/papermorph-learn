"""Run a code cell in a separate Python (tools/tutor/.runner-venv: numpy, matplotlib, sympy).

Only on the user's click and only for users granted the 'run' permission. Each run: fresh temp dir, minimal environment,
timeout, CPU limit, figures captured as PNG, one cell at a time (TUTOR_RUNNER_SLOTS). TUTOR_RUNNER=off disables it.

Security note: cells run as the server's own user. Grant 'run' only to people you trust with the server, or run the
server in a container without access to anything else (see references/deploy.md).
"""
import asyncio, base64, os, resource, signal, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE / ".runner-venv"
PY = VENV / "bin" / "python"
MAX_OUT = 20000
ENABLED = os.environ.get("TUTOR_RUNNER", "on") != "off"
SLOTS = asyncio.Semaphore(int(os.environ.get("TUTOR_RUNNER_SLOTS", "1")))

PRELUDE = '''
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, runpy
plt.style.use("dark_background")
_n = [0]
def _show(*a, **k):
    for n in plt.get_fignums():
        plt.figure(n).savefig(f"_fig{_n[0]}.png", dpi=110, bbox_inches="tight"); _n[0] += 1
    plt.close("all")
plt.show = _show
try:
    runpy.run_path("cell.py", run_name="__main__")
finally:
    _show()
'''


def _limits():   # child process: CPU-time cap, no core dumps
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120)); resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def status() -> dict:
    return {"ready": PY.exists() and ENABLED}


async def run(code: str, timeout: int = 90) -> dict:
    if not ENABLED:
        return {"error": "code cells are disabled on this server"}
    async with SLOTS:
        return await _run(code, timeout)


async def _run(code: str, timeout: int) -> dict:
    if not PY.exists():
        return {"error": "runner env missing: uv venv tools/tutor/.runner-venv && uv pip install --python tools/tutor/.runner-venv/bin/python numpy matplotlib sympy"}
    if len(code) > 40000:
        return {"error": "code too long"}
    with tempfile.TemporaryDirectory(prefix="tutor-run-") as d:
        d = Path(d)
        (d / "cell.py").write_text(code)
        (d / "_run.py").write_text(PRELUDE)
        env = {"PATH": f"{VENV / 'bin'}:/usr/bin:/bin", "HOME": str(d), "MPLCONFIGDIR": str(d), "PYTHONUNBUFFERED": "1",
               "PYTHONDONTWRITEBYTECODE": "1", "LANG": "en_US.UTF-8"}
        t0 = time.time()
        p = await asyncio.create_subprocess_exec(str(PY), "_run.py", cwd=d, env=env, stdout=asyncio.subprocess.PIPE,
                                                 stderr=asyncio.subprocess.STDOUT, start_new_session=True, preexec_fn=_limits)
        timed_out = False
        try:
            out, _ = await asyncio.wait_for(p.communicate(), timeout)
        except asyncio.TimeoutError:
            timed_out = True
            try: os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            out, _ = await p.communicate()
        text = out.decode(errors="replace")
        if len(text) > MAX_OUT:
            text = text[:MAX_OUT] + "\n… (output truncated)"
        imgs = [base64.b64encode(f.read_bytes()).decode() for f in sorted(d.glob("_fig*.png"))[:6]]
        return {"output": text, "images": imgs, "code": p.returncode, "timeout": timed_out, "secs": round(time.time() - t0, 1)}
