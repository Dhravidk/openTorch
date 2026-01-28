#!/usr/bin/env python3
"""End-to-end smoke test for CGinS (Next.js frontend + Jac backend).

Requires:
  - Jac backend running (default http://localhost:8000)
  - Next frontend running (default http://localhost:3000)

Usage:
  python tools/smoke_http.py
  python tools/smoke_http.py --run-pipeline
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import tempfile
import time
import uuid
import urllib.error
import urllib.request


def http_request(method: str, url: str, data: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def http_json(method: str, url: str, payload: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    status, body = http_request(method, url, data=data, headers={"Content-Type": "application/json"})
    try:
        parsed = json.loads(body.decode("utf-8"))
    except Exception:
        parsed = {"raw": body.decode("utf-8", errors="replace")}
    return status, parsed


def encode_multipart(fields: dict, files: list[tuple[str, str]]):
    boundary = uuid.uuid4().hex
    body = bytearray()

    def add_line(text: str) -> None:
        body.extend(text.encode("utf-8"))
        body.extend(b"\r\n")

    for name, value in fields.items():
        add_line(f"--{boundary}")
        add_line(f'Content-Disposition: form-data; name="{name}"')
        add_line("")
        add_line(str(value))

    for field_name, path in files:
        filename = os.path.basename(path)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        add_line(f"--{boundary}")
        add_line(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'
        )
        add_line(f"Content-Type: {content_type}")
        add_line("")
        with open(path, "rb") as f:
            body.extend(f.read())
        body.extend(b"\r\n")

    add_line(f"--{boundary}--")
    return f"multipart/form-data; boundary={boundary}", bytes(body)


def wait_for_job(frontend: str, project: str, job_id: str, timeout_s: int) -> dict:
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        status, data = http_json("GET", f"{frontend}/api/projects/{project}/jobs/{job_id}")
        if status >= 400:
            raise RuntimeError(f"Job status failed: {status} {data}")
        last = data.get("job") or {}
        state = (last.get("status") or "").lower()
        if state in {"success", "failed", "error", "done"}:
            return last
        time.sleep(2)
    raise TimeoutError(f"Job {job_id} did not finish in {timeout_s}s. Last: {last}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", default=os.getenv("CGINS_FRONTEND_URL", "http://localhost:3000"))
    parser.add_argument("--backend", default=os.getenv("CGINS_BACKEND_URL", "http://localhost:8000"))
    parser.add_argument("--run-pipeline", action="store_true", help="Run full profile->generate->optimize->export")
    args = parser.parse_args()

    frontend = args.frontend.rstrip("/")
    backend = args.backend.rstrip("/")

    # Basic connectivity checks
    status, cfg = http_json("GET", f"{frontend}/api/config")
    if status >= 400:
        raise SystemExit(f"Frontend config failed: {status} {cfg}")

    status, _ = http_request("GET", f"{backend}/walkers")
    if status >= 400:
        raise SystemExit(f"Backend walkers failed: {status}")

    # Build small test artifacts
    try:
        import torch
        import torch.nn as nn
    except Exception as exc:
        raise SystemExit(f"torch is required for the smoke test: {exc}")

    tmp_dir = tempfile.mkdtemp(prefix="cgins_smoke_")
    project_name = f"smoke_{int(time.time())}"
    weights_path = os.path.join(tmp_dir, "weights.pt")
    example_inputs_path = os.path.join(tmp_dir, "example_inputs.pt")

    model = nn.Conv2d(3, 8, kernel_size=3)
    torch.save(model.state_dict(), weights_path)
    x = torch.randn(1, 3, 8, 8)
    torch.save({"args": [x], "kwargs": {}}, example_inputs_path)

    model_code = """import torch
import torch.nn as nn

class Model(nn.Module):
    def __init__(self):
        super().__init__()
        self.layer = nn.Conv2d(3, 8, kernel_size=3)

    def forward(self, x):
        return self.layer(x)


def build_model():
    return Model()
"""

    fields = {
        "projectName": project_name,
        "mode": "A",
        "code": model_code,
    }
    files = [
        ("weightsFile", weights_path),
        ("exampleInputsFile", example_inputs_path),
    ]

    content_type, body = encode_multipart(fields, files)
    status, raw = http_request(
        "POST",
        f"{frontend}/api/projects",
        data=body,
        headers={"Content-Type": content_type},
    )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        payload = {"raw": raw.decode("utf-8", errors="replace")}
    if status >= 400:
        raise SystemExit(f"Create project failed: {status} {payload}")

    status, proj_list = http_json("GET", f"{frontend}/api/projects")
    if status >= 400 or not any(p.get("name") == project_name for p in proj_list.get("projects", [])):
        raise SystemExit(f"Project list missing {project_name}: {proj_list}")

    status, proj_meta = http_json("GET", f"{frontend}/api/projects/{project_name}")
    if status >= 400 or proj_meta.get("project", {}).get("name") != project_name:
        raise SystemExit(f"Project fetch failed: {status} {proj_meta}")

    status, job_start = http_json(
        "POST",
        f"{frontend}/api/projects/{project_name}/jobs",
        {"job_type": "profile"},
    )
    if status >= 400:
        raise SystemExit(f"Start job failed: {status} {job_start}")
    job_id = job_start.get("job", {}).get("job_id")
    if not job_id:
        raise SystemExit(f"Missing job_id in response: {job_start}")

    status, job_info = http_json("GET", f"{frontend}/api/projects/{project_name}/jobs/{job_id}")
    if status >= 400 or job_info.get("job", {}).get("job_id") != job_id:
        raise SystemExit(f"Job fetch failed: {status} {job_info}")

    if args.run_pipeline:
        steps = [
            ("profile", 600),
            ("generate", 900),
            ("optimize", 1200),
            ("export", 600),
        ]
        for job_type, timeout in steps:
            status, started = http_json(
                "POST",
                f"{frontend}/api/projects/{project_name}/jobs",
                {"job_type": job_type},
            )
            if status >= 400:
                raise SystemExit(f"Start {job_type} failed: {status} {started}")
            j_id = started.get("job", {}).get("job_id")
            if not j_id:
                raise SystemExit(f"Missing job_id for {job_type}: {started}")
            final = wait_for_job(frontend, project_name, j_id, timeout)
            if (final.get("status") or "").lower() != "success":
                raise SystemExit(f"{job_type} failed: {final}")

    # Cleanup
    http_json("DELETE", f"{frontend}/api/projects/{project_name}")
    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
