import json;
import os;
import shutil;
import subprocess;
import sys;
import time;
import uuid;

import from pathlib { Path }

glob PROJECTS_DIR = Path("projects");
glob CONFIG_PATH = Path("cgins_config.json");


def _ensure_dir(p: Path) -> None {
    p.mkdir(parents=True, exist_ok=True);
}


def _read_json(p: Path, default: any) -> any {
    if not p.exists() {
        return default;
    }

    try {
        with open(p, "r", encoding="utf-8") as f {
            return json.load(f);
        }
    } except Exception {
        return default;
    }
}


def _write_json(p: Path, obj: any) -> None {
    _ensure_dir(p.parent);
    with open(p, "w", encoding="utf-8") as f {
        json.dump(obj, f, indent=2);
    }
}


def _now() -> float {
    return time.time();
}


def _sort_last_accessed(p: dict) -> int {
    return p.get("last_accessed_at") or 0;
}


def _sort_function_name(o: dict) -> str {
    return o.get("function_name") or "";
}


def _sort_path_mtime(p: Path) -> float {
    return p.stat().st_mtime;
}


def _sort_bundle_mtime(b: dict) -> int {
    return b.get("mtime") or 0;
}


def _project_dir(name: str) -> Path {
    return PROJECTS_DIR / name;
}


def _default_config() -> dict {
    return {
        "llm_provider": "anthropic",
        "llm_model": "claude-opus-4-5-20251101",
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY", ""),
        "google_api_key": os.getenv("GOOGLE_API_KEY", ""),
    };
}

def _validate_llm_config(cfg: dict) -> any {
    provider = (cfg.get("llm_provider") or "anthropic").strip().lower();
    model = (cfg.get("llm_model") or "").strip().lower();

    if provider in ["openai", "gpt"] {
        if not cfg.get("openai_api_key") {
            return "OpenAI provider selected but OPENAI_API_KEY is empty.";
        }
        if "claude" in model or "gemini" in model {
            return "OpenAI provider selected but model looks like Anthropic/Gemini. Pick a GPT model or switch provider.";
        }
    } elif provider in ["anthropic", "claude"] {
        if not cfg.get("anthropic_api_key") {
            return "Anthropic provider selected but ANTHROPIC_API_KEY is empty.";
        }
        if "gpt" in model or "gemini" in model {
            return "Anthropic provider selected but model looks like OpenAI/Gemini. Pick a Claude model or switch provider.";
        }
    } elif provider in ["gemini", "google"] {
        if not cfg.get("google_api_key") {
            return "Gemini provider selected but GOOGLE_API_KEY is empty.";
        }
        if "gpt" in model or "claude" in model {
            return "Gemini provider selected but model looks like OpenAI/Anthropic. Pick a Gemini model or switch provider.";
        }
    } elif provider in ["ollama"] {
        # local provider; no key needed
        noop = 0;
    } else {
        return f"Unsupported LLM provider: {provider}";
    }

    return None;
}


def _prepare_env(cfg: dict) -> dict {
    env = dict(os.environ);

    provider = (cfg.get("llm_provider") or "anthropic").strip();
    model = (cfg.get("llm_model") or "").strip();

    env["CGINS_LLM_PROVIDER"] = provider;
    if model {
        env["CGINS_LLM_MODEL"] = model;
    }

    # Forward provider keys for child processes
    if cfg.get("openai_api_key") {
        env["OPENAI_API_KEY"] = cfg["openai_api_key"];
    }
    if cfg.get("anthropic_api_key") {
        env["ANTHROPIC_API_KEY"] = cfg["anthropic_api_key"];
    }
    if cfg.get("google_api_key") {
        env["GOOGLE_API_KEY"] = cfg["google_api_key"];
    }

    return env;
}


walker: pub get_config {
    can get with `root entry {
        cfg = _read_json(CONFIG_PATH, _default_config());
        report cfg;
    }
}


walker: pub save_config {
    has llm_provider: str;
    has llm_model: str;
    has openai_api_key: str = "";
    has anthropic_api_key: str = "";
    has google_api_key: str = "";

    can save with `root entry {
        cfg = {
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "openai_api_key": self.openai_api_key,
            "anthropic_api_key": self.anthropic_api_key,
            "google_api_key": self.google_api_key,
        };
        _write_json(CONFIG_PATH, cfg);
        report {"ok": True};
    }
}


walker: pub list_projects {
    can list with `root entry {
        _ensure_dir(PROJECTS_DIR);

        projs = [];
        for d in PROJECTS_DIR.iterdir() {
            if not d.is_dir() {
                continue;
            }
            # Skip internal upload cache or hidden folders
            if d.name.startswith("_") or d.name.startswith(".") {
                continue;
            }
            meta_path = d / "project.json";
            meta = _read_json(meta_path, {});
            if not meta {
                meta = {"name": d.name, "mode": "A", "created_at": None};
            }
            projs.append(meta);
        }

        projs.sort(key=_sort_last_accessed, reverse=True);
        report projs;
    }
}


walker: pub get_project {
    has name: str;

    can get with `root entry {
        pdir = _project_dir(self.name);
        meta = _read_json(pdir / "project.json", {});
        if not meta {
            report {"error": f"Project not found: {self.name}"};
            return;
        }

        # Derived status
        profiler_summary = _read_json(pdir / "profiler" / "summary.json", {});
        gen_dir = pdir / "kernels" / "generated" / "individual_op_kernels";
        opt_dir = pdir / "kernels" / "optimized" / "individual_op_kernels";
        export_dir = pdir / "export";

        meta["profiler_ops"] = len((profiler_summary.get("ops") or {}).keys());
        meta["generated_ops"] = len([x for x in gen_dir.glob("*") if (x / "kernel.cu").exists()]);
        meta["optimized_ops"] = len([x for x in opt_dir.glob("*") if (x / "kernel.cu").exists()]);
        meta["export_bundles"] = len([x for x in export_dir.glob("*.cgins")]);

        # Touch last accessed
        meta["last_accessed_at"] = _now();
        _write_json(pdir / "project.json", meta);

        report meta;
    }
}


walker: pub delete_project {
    has name: str;

    can delete with `root entry {
        pdir = _project_dir(self.name);
        if pdir.exists() {
            shutil.rmtree(pdir);
        }
        report {"ok": True};
    }
}


walker: pub create_project {
    has name: str;
    has mode: str = "A";  # A=code+weights, B=pickled full model
    has model_code: str = "";
    has weights_path: str = "";
    has full_model_path: str = "";
    has example_inputs_path: str = "";

    can create with `root entry {
        _ensure_dir(PROJECTS_DIR);

        if not self.name {
            report {"error": "Project name is required"};
            return;
        }

        pdir = _project_dir(self.name);
        if pdir.exists() {
            report {"error": f"Project already exists: {self.name}"};
            return;
        }

        if self.mode == "B" and not self.full_model_path {
            report {"error": "Mode B requires full_model_path (pickled full model .pt)"};
            return;
        }

        model_dir = pdir / "model";
        inputs_dir = pdir / "inputs";

        _ensure_dir(model_dir);
        _ensure_dir(inputs_dir);
        _ensure_dir(pdir / "profiler");
        _ensure_dir(pdir / "kernels" / "generated");
        _ensure_dir(pdir / "kernels" / "optimized");
        _ensure_dir(pdir / "jobs");
        _ensure_dir(pdir / "logs");
        _ensure_dir(pdir / "export");

        # Save model code (Mode A required, Mode B optional for unpickling)
        code = self.model_code or "";
        if code {
            with open(model_dir / "model.py", "w", encoding="utf-8") as f {
                f.write(code);
            }
        } else {
            # Create a stub to guide user
            with open(model_dir / "model.py", "w", encoding="utf-8") as f {
                f.write("""\
import torch

# Mode A expectation:
# - define build_model() -> nn.Module, or define a Model(nn.Module) class.

class Model(torch.nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self, *args, **kwargs):
        raise NotImplementedError("Implement forward")


def build_model():
    return Model()
""");
            }
        }

        # Copy artifacts by path (WSL-friendly)
        if self.weights_path {
            try {
                shutil.copy(self.weights_path, model_dir / "weights.pt");
            } except Exception as e {
                report {"error": f"Failed to copy weights_path: {e}"};
                return;
            }
        }

        if self.full_model_path {
            try {
                shutil.copy(self.full_model_path, model_dir / "full_model.pt");
            } except Exception as e {
                report {"error": f"Failed to copy full_model_path: {e}"};
                return;
            }
        }

        if self.example_inputs_path {
            try {
                shutil.copy(self.example_inputs_path, inputs_dir / "example_inputs.pt");
            } except Exception as e {
                report {"error": f"Failed to copy example_inputs_path: {e}"};
                return;
            }
        } else {
            report {"error": "example_inputs_path is required"};
            return;
        }

        meta = {
            "name": self.name,
            "mode": self.mode,
            "created_at": _now(),
            "last_accessed_at": _now(),
        };
        _write_json(pdir / "project.json", meta);

        report {"ok": True, "project": meta};
    }
}


walker: pub list_ops {
    has project_name: str;

    can list with `root entry {
        pdir = _project_dir(self.project_name);
        summary = _read_json(pdir / "profiler" / "summary.json", {});
        ops_map = summary.get("ops") or {};
        ops = [];

        gen_base = pdir / "kernels" / "generated" / "individual_op_kernels";
        opt_base = pdir / "kernels" / "optimized" / "individual_op_kernels";

        for op_id in ops_map.keys() {
            info = ops_map.get(op_id) or {};
            gen_ok = (gen_base / op_id / "kernel.cu").exists();
            opt_ok = (opt_base / op_id / "kernel.cu").exists();
            ops.append({
                "op_id": op_id,
                "function_name": info.get("function_name"),
                "count": info.get("count"),
                "generated": gen_ok,
                "optimized": opt_ok,
            });
        }

        ops.sort(key=_sort_function_name);
        report ops;
    }
}


walker: pub start_job {
    has project_name: str;
    has job_type: str;  # profile|generate|optimize|export|benchmark|smoke

    can start with `root entry {
        pdir = _project_dir(self.project_name);
        if not pdir.exists() {
            report {"error": f"Project not found: {self.project_name}"};
            return;
        }

        job_id = str(uuid.uuid4());
        job_dir = pdir / "jobs";
        log_dir = pdir / "logs";
        _ensure_dir(job_dir);
        _ensure_dir(log_dir);

        job_json = job_dir / f"{job_id}.json";
        log_file = log_dir / f"{self.job_type}-{job_id}.log";

        cfg = _read_json(CONFIG_PATH, _default_config());
        if self.job_type in ["generate", "optimize"] {
            err = _validate_llm_config(cfg);
            if err {
                report {"error": err};
                return;
            }
        }
        env = _prepare_env(cfg);

        py = sys.executable;
        repo_root = Path.cwd();

        if self.job_type == "profile" {
            cmd = [py, "-m", "src.project.profile_project", "--project-dir", str(pdir)];
        } elif self.job_type == "generate" {
            cmd = [
                py, "-m", "src.generator.main",
                str(pdir / "profiler" / "individual_ops"),
                "--output-base", str(pdir / "kernels" / "generated"),
            ];
        } elif self.job_type == "optimize" {
            cmd = [
                py, "-m", "src.optimizer.optimize_ops",
                str(pdir / "profiler" / "individual_ops"),
                "--generated-base", str(pdir / "kernels" / "generated" / "individual_op_kernels"),
                "--optimized-base", str(pdir / "kernels" / "optimized" / "individual_op_kernels"),
                "--model", cfg.get("llm_model", "claude-opus-4-5-20251101"),
            ];
        } elif self.job_type == "export" {
            cmd = [py, "-m", "src.project.export_bundle", "--project-dir", str(pdir)];
        } elif self.job_type == "benchmark" {
            cmd = [py, "-m", "src.project.benchmark_project", "--project-dir", str(pdir)];
        } elif self.job_type == "smoke" {
            bundles = sorted((pdir / "export").glob("*.cgins"), key=_sort_path_mtime, reverse=True);
            if not bundles {
                report {"error": "No .cgins bundle found. Run export first."};
                return;
            }
            cmd = [
                py, "-m", "src.project.run_with_bundle",
                "--project-dir", str(pdir),
                "--bundle", str(bundles[0]),
            ];
        } else {
            report {"error": f"Unknown job_type: {self.job_type}"};
            return;
        }

        _write_json(job_json, {
            "job_id": job_id,
            "project": self.project_name,
            "job_type": self.job_type,
            "status": "queued",
            "created_at": _now(),
            "log_file": str(log_file),
        });

        runner = repo_root / "tools" / "job_runner.py";
        runner_cmd = [
            py,
            str(runner),
            "--job-json", str(job_json),
            "--log-file", str(log_file),
            "--cwd", str(repo_root),
            "--",
        ] + cmd;

        subprocess.Popen(runner_cmd, env=env);

        report {
            "ok": True,
            "job_id": job_id,
            "job_type": self.job_type,
            "status": "queued",
            "job_json": str(job_json),
            "log_file": str(log_file),
            "command": cmd,
        };
    }
}


walker: pub get_job {
    has project_name: str;
    has job_id: str;
    has tail_lines: int = 200;

    can get with `root entry {
        pdir = _project_dir(self.project_name);
        job_json = pdir / "jobs" / f"{self.job_id}.json";
        job = _read_json(job_json, {});

        log_text = "";
        log_file_str = job.get("log_file", "");
        if log_file_str {
            log_file = Path(log_file_str);
            if log_file.exists() {
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f {
                    lines = f.readlines();
                }
                start = max(0, len(lines) - int(self.tail_lines));
                log_text = "".join(lines[start:]);
            }
        }

        job["log_tail"] = log_text;
        report job;
    }
}


walker: pub list_bundles {
    has project_name: str;

    can list with `root entry {
        pdir = _project_dir(self.project_name);
        export_dir = pdir / "export";
        _ensure_dir(export_dir);

        bundles = [];
        for p in export_dir.glob("*.cgins") {
            bundles.append({"name": p.name, "path": str(p), "mtime": p.stat().st_mtime});
        }

        bundles.sort(key=_sort_bundle_mtime, reverse=True);
        report bundles;
    }
}


walker: pub run_smoke_test {
    has project_name: str;

    can run with `root entry {
        r = start_job(project_name=self.project_name, job_type="smoke") spawn root;
        report r.reports[0];
    }
}
