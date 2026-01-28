#!/usr/bin/env python3
"""tools/job_runner.py

A tiny, robust subprocess runner used by the Jac backend.

It:
- Writes a job JSON file (status/progress)
- Streams stdout/stderr to a log file
- Updates the job JSON on completion

This keeps the Jac server responsive while long-running GPU jobs execute.

Usage:
  python tools/job_runner.py --job-json <path> --log-file <path> -- <cmd...>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict


def _now() -> float:
    return time.time()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-json", required=True)
    parser.add_argument("--log-file", required=True)
    parser.add_argument("--cwd", default=None)
    parser.add_argument("--", dest="cmd_sep", action="store_true")
    parser.add_argument("cmd", nargs=argparse.REMAINDER)

    args = parser.parse_args()

    job_json = Path(args.job_json).resolve()
    log_file = Path(args.log_file).resolve()

    cmd = list(args.cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]

    if not cmd:
        raise SystemExit("No command provided after --")

    # Load existing job metadata if present
    job = _read_json(job_json)

    job.update(
        {
            "status": "running",
            "started_at": _now(),
            "pid": None,
            "exit_code": None,
            "ended_at": None,
            "command": cmd,
            "log_file": str(log_file),
            "cwd": args.cwd or os.getcwd(),
        }
    )
    _write_json(job_json, job)

    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "w", encoding="utf-8") as lf:
        lf.write("[job_runner] starting job...\n")
        lf.write(f"[job_runner] cmd: {' '.join(cmd)}\n")
        lf.flush()

        proc = subprocess.Popen(
            cmd,
            stdout=lf,
            stderr=subprocess.STDOUT,
            cwd=args.cwd or None,
            env=os.environ.copy(),
        )

        job["pid"] = proc.pid
        _write_json(job_json, job)

        rc = proc.wait()

        job["exit_code"] = int(rc)
        job["ended_at"] = _now()
        job["status"] = "success" if rc == 0 else "failed"
        _write_json(job_json, job)

        lf.write(f"\n[job_runner] finished rc={rc}\n")
        lf.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
