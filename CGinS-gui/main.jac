# CGinS Jac Fullstack Entrypoint
# - Backend walkers live in jac_app/services/cgins_api.jac
# - Frontend is embedded here to avoid cross-file client imports

import from jac_app.services.cgins_api {
    list_projects,
    create_project,
    get_project,
    delete_project,
    get_config,
    save_config,
    list_ops,
    start_job,
    get_job,
    list_bundles,
    run_smoke_test
}

cl {
    # Backend walkers are imported by main.jac; the client can call them via `root spawn ...`.
    # This UI is path-based (WSL-friendly): provide filesystem paths for artifacts.
    
    def _inline_styles() -> str {
        return ":root {\\n  --bg: #0b1020;\\n  --bg2: #0f1730;\\n  --panel: rgba(255, 255, 255, 0.06);\\n  --panel2: rgba(255, 255, 255, 0.08);\\n  --border: rgba(255, 255, 255, 0.12);\\n  --text: rgba(255, 255, 255, 0.92);\\n  --muted: rgba(255, 255, 255, 0.65);\\n  --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, \"Liberation Mono\",\\n    \"Courier New\", monospace;\\n}\\n\\n* {\\n  box-sizing: border-box;\\n}\\n\\nbody {\\n  margin: 0;\\n  font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial,\\n    sans-serif;\\n  color: var(--text);\\n  background: radial-gradient(1200px 800px at 20% 10%, #1b2550 0%, transparent 55%),\\n    radial-gradient(1000px 600px at 90% 30%, #3b1a6b 0%, transparent 55%),\\n    linear-gradient(180deg, var(--bg), var(--bg2));\\n  min-height: 100vh;\\n}\\n\\nbutton,\\ninput,\\ntextarea,\\nselect {\\n  font: inherit;\\n}\\n\\n.app-root {\\n  display: flex;\\n  flex-direction: column;\\n  min-height: 100vh;\\n}\\n\\n.topbar {\\n  display: flex;\\n  align-items: center;\\n  justify-content: space-between;\\n  padding: 14px 18px;\\n  border-bottom: 1px solid var(--border);\\n  background: rgba(0, 0, 0, 0.25);\\n  backdrop-filter: blur(10px);\\n  position: sticky;\\n  top: 0;\\n  z-index: 10;\\n}\\n\\n.brand {\\n  display: flex;\\n  align-items: baseline;\\n  gap: 10px;\\n  cursor: pointer;\\n  user-select: none;\\n}\\n\\n.brand-dot {\\n  width: 10px;\\n  height: 10px;\\n  border-radius: 50%;\\n  background: linear-gradient(90deg, #5ddcff, #3c67e3, #4e00c2);\\n  display: inline-block;\\n}\\n\\n.brand-title {\\n  font-weight: 700;\\n  letter-spacing: 0.2px;\\n}\\n\\n.brand-sub {\\n  font-size: 12px;\\n  color: var(--muted);\\n}\\n\\n.topbar-actions {\\n  display: flex;\\n  gap: 8px;\\n}\\n\\n.nav-btn {\\n  padding: 8px 12px;\\n  border-radius: 10px;\\n  border: 1px solid var(--border);\\n  background: rgba(255, 255, 255, 0.04);\\n  color: var(--text);\\n  cursor: pointer;\\n}\\n\\n.nav-btn.active {\\n  background: rgba(255, 255, 255, 0.10);\\n}\\n\\n.page {\\n  max-width: 1100px;\\n  width: 100%;\\n  margin: 0 auto;\\n  padding: 18px;\\n}\\n\\n.status {\\n  padding: 10px 12px;\\n  border-radius: 12px;\\n  background: rgba(255, 255, 255, 0.08);\\n  border: 1px solid var(--border);\\n  margin-bottom: 14px;\\n}\\n\\n.status.error {\\n  background: rgba(255, 0, 0, 0.12);\\n  border-color: rgba(255, 0, 0, 0.35);\\n}\\n\\n.panel {\\n  padding: 16px;\\n  border-radius: 18px;\\n  background: var(--panel);\\n  border: 1px solid var(--border);\\n}\\n\\n.panel-header {\\n  display: flex;\\n  align-items: flex-start;\\n  justify-content: space-between;\\n  gap: 12px;\\n  margin-bottom: 12px;\\n}\\n\\n.panel-header h2 {\\n  margin: 0;\\n}\\n\\n.panel-actions {\\n  display: flex;\\n  gap: 10px;\\n}\\n\\n.btn {\\n  padding: 8px 12px;\\n  border-radius: 12px;\\n  border: 1px solid var(--border);\\n  background: rgba(255, 255, 255, 0.06);\\n  color: var(--text);\\n  cursor: pointer;\\n}\\n\\n.btn.primary {\\n  background: linear-gradient(90deg, #5ddcff33, #3c67e333, #4e00c233);\\n  border-color: rgba(255, 255, 255, 0.18);\\n}\\n\\n.btn.danger {\\n  background: rgba(255, 0, 0, 0.12);\\n  border-color: rgba(255, 0, 0, 0.35);\\n}\\n\\n.empty {\\n  color: var(--muted);\\n  padding: 10px 0;\\n}\\n\\n.cards {\\n  display: grid;\\n  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));\\n  gap: 12px;\\n}\\n\\n.card {\\n  padding: 14px;\\n  border-radius: 16px;\\n  border: 1px solid var(--border);\\n  background: var(--panel2);\\n}\\n\\n.card.selected {\\n  outline: 2px solid rgba(93, 220, 255, 0.35);\\n}\\n\\n.card-title {\\n  font-weight: 700;\\n  margin-bottom: 8px;\\n}\\n\\n.card-meta {\\n  display: flex;\\n  gap: 8px;\\n  margin-bottom: 12px;\\n}\\n\\n.pill {\\n  display: inline-flex;\\n  align-items: center;\\n  gap: 6px;\\n  padding: 4px 8px;\\n  border-radius: 999px;\\n  border: 1px solid var(--border);\\n  background: rgba(0, 0, 0, 0.18);\\n  font-size: 12px;\\n  color: var(--muted);\\n}\\n\\n.card-actions {\\n  display: flex;\\n  justify-content: flex-end;\\n}\\n\\n.form-grid {\\n  display: grid;\\n  gap: 12px;\\n}\\n\\n.form-row {\\n  display: grid;\\n  gap: 6px;\\n}\\n\\n.form-row label {\\n  color: var(--muted);\\n  font-size: 13px;\\n}\\n\\ninput,\\nselect,\\ntextarea {\\n  border-radius: 12px;\\n  border: 1px solid var(--border);\\n  background: rgba(0, 0, 0, 0.25);\\n  color: var(--text);\\n  padding: 10px 12px;\\n}\\n\\ntextarea {\\n  min-height: 220px;\\n  resize: vertical;\\n  font-family: var(--mono);\\n  font-size: 12px;\\n}\\n\\n.form-actions {\\n  display: flex;\\n  gap: 10px;\\n}\\n\\n.job-actions {\\n  display: flex;\\n  flex-wrap: wrap;\\n  gap: 10px;\\n  margin: 14px 0 10px;\\n}\\n\\n.job {\\n  margin-top: 12px;\\n  border-radius: 16px;\\n  border: 1px solid var(--border);\\n  background: rgba(0, 0, 0, 0.18);\\n  overflow: hidden;\\n}\\n\\n.job-header {\\n  display: flex;\\n  align-items: flex-start;\\n  justify-content: space-between;\\n  padding: 12px;\\n  gap: 10px;\\n  border-bottom: 1px solid var(--border);\\n}\\n\\n.job-title {\\n  font-weight: 700;\\n}\\n\\n.job-meta {\\n  font-size: 12px;\\n  color: var(--muted);\\n}\\n\\n.log {\\n  margin: 0;\\n  padding: 12px;\\n  font-family: var(--mono);\\n  font-size: 12px;\\n  line-height: 1.3;\\n  white-space: pre-wrap;\\n  max-height: 320px;\\n  overflow: auto;\\n}\\n\\n.split {\\n  display: grid;\\n  grid-template-columns: 1fr 1fr;\\n  gap: 14px;\\n  margin-top: 14px;\\n}\\n\\n@media (max-width: 900px) {\\n  .split {\\n    grid-template-columns: 1fr;\\n  }\\n}\\n\\n.split-col h3 {\\n  margin: 0 0 8px;\\n}\\n\\n.table {\\n  border: 1px solid var(--border);\\n  border-radius: 14px;\\n  overflow: hidden;\\n}\\n\\n.row {\\n  display: grid;\\n  grid-template-columns: 1.4fr 0.4fr 0.4fr 0.4fr;\\n  gap: 10px;\\n  padding: 10px 12px;\\n  border-top: 1px solid var(--border);\\n  background: rgba(255, 255, 255, 0.03);\\n}\\n\\n.row.head {\\n  border-top: none;\\n  background: rgba(255, 255, 255, 0.06);\\n  font-weight: 700;\\n}\\n\\n.mono {\\n  font-family: var(--mono);\\n  font-size: 12px;\\n  color: rgba(255, 255, 255, 0.82);\\n}\\n\\n.bundle-list {\\n  display: grid;\\n  gap: 10px;\\n}\\n\\n.bundle {\\n  padding: 10px 12px;\\n  border-radius: 14px;\\n  border: 1px solid var(--border);\\n  background: rgba(255, 255, 255, 0.04);\\n}\\n\\n.bundle-name {\\n  font-weight: 700;\\n  margin-bottom: 6px;\\n}\\n\\n.bundle-path {\\n  color: var(--muted);\\n  word-break: break-all;\\n}\\n";
    }
    
    
    
    
    def: pub App() -> any {
        has page: str = "home";
        has projects: list = [];
        has selectedProject: str = "";
        has status: str = "";
        has didInit: bool = False;
    
        # New project form
        has newName: str = "";
        has newMode: str = "A";
        has newWeightsPath: str = "";
        has newFullModelPath: str = "";
        has newExampleInputsPath: str = "";
        has newModelCode: str = "";
    
        # Settings
        has llmProvider: str = "anthropic";
        has llmModel: str = "claude-opus-4-5-20251101";
        has openaiKey: str = "";
        has anthropicKey: str = "";
        has googleKey: str = "";
    
        # Project view
        has projectMeta: any = None;
        has ops: list = [];
        has bundles: list = [];
        has job: any = None;
    
        async def refreshProjects() -> None {
            res = await root spawn list_projects();
            projects = res.reports[0] or [];
        }
    
        async def loadSettings() -> None {
            res = await root spawn get_config();
            cfg = res.reports[0];
            if cfg {
                llmProvider = cfg.llm_provider or "anthropic";
                llmModel = cfg.llm_model or "claude-opus-4-5-20251101";
                openaiKey = cfg.openai_api_key or "";
                anthropicKey = cfg.anthropic_api_key or "";
                googleKey = cfg.google_api_key or "";
            }
        }
    
        async def refreshProject() -> None {
            if not selectedProject {
                return;
            }
            metaRes = await root spawn get_project(name=selectedProject);
            meta = metaRes.reports[0];
            projectMeta = meta;
    
            opsRes = await root spawn list_ops(project_name=selectedProject);
            ops = opsRes.reports[0] or [];
    
            bRes = await root spawn list_bundles(project_name=selectedProject);
            bundles = bRes.reports[0] or [];
        }
    
        async def refreshJob() -> None {
            if not selectedProject or not job or not job.job_id {
                return;
            }
            jRes = await root spawn get_job(project_name=selectedProject, job_id=job.job_id, tail_lines=400);
            job = jRes.reports[0];
        }
    
        async def openProject(name: str) -> None {
            selectedProject = name;
            page = "project";
            job = None;
            refreshProject();
        }
    
        async def createNewProject() -> None {
            status = "";
            if not newName {
                status = "Project name is required";
                return;
            }
            if not newExampleInputsPath {
                status = "example_inputs_path is required";
                return;
            }
            if newMode == "B" and not newFullModelPath {
                status = "Mode B requires full_model_path (pickled model .pt)";
                return;
            }
    
            res = await root spawn create_project(
                name=newName,
                mode=newMode,
                model_code=newModelCode,
                weights_path=newWeightsPath,
                full_model_path=newFullModelPath,
                example_inputs_path=newExampleInputsPath
            );
    
            out = res.reports[0];
            if out and out.error {
                status = out.error;
                return;
            }
    
            status = "Project created.";
            refreshProjects();
            openProject(newName);
        }
    
        async def deleteSelectedProject() -> None {
            if not selectedProject {
                return;
            }
            if not confirm(f"Delete project '{selectedProject}'? This removes all kernels/logs/export.") {
                return;
            }
            await root spawn delete_project(name=selectedProject);
            selectedProject = "";
            projectMeta = None;
            ops = [];
            bundles = [];
            job = None;
            page = "home";
            refreshProjects();
        }
    
        async def startJob(jobType: str) -> None {
            status = "";
            if not selectedProject {
                return;
            }
            res = await root spawn start_job(project_name=selectedProject, job_type=jobType);
            out = res.reports[0];
            if out and out.error {
                status = out.error;
                return;
            }
            job = out;
            status = f"Started job: {jobType}";
        }
    
        async def saveSettings() -> None {
            res = await root spawn save_config(
                llm_provider=llmProvider,
                llm_model=llmModel,
                openai_api_key=openaiKey,
                anthropic_api_key=anthropicKey,
                google_api_key=googleKey
            );
            out = res.reports[0];
            if out and out.ok {
                status = "Settings saved.";
            }
        }
    
        if not didInit {
            didInit = True;
            refreshProjects();
            loadSettings();
        }
    
        def _navButton(label: str, to: str) -> any {
            return (
                <button
                    className={"nav-btn" + (" active" if page == to else "")}
                    onClick={lambda _e: any -> None { page = to; status = ""; }}
                >
                    {label}
                </button>
            );
        }
    
        return (
            <div className="app-root">
                <style>{_inline_styles()}</style>
                <div className="topbar">
                    <div className="brand" onClick={lambda _e: any -> None { page = "home"; status = ""; }}>
                        <span className="brand-dot" />
                        <span className="brand-title">CGinS</span>
                        <span className="brand-sub">Jac GUI</span>
                    </div>
                    <div className="topbar-actions">
                        {_navButton("Home", "home")}
                        {_navButton("New Project", "new")}
                        {_navButton("Settings", "settings")}
                    </div>
                </div>
    
                <div className="page">
                    {(
                        <div className="status">{status}</div>
                    ) if status else None}
    
                    {(
                        <div className="panel">
                            <div className="panel-header">
                                <h2>Projects</h2>
                                <button className="btn" onClick={lambda _e: any -> None { refreshProjects(); }}>
                                    Refresh
                                </button>
                            </div>
    
                            {(
                                <div className="empty">No projects yet. Click <b>New Project</b> to create one.</div>
                            ) if (projects.length == 0) else None}
    
                            <div className="cards">
                                {projects.map(lambda p: any -> any {
                                    return (
                                        <div className={"card" + (" selected" if p.name == selectedProject else "")} key={p.name}>
                                            <div className="card-title">{p.name}</div>
                                            <div className="card-meta">
                                                <span className="pill">Mode {p.mode}</span>
                                            </div>
                                            <div className="card-actions">
                                                <button className="btn" onClick={lambda _e: any -> None { openProject(p.name); }}>
                                                    Open
                                                </button>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    ) if page == "home" else None}
    
                    {(
                        <div className="panel">
                            <div className="panel-header">
                                <h2>New Project</h2>
                            </div>
    
                            <div className="form-grid">
                                <div className="form-row">
                                    <label>Project name</label>
                                    <input value={newName} onChange={lambda e: any -> None { newName = e.target.value; }} placeholder="my_model" />
                                </div>
    
                                <div className="form-row">
                                    <label>Mode</label>
                                    <select value={newMode} onChange={lambda e: any -> None { newMode = e.target.value; }}>
                                        <option value="A">A — model.py + weights.pt (optional)</option>
                                        <option value="B">B — pickled full_model.pt (torch.save(model))</option>
                                    </select>
                                </div>
    
                                <div className="form-row">
                                    <label>weights.pt path (Mode A, optional)</label>
                                    <input value={newWeightsPath} onChange={lambda e: any -> None { newWeightsPath = e.target.value; }} placeholder="/path/to/weights.pt" />
                                </div>
    
                                <div className="form-row">
                                    <label>full_model.pt path (Mode B required)</label>
                                    <input value={newFullModelPath} onChange={lambda e: any -> None { newFullModelPath = e.target.value; }} placeholder="/path/to/full_model.pt" />
                                </div>
    
                                <div className="form-row">
                                    <label>example_inputs.pt path (required)</label>
                                    <input value={newExampleInputsPath} onChange={lambda e: any -> None { newExampleInputsPath = e.target.value; }} placeholder="/path/to/example_inputs.pt" />
                                </div>
    
                                <div className="form-row form-code">
                                    <label>model.py code (required for Mode A; optional for Mode B unpickling)</label>
                                    <textarea
                                        value={newModelCode}
                                        onChange={lambda e: any -> None { newModelCode = e.target.value; }}
                                        placeholder="Paste your model.py here..."
                                    />
                                </div>
    
                                <div className="form-actions">
                                    <button className="btn primary" onClick={lambda _e: any -> None { createNewProject(); }}>
                                        Create Project
                                    </button>
                                </div>
                            </div>
                        </div>
                    ) if page == "new" else None}
    
                    {(
                        <div className="panel">
                            <div className="panel-header">
                                <h2>Settings</h2>
                            </div>
    
                            <div className="form-grid">
                                <div className="form-row">
                                    <label>LLM Provider</label>
                                    <select value={llmProvider} onChange={lambda e: any -> None { llmProvider = e.target.value; }}>
                                        <option value="anthropic">anthropic</option>
                                        <option value="openai">openai</option>
                                        <option value="gemini">gemini</option>
                                        <option value="ollama">ollama (local)</option>
                                    </select>
                                </div>
    
                                <div className="form-row">
                                    <label>LLM Model</label>
                                    <input value={llmModel} onChange={lambda e: any -> None { llmModel = e.target.value; }} placeholder="claude-opus-4-5-20251101" />
                                </div>
    
                                <div className="form-row">
                                    <label>Anthropic API Key</label>
                                    <input type="password" value={anthropicKey} onChange={lambda e: any -> None { anthropicKey = e.target.value; }} placeholder="ANTHROPIC_API_KEY" />
                                </div>
    
                                <div className="form-row">
                                    <label>OpenAI API Key</label>
                                    <input type="password" value={openaiKey} onChange={lambda e: any -> None { openaiKey = e.target.value; }} placeholder="OPENAI_API_KEY" />
                                </div>
    
                                <div className="form-row">
                                    <label>Google API Key</label>
                                    <input type="password" value={googleKey} onChange={lambda e: any -> None { googleKey = e.target.value; }} placeholder="GOOGLE_API_KEY" />
                                </div>
    
                                <div className="form-actions">
                                    <button className="btn primary" onClick={lambda _e: any -> None { saveSettings(); }}>
                                        Save Settings
                                    </button>
                                    <button className="btn" onClick={lambda _e: any -> None { loadSettings(); status = "Reloaded settings."; }}>
                                        Reload
                                    </button>
                                </div>
                            </div>
                        </div>
                    ) if page == "settings" else None}
    
                    {(
                        <div className="panel">
                            <div className="panel-header">
                                <div>
                                    <h2>Project: {selectedProject}</h2>
                                    {(
                                        <div className="meta">
                                            <span className="pill">Mode {projectMeta.mode}</span>
                                            <span className="pill">Profile ops: {projectMeta.profiler_ops}</span>
                                            <span className="pill">Generated: {projectMeta.generated_ops}</span>
                                            <span className="pill">Optimized: {projectMeta.optimized_ops}</span>
                                            <span className="pill">Bundles: {projectMeta.export_bundles}</span>
                                        </div>
                                    ) if (projectMeta and not projectMeta.error) else None}
                                </div>
                                <div className="panel-actions">
                                    <button className="btn" onClick={lambda _e: any -> None { refreshProject(); }}>
                                        Refresh
                                    </button>
                                    <button className="btn danger" onClick={lambda _e: any -> None { deleteSelectedProject(); }}>
                                        Delete
                                    </button>
                                </div>
                            </div>
    
                            {(
                                <div className="status error">{projectMeta.error}</div>
                            ) if (projectMeta and projectMeta.error) else None}
    
                            <div className="job-actions">
                                <button className="btn" onClick={lambda _e: any -> None { startJob("profile"); }}>
                                    1) Profile
                                </button>
                                <button className="btn" onClick={lambda _e: any -> None { startJob("generate"); }}>
                                    2) Generate
                                </button>
                                <button className="btn" onClick={lambda _e: any -> None { startJob("optimize"); }}>
                                    3) Optimize
                                </button>
                                <button className="btn" onClick={lambda _e: any -> None { startJob("export"); }}>
                                    4) Export
                                </button>
                                <button className="btn primary" onClick={lambda _e: any -> None { startJob("smoke"); }}>
                                    Smoke Test
                                </button>
                            </div>
    
                            {(
                                <div className="job">
                                    <div className="job-header">
                                        <div>
                                            <div className="job-title">Job: {job.job_type} · {job.status}</div>
                                            <div className="job-meta">id: {job.job_id}</div>
                                        </div>
                                        <div className="job-header-actions">
                                            <button className="btn" onClick={lambda _e: any -> None { refreshJob(); }}>
                                                Refresh Job
                                            </button>
                                        </div>
                                    </div>
                                    <pre className="log">{job.log_tail or ""}</pre>
                                </div>
                            ) if job else None}
    
                            <div className="split">
                                <div className="split-col">
                                    <h3>Ops</h3>
                                    <div className="table">
                                        <div className="row head">
                                            <div>Op</div>
                                            <div>Count</div>
                                            <div>Generated</div>
                                            <div>Optimized</div>
                                        </div>
                                        {ops.map(lambda o: any -> any {
                                            return (
                                                <div className="row" key={o.op_id}>
                                                    <div className="mono">{o.function_name}</div>
                                                    <div>{o.count}</div>
                                                    <div>{("✅" if o.generated else "—")}</div>
                                                    <div>{("✅" if o.optimized else "—")}</div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
    
                                <div className="split-col">
                                    <h3>Bundles</h3>
                                    {(
                                        <div className="empty">No bundles yet. Run Export.</div>
                                    ) if (bundles.length == 0) else None}
    
                                    <div className="bundle-list">
                                        {bundles.map(lambda b: any -> any {
                                            return (
                                                <div className="bundle" key={b.name}>
                                                    <div className="bundle-name">{b.name}</div>
                                                    <div className="bundle-path mono">{b.path}</div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            </div>
                        </div>
                    ) if page == "project" else None}
                </div>
            </div>
        );
    }

    def: pub app() -> any {
        return <App />;
    }
}
