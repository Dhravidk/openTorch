# Jac Conversion Skill Pack for a Codex-style Agent

This is a practical “skill doc” you can drop into a Codex/agent setup so it can reliably **write Jac** and **migrate an existing application to Jac**.

It is grounded in patterns and tooling found in these repos:
- `jaseci-main/` (Jac language + CLI + jac-client + jac-scale)
- `jac-client-playground-main/` (many small Jac + jac-client examples)
- `Agentic-AI-main/` (real apps written in Jac: translator, jac-gpt-fullstack, etc.)

---

## 0) Prime directive

When converting an application to Jac:

1. **Make it run first** (even if not yet “idiomatic”).
2. Then refactor into **nodes/edges/walkers** where it adds value.
3. Preserve behavior by continuously running:
   - `jac format . --fix`
   - `jac check ...`
   - `jac test ...`
   - `jac start ...` (and hit endpoints)

If you’re unsure about syntax, do *not* invent it. Instead, look up a known-good example in the reference repos (see “Reference gold mines” below).

---

## 1) What Jac building blocks map to

### 1.1 Nodes = persistent domain objects (graph-native)
Use `node` for entities you want to store and connect.

```jac
node User {
    has email: str;
    has name: str = "";
}
```

### 1.2 Edges = relationships between nodes
Use `edge` when the relationship itself matters (type, metadata, direction).

```jac
edge Owns {}
```

### 1.3 Walkers = “controllers / jobs / workflows”
Use `walker` to implement operations that traverse/modify the graph, or act as API endpoints.

Key idioms:
- `can ... with \`root entry { ... }` = entrypoint logic
- `report ...;` = return values (API response data)

```jac
walker:pub create_user {
    has email: str;
    has name: str = "";

    can create with `root entry {
        new_user = (here ++> User(email=self.email, name=self.name))[0];
        report {"id": str(new_user.__jac__.id), "email": new_user.email, "name": new_user.name};
    }
}
```

> Note on `here ++> Node(...)`: in multiple examples, `++>` yields a list of created nodes. Index `[0]` if you want the single created node.

### 1.4 `with entry { ... }` = executable entrypoint
Great for local smoke tests, data seeding, or quick demos.

```jac
with entry {
    resp = root spawn create_user(email="a@b.com", name="Alice");
    print(resp.reports);
}
```

### 1.5 Client-side Jac (jac-client) = `.cl.jac` or `cl { ... }`
- `.jac` = server-side
- `.cl.jac` = client-side
- or mix both using `cl { ... }` blocks.

Client calls backend walkers using **`root spawn`** (often inside an `async def` handler).

```jac
# app.cl.jac
import from react { useEffect }

def:pub app() -> any {
    has todos: list = [];

    useEffect(lambda -> None {
        async def load() -> None {
            resp = await root spawn read_todos();
            todos = resp.reports;
        }
        load();
    }, []);

    return <div>{todos.length}</div>;
}
```

---

## 2) Core CLI commands the agent should use

These are present in the Jac CLI and show up in the repos’ docs and tooling:

### 2.1 Create a project

```bash
jac create my-app
# or fullstack scaffold:
jac create --use client my-app
```

### 2.2 Run / Start server

```bash
jac run src/app.jac
jac start src/app.jac
```

With jac-scale installed, `jac start` uses a FastAPI server and exposes Swagger at `/docs`.

### 2.3 Convert Python → Jac (bootstrap a migration)

```bash
jac py2jac some_module.py > some_module.jac
```

Typical workflow:
1) convert a file,
2) move it into the Jac project,
3) run formatter and type checker.

### 2.4 Format, typecheck, test

```bash
jac format . --fix
jac check src/app.jac
jac test .
```

---

## 3) Recommended migration strategy (works in practice)

### Phase A — Inventory & boundaries
Agent checklist:
- Identify languages: Python? JS/TS? both?
- Identify entrypoints: CLI, REST API, cron jobs, workers.
- Identify domain entities (models) and storage.
- Identify endpoints and request/response schemas.

Output artifact:
- A **mapping document** listing:
  - Models → proposed `node`/`obj`
  - Endpoints → proposed `walker`
  - Background tasks → proposed `walker` or `with entry` runner

### Phase B — Make it run (minimal Jac wrapper)
Goal: get a working Jac project quickly.

Options:

**Option 1: Python-heavy codebase (fastest)**
- Use `jac py2jac` on modules to get valid `.jac` quickly.
- Keep complex legacy logic as inline Python blocks using `::py:: ... ::py::`.
- Wrap old controller functions with walkers.

**Option 2: Fresh Jac-native rewrite**
- Model domain as nodes/edges.
- Rewrite flows as walkers.

### Phase C — Convert “API controllers” into walkers
Default `jac start` exposes walkers at:
- `POST /walker/<walker_name>` (spawn on root)
- `POST /walker/<walker_name>/{node}` (spawn on a specific node)

Conversion pattern:
- **Request body** → `has` fields on the walker
- **Response** → `report` dicts/lists
- **Database row** → `node` (or keep external DB temporarily)

### Phase D — Replace global state with graph state
Common replacements:
- global dict cache → nodes connected to `root`
- relational join tables → edges
- “current user” → connect user root or store user id in walker inputs (auth later)

### Phase E — Client migration (if needed)
If you have an existing React app:
- Start with `jac create --use client`.
- Move UI piece-by-piece into `.cl.jac` components.
- Replace `fetch/axios` with `root spawn <walker>()`.

---

## 4) Mapping table (old app → Jac)

| Typical app concept | Jac target | Notes |
|---|---|---|
| Data model / ORM class | `node` (persistent) or `obj` (non-graph) | Use `node` if you want graph storage and traversal |
| Controller route handler | `walker` | Inputs become `has` fields; output via `report` |
| Service class | `obj` or `node` with `def` methods | If stateful & persistent, prefer `node` |
| Background job / task runner | `walker` + `with entry` scheduler | Can be triggered by `with entry` for local dev |
| Relationship / foreign key | `edge` + traversal | Use edge types to encode semantics |
| In-memory cache | nodes attached to `root` (or keep Python cache short-term) | Graph becomes the "database" |
| REST GET /items | still a walker (POST endpoint) | Jac server endpoints are POST by default; treat as RPC |
| React component | `def` in `.cl.jac` or `cl {}` | `has` inside component = reactive state |

---

## 5) Templates the agent should reuse

### 5.1 CRUD-like “list” walker

```jac
node Item {
    has name: str;
}

walker:pub list_items {
    can list with `root entry {
        for item in [-->](`?Item) {
            report {"id": str(item.__jac__.id), "name": item.name};
        }
    }
}
```

### 5.2 Lookup-by-id walker (using Jac internal ids)

```jac
walker:pub get_item {
    has item_id: str;

    can get with `root entry {
        for item in [-->](`?Item) {
            if str(item.__jac__.id) == self.item_id {
                report {"id": self.item_id, "name": item.name};
                return;
            }
        }
        report {"error": "not_found", "id": self.item_id};
    }
}
```

### 5.3 Client call pattern

```jac
# app.cl.jac
import from react { useEffect }

def:pub app() -> any {
    has items: list = [];

    useEffect(lambda -> None {
        async def load() -> None {
            resp = await root spawn list_items();
            items = resp.reports;
        }
        load();
    }, []);

    return <div>
        {items.map(lambda it: any -> any { return <div key={it.id}>{it.name}</div>; })}
    </div>;
}
```

---

## 6) “Reference gold mines” for the agent

When you need a known-good example, search these:

### Jac language + CLI
- `jaseci-main/jac/jaclang/cli/commands/transform.jac` (shows `py2jac`, `jac2py`, `js`)

### jac-client (frontend)
- `jaseci-main/jac-client/README.md`
- `jaseci-main/jac-client/jac_client/docs/file-system/backend-frontend.md`

### Full-stack app examples
- `jaseci-main/jac-scale/examples/todo/src/app.jac` (simple fullstack)
- `Agentic-AI-main/translator/app.jac` + `app.cl.jac` (LLM + UI)
- `Agentic-AI-main/jac-gpt-fullstack/` (large reference app)

### Many small syntax examples
- `jac-client-playground-main/jac_playground/examples/` (basic + object-spatial + more)

---

## 7) Validation checklist (agent must run this often)

Before declaring a migration step “done”:
- `jac format . --fix`
- `jac check <entry file>`
- `jac test .` (if tests exist)
- `jac start <entry file>` and confirm:
  - `/docs` loads (if running with jac-scale)
  - target walkers appear in docs
  - a sample request works and returns expected `reports`

Also confirm:
- Response shapes are what the client expects (`reports` can be nested lists if you `report` a list).

---

## 8) Practical “don’t get stuck” rules

- If the legacy app is complex, start by wrapping it:
  - Keep core logic in Python via imports or `::py::` blocks.
  - Build Jac walkers that call that logic.
  - Only then refactor the internals to nodes/edges.

- Prefer **small, safe steps**:
  - convert one endpoint at a time,
  - ensure it runs,
  - then proceed.

- Don’t fight HTTP semantics early:
  - Jac walkers are exposed as POST endpoints; treat them as RPC.

