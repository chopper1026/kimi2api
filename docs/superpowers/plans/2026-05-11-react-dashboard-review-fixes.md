# React Dashboard Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the React dashboard refactor regressions found in review: static path traversal, misleading token success states, missing built-dashboard behavior, lint failures, favicon mismatch, and stale documentation.

**Architecture:** Keep the FastAPI backend as the owner of `/admin/api/*` JSON and SPA file serving. Add small, testable helpers for dashboard static file resolution so security behavior is covered without depending on Vite build artifacts. Keep React changes focused on API result handling and lint-clean component/hook structure.

**Tech Stack:** FastAPI, pytest/TestClient, React 19, Vite, TypeScript, ESLint, Ruff.

---

## File Structure

- Modify `app/main.py`: add safe SPA path resolution, register `/admin` fallback even when `dist` is absent, optionally accept `static_dir` for focused tests.
- Modify `app/dashboard/api_routes.py`: remove dead imports; return error HTTP statuses for token operation failures.
- Modify `web/src/pages/TokenPage.tsx`: treat `{ success: false }` API bodies as failures.
- Modify `web/src/hooks/use-polling.ts`: avoid ref mutation during render or simplify callback dependencies.
- Modify `web/src/pages/LogDetailPage.tsx`: replace mutable JSON parsing variables with helper functions.
- Modify `web/src/components/ui/button.tsx` and `web/src/components/ui/badge.tsx`: split exported variant helpers into non-component files or adjust exports.
- Modify `web/eslint.config.js`: if needed, disable only `react-hooks/set-state-in-effect` with a comment explaining data-fetch-on-mount usage.
- Modify `web/index.html`: point favicon to an actually served URL.
- Modify `README.md` and `web/README.md`: document React/Vite build and local dev flow.
- Modify or create tests:
  - `tests/test_dashboard_spa.py`
  - `tests/test_public_routes.py`
  - `tests/test_token_management.py`
  - remove unused imports from touched tests.

---

### Task 1: Block SPA Path Traversal

**Files:**
- Modify: `app/main.py`
- Create: `tests/test_dashboard_spa.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_dashboard_spa.py`:

```python
from fastapi.testclient import TestClient

from app.main import _safe_spa_file_path, create_app


def test_safe_spa_file_path_rejects_traversal(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    outside = tmp_path / "secret.py"
    outside.write_text("SECRET = True", encoding="utf-8")

    assert _safe_spa_file_path(str(dist), "../secret.py") is None
    assert _safe_spa_file_path(str(dist), "%2e%2e/secret.py") is None


def test_safe_spa_file_path_allows_files_inside_dist(tmp_path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    asset = assets / "app.js"
    asset.write_text("console.log('ok')", encoding="utf-8")

    assert _safe_spa_file_path(str(dist), "assets/app.js") == str(asset.resolve())


def test_admin_traversal_serves_no_source_file(tmp_path):
    static_dir = tmp_path / "static"
    dist = static_dir / "dist"
    dist.mkdir(parents=True)
    (static_dir / "favicon.svg").write_text("<svg />", encoding="utf-8")
    (dist / "index.html").write_text("<div id=\"root\"></div>", encoding="utf-8")

    client = TestClient(create_app(initialize=False, static_dir=str(static_dir)))
    response = client.get("/admin/%2e%2e/%2e%2e/main.py")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "import os" not in response.text
    assert '<div id="root"></div>' in response.text
```

- [ ] **Step 2: Run tests to verify the security regression**

Run:

```bash
uv run pytest tests/test_dashboard_spa.py -q
```

Expected before implementation: import or assertion failure because `_safe_spa_file_path` and `static_dir` injection do not exist.

- [ ] **Step 3: Implement safe path resolution**

In `app/main.py`, add:

```python
from urllib.parse import unquote
```

Add helper near the other private helpers:

```python
def _safe_spa_file_path(dist_dir: str, requested_path: str) -> Optional[str]:
    root = os.path.realpath(dist_dir)
    decoded_path = unquote(requested_path).lstrip("/")
    candidate = os.path.realpath(os.path.join(root, decoded_path))
    if candidate == root or not candidate.startswith(root + os.sep):
        return None
    if not os.path.isfile(candidate):
        return None
    return candidate
```

Change the app factory signature and static dir selection:

```python
def create_app(initialize: bool = True, static_dir: Optional[str] = None) -> FastAPI:
    ...
    _static_dir = static_dir or os.path.join(os.path.dirname(__file__), "static")
```

Update `spa_fallback`:

```python
safe_file = _safe_spa_file_path(_dist_dir, path)
if safe_file:
    return FileResponse(safe_file)
index_path = os.path.join(_dist_dir, "index.html")
if os.path.isfile(index_path):
    return FileResponse(index_path)
return HTMLResponse("Dashboard not built. Run: cd web && npm run build", status_code=503)
```

- [ ] **Step 4: Verify path traversal is blocked**

Run:

```bash
uv run pytest tests/test_dashboard_spa.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Add a manual smoke check**

Run:

```bash
uv run python - <<'PY'
from fastapi.testclient import TestClient
from app.main import create_app
client = TestClient(create_app(initialize=False))
for path in ["/admin/%2e%2e/%2e%2e/main.py", "/admin/%2e%2e/%2e%2e/config.py"]:
    r = client.get(path)
    print(path, r.status_code, r.headers.get("content-type"), "import os" in r.text)
PY
```

Expected after implementation: neither response exposes Python source; the final printed boolean is `False`.

---

### Task 2: Return a Useful Dashboard Response When `dist` Is Missing

**Files:**
- Modify: `app/main.py`
- Modify: `tests/test_dashboard_spa.py`

- [ ] **Step 1: Add a failing test**

Append to `tests/test_dashboard_spa.py`:

```python
def test_admin_returns_build_hint_when_dist_missing(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "favicon.svg").write_text("<svg />", encoding="utf-8")

    client = TestClient(create_app(initialize=False, static_dir=str(static_dir)))
    response = client.get("/admin")

    assert response.status_code == 503
    assert "Dashboard not built" in response.text
```

- [ ] **Step 2: Run the focused test**

Run:

```bash
uv run pytest tests/test_dashboard_spa.py::test_admin_returns_build_hint_when_dist_missing -q
```

Expected before implementation: 404, because the route is only registered when `dist` exists.

- [ ] **Step 3: Register the fallback route unconditionally**

In `app/main.py`, keep `/assets` mounted only if the assets dir exists, but move `@app.get("/admin/{path:path}")` outside the `if os.path.isdir(_dist_dir)` block.

Use this structure:

```python
_dist_dir = os.path.join(_static_dir, "dist")
_assets_dir = os.path.join(_dist_dir, "assets")
if os.path.isdir(_assets_dir):
    app.mount("/assets", StaticFiles(directory=_assets_dir), name="spa-assets")

@app.get("/admin/{path:path}", include_in_schema=False)
async def spa_fallback(path: str):
    if path.startswith("api/"):
        return JSONResponse({"error": "Not found"}, status_code=404)
    safe_file = _safe_spa_file_path(_dist_dir, path)
    if safe_file:
        return FileResponse(safe_file)
    index_path = os.path.join(_dist_dir, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return HTMLResponse(
        "Dashboard not built. Run: cd web && npm run build",
        status_code=503,
    )
```

- [ ] **Step 4: Verify missing-dist behavior**

Run:

```bash
uv run pytest tests/test_dashboard_spa.py -q
```

Expected: all dashboard SPA tests pass.

---

### Task 3: Make Token Save/Refresh Failures Visible

**Files:**
- Modify: `app/dashboard/api_routes.py`
- Modify: `web/src/pages/TokenPage.tsx`
- Modify: `tests/test_token_management.py`

- [ ] **Step 1: Write backend failure tests**

Add to `tests/test_token_management.py`:

```python
def test_admin_token_save_empty_token_returns_400(authenticated_admin_client):
    session = authenticated_admin_client.get("/admin/api/session")
    csrf = session.json()["csrf_token"]

    response = authenticated_admin_client.post(
        "/admin/api/token",
        json={"raw_token": ""},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    assert response.json()["success"] is False
    assert response.json()["error"] == "Token 不能为空"
```

If there is no existing no-token refresh test, add:

```python
def test_admin_token_refresh_without_token_returns_400(authenticated_admin_client):
    session = authenticated_admin_client.get("/admin/api/session")
    csrf = session.json()["csrf_token"]

    response = authenticated_admin_client.post(
        "/admin/api/token/refresh",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 400
    assert response.json()["success"] is False
    assert response.json()["error"] == "请先保存 Token"
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
uv run pytest tests/test_token_management.py::test_admin_token_save_empty_token_returns_400 tests/test_token_management.py::test_admin_token_refresh_without_token_returns_400 -q
```

Expected before implementation: status code is 200.

- [ ] **Step 3: Return proper HTTP status codes**

In `app/dashboard/api_routes.py`, update failures:

```python
if not raw_token:
    return JSONResponse(
        {"success": False, "error": "Token 不能为空", "token": token_info()},
        status_code=400,
    )
```

For save exceptions:

```python
except Exception as exc:
    return JSONResponse(
        {"success": False, "error": f"Token 保存失败: {exc}", "token": token_info()},
        status_code=500,
    )
```

For refresh without a token:

```python
except RuntimeError:
    return JSONResponse(
        {"success": False, "error": "请先保存 Token", "token": token_info()},
        status_code=400,
    )
```

- [ ] **Step 4: Add defensive frontend success checks**

In `web/src/pages/TokenPage.tsx`, after `api.refreshToken()`:

```tsx
if (!result.success) {
  throw new Error(result.error || "刷新失败")
}
setTokenInfo(result.token)
setRefreshSuccess(true)
```

After `api.saveToken(...)`:

```tsx
if (!result.success) {
  throw new Error(result.error || "保存失败")
}
setTokenInfo(result.token)
setSaveSuccess(true)
```

- [ ] **Step 5: Verify token behavior**

Run:

```bash
uv run pytest tests/test_token_management.py -q
npm run build
```

Expected: token tests pass and frontend builds.

---

### Task 4: Restore Ruff and Frontend Lint Cleanliness

**Files:**
- Modify: `app/dashboard/api_routes.py`
- Modify: `tests/test_dashboard_auth.py`
- Modify: `tests/test_token_management.py`
- Modify: `web/src/hooks/use-polling.ts`
- Modify: `web/src/pages/LogDetailPage.tsx`
- Modify: `web/src/components/ui/button.tsx`
- Modify: `web/src/components/ui/badge.tsx`
- Create: `web/src/components/ui/button-variants.ts`
- Create: `web/src/components/ui/badge-variants.ts`
- Optionally modify: `web/eslint.config.js`

- [ ] **Step 1: Remove unused Python imports**

Remove:

```python
import json
from . import view_models
```

from `app/dashboard/api_routes.py`.

Remove unused `import re` from:

```text
tests/test_dashboard_auth.py
tests/test_token_management.py
```

- [ ] **Step 2: Split React variant exports**

Create `web/src/components/ui/button-variants.ts`:

```ts
import { cva } from "class-variance-authority"

export const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-lg border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground [a]:hover:bg-primary/80",
        outline:
          "border-border bg-background hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80 aria-expanded:bg-secondary aria-expanded:text-secondary-foreground",
        ghost:
          "hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:hover:bg-muted/50",
        destructive:
          "bg-destructive/10 text-destructive hover:bg-destructive/20 focus-visible:border-destructive/40 focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:hover:bg-destructive/30 dark:focus-visible:ring-destructive/40",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default:
          "h-8 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        icon: "size-8",
        "icon-xs":
          "size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
)
```

Then import it from `button.tsx` and export only `Button` from `button.tsx`.

Do the same for `badgeVariants` in `web/src/components/ui/badge-variants.ts`, then export only `Badge` from `badge.tsx`.

- [ ] **Step 3: Fix `use-polling` ref lint**

Prefer a dependency-based callback:

```ts
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
  enabled = true,
) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setError(null)
      const result = await fetcher()
      setData(result)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "请求失败"
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [fetcher])

  useEffect(() => {
    if (!enabled) return
    void refresh()
    const timer = setInterval(() => {
      void refresh()
    }, intervalMs)
    return () => clearInterval(timer)
  }, [intervalMs, enabled, refresh])

  return { data, loading, error, refresh }
}
```

- [ ] **Step 4: Fix `LogDetailPage` mutable parse lint**

Add helper:

```tsx
function parseJsonObject(value: string): Record<string, unknown> | null {
  if (!value) return null
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed
      : null
  } catch {
    return null
  }
}
```

Replace mutable assignments with:

```tsx
const parsedHeaders = parseJsonObject(data.request_headers)
const parsedRespHeaders = parseJsonObject(data.response_headers)
```

- [ ] **Step 5: Decide on `set-state-in-effect` rule**

If `npm run lint` still reports `react-hooks/set-state-in-effect` for async data loading, disable only that rule in `web/eslint.config.js`:

```js
rules: {
  "react-hooks/set-state-in-effect": "off",
},
```

Rationale: these effects intentionally start async dashboard API reads on mount; the rule is too broad for this local data-fetching pattern.

- [ ] **Step 6: Verify lint**

Run:

```bash
uv run ruff check .
npm run lint
```

Expected: both commands exit 0.

---

### Task 5: Fix Favicon Route Mismatch

**Files:**
- Modify: `web/index.html`
- Modify: `tests/test_public_routes.py`

- [ ] **Step 1: Add a route expectation**

Either choose `/favicon.ico` in HTML or add a backend `/favicon.svg` route. Prefer the simpler HTML fix.

Update `tests/test_public_routes.py` only if you want to assert both served routes. Existing `/favicon.ico` test can remain.

- [ ] **Step 2: Point HTML to the existing route**

In `web/index.html`, change:

```html
<link rel="icon" href="/favicon.svg" type="image/svg+xml" />
```

to:

```html
<link rel="icon" href="/favicon.ico" type="image/svg+xml" />
```

- [ ] **Step 3: Verify**

Run:

```bash
npm run build
uv run pytest tests/test_public_routes.py -q
```

Expected: build succeeds and favicon route test passes.

---

### Task 6: Update Developer Documentation

**Files:**
- Modify: `README.md`
- Modify: `web/README.md`

- [ ] **Step 1: Update root README local setup**

In `README.md`, under development commands, include:

```bash
uv sync --group dev
cd web && npm ci && npm run build
cd ..
uv run pytest
uv run ruff check .
cd web && npm run lint && cd ..
uv run python run.py
```

Also document local frontend dev:

```text
For Vite development, run the FastAPI backend on port 8003, then run `cd web && npm run dev`.
The Vite proxy forwards `/admin/api`, `/v1`, and `/healthz` to `http://localhost:8003`.
```

- [ ] **Step 2: Replace template `web/README.md`**

Replace the Vite template text with project-specific notes:

```markdown
# Kimi2API Dashboard Web

React/Vite frontend for the `/admin` dashboard.

## Commands

```bash
npm ci
npm run dev
npm run build
npm run lint
```

`npm run build` writes production assets to `../app/static/dist`.
The backend serves those assets from `/admin` and `/assets`.

For local Vite development, start the backend on port `8003`; `vite.config.ts`
proxies `/admin/api`, `/v1`, and `/healthz` to it.
```

- [ ] **Step 3: Verify docs commands**

Run:

```bash
npm run build
npm run lint
uv run ruff check .
uv run pytest -q
```

Expected: every documented check exits 0.

---

### Task 7: Final Verification Gate

**Files:**
- No code changes unless prior tasks expose a failure.

- [ ] **Step 1: Run full backend checks**

Run:

```bash
uv run ruff check .
uv run python -m compileall app tests run.py
uv run pytest -q
```

Expected:

```text
ruff: no findings
compileall: exit 0
pytest: 61+ passed, 0 failed
```

- [ ] **Step 2: Run full frontend checks**

Run:

```bash
cd web
npm run lint
npm run build
```

Expected: lint exits 0 and Vite build exits 0.

- [ ] **Step 3: Re-run the original path traversal proof**

Run:

```bash
uv run python - <<'PY'
from fastapi.testclient import TestClient
from app.main import create_app
client = TestClient(create_app(initialize=False))
for path in ["/admin/%2e%2e/%2e%2e/main.py", "/admin/%2e%2e/%2e%2e/config.py"]:
    r = client.get(path)
    assert "import os" not in r.text
    assert "class Config" not in r.text
    print(path, r.status_code, r.headers.get("content-type"))
PY
```

Expected: command exits 0 and prints non-source responses.

- [ ] **Step 4: Inspect git diff**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; status shows only intended files.

---

## Execution Order

1. Task 1 first: closes the source disclosure vulnerability.
2. Task 2 next: fixes local/fresh-clone dashboard entry behavior while already in `app/main.py`.
3. Task 3 next: fixes user-visible token operation correctness.
4. Task 4 next: restores quality gates.
5. Task 5 and Task 6: small polish/docs fixes.
6. Task 7: required final verification before claiming completion.

