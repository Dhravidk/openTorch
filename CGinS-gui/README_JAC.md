# CGinS Jac App (WSL)

This repo now includes a fully working **Jac fullstack app** (UI + backend walkers)
for CGinS projects.

The Jac app lives at the repo root:
- `jac.toml`
- `main.jac`
- `jac_app/...`

## What you can do
- Create a **project**
- Profile a model (captures `torch.nn.functional.*` calls)
- Generate kernels for each op (LLM)
- Optimize kernels for the **current GPU** (auto-detected)
- Export a single-file bundle (`.cgins`)
- Smoke-test the bundle (patches `torch.nn.functional` via `cgins_runtime` and runs forward)

## Prereqs
- WSL2 with NVIDIA GPU / CUDA configured
- Python >= 3.10
- CUDA-enabled PyTorch
- Jac + Jac client tooling (same as `jac-client-playground`)

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Install jac-client dependencies
jac add --cl

# Start the app
jac start
```

Then open:
- `http://localhost:8000/app`

## Next.js UI (recommended)
Run the Jac backend and the Next frontend side-by-side:

```bash
# Backend only
jac start main.jac --no_client

# Frontend
cd cgins-frontend
npm install
npm run dev
```

Open:
- `http://localhost:3000`

### Smoke test
With both servers running:
```bash
cd cgins-frontend
npm run test:smoke
```

To run the full pipeline (profile -> generate -> optimize -> export):
```bash
cd cgins-frontend
python ../tools/smoke_http.py --run-pipeline
```

### Test suite (preflight + pipeline)
From the repo root:
```bash
python tools/test_suite.py
```

With a specific project and full pipeline:
```bash
python tools/test_suite.py --project <name> --pipeline profile,generate,optimize,export,benchmark
```

Optional live OpenAI key probe (uses the configured model):
```bash
python tools/test_suite.py --probe-openai
```

Notes:
- Requires backend and frontend running (uses CGINS_BACKEND_URL and CGINS_FRONTEND_URL).
- Redacts API keys in output and checks provider/model consistency.

## Model inputs
The profiler expects `example_inputs.pt` at:
- `projects/<name>/inputs/example_inputs.pt`

You can create it like:
```python
# example_inputs.py
import torch

x = torch.randn(1, 3, 224, 224)

torch.save({
    "args": [x],
    "kwargs": {},
}, "example_inputs.pt")
```

## Mode A vs Mode B
### Mode A (code + weights)
Provide:
- `model.py` code (paste into UI)
- Optional `weights.pt` path (a state_dict)

Your model code must define either:
- `build_model() -> torch.nn.Module`, or
- `class Model(torch.nn.Module)`

### Mode B (pickled full model)
Provide:
- `full_model.pt` path created via `torch.save(model, "full_model.pt")`
- (Optional but recommended) paste `model.py` containing class definitions if needed for unpickling.

## Pipeline
From the UI:
1. **Profile**
2. **Generate**
3. **Optimize**
4. **Export** (creates `projects/<name>/export/<name>_<timestamp>.cgins`)
5. **Smoke Test**

### Benchmark (Torch vs CGinS bundle)
After **Export**, you can benchmark baseline PyTorch vs the exported bundle:

```bash
python -m src.project.benchmark_project --project-dir projects/<name>
```

This writes `projects/<name>/benchmark.json` and prints a summary with speedup.

If no bundle exists yet, the benchmark will run **baseline-only** (PyTorch) and still
write `benchmark.json` with `bundle_status: "missing"`. Re-run after export to compare.

## Export bundle runtime
A minimal runtime is included:
- `cgins_runtime.apply_bundle("/path/to/bundle.cgins")`

Example one-liner:
```bash
python -c "import glob, cgins_runtime as r; b=sorted(glob.glob('projects/myproj/export/*.cgins'))[-1]; r.apply_bundle(b); import my_app; my_app.main()"
```

(For now, this runtime only patches ops that were profiled from `torch.nn.functional.*` and whose kernels compiled successfully.)
