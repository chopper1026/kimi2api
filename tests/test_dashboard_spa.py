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
    (dist / "index.html").write_text('<div id="root"></div>', encoding="utf-8")

    client = TestClient(create_app(initialize=False, static_dir=str(static_dir)))
    response = client.get("/admin/%2e%2e/%2e%2e/main.py")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "import os" not in response.text
    assert '<div id="root"></div>' in response.text


def test_admin_malformed_encoded_path_serves_index(tmp_path):
    static_dir = tmp_path / "static"
    dist = static_dir / "dist"
    dist.mkdir(parents=True)
    (static_dir / "favicon.svg").write_text("<svg />", encoding="utf-8")
    (dist / "index.html").write_text('<div id="root"></div>', encoding="utf-8")

    client = TestClient(
        create_app(initialize=False, static_dir=str(static_dir)),
        raise_server_exceptions=False,
    )
    response = client.get("/admin/%00")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Internal Server Error" not in response.text
    assert '<div id="root"></div>' in response.text


def test_admin_api_exact_path_returns_json_404_while_spa_routes_serve_index(tmp_path):
    static_dir = tmp_path / "static"
    dist = static_dir / "dist"
    dist.mkdir(parents=True)
    (static_dir / "favicon.svg").write_text("<svg />", encoding="utf-8")
    (dist / "index.html").write_text('<div id="root"></div>', encoding="utf-8")

    client = TestClient(create_app(initialize=False, static_dir=str(static_dir)))

    api_response = client.get("/admin/api")
    assert api_response.status_code == 404
    assert api_response.headers["content-type"].startswith("application/json")
    assert api_response.json() == {"error": "Not found"}

    spa_response = client.get("/admin/login")
    assert spa_response.status_code == 200
    assert spa_response.headers["content-type"].startswith("text/html")
    assert '<div id="root"></div>' in spa_response.text


def test_admin_returns_build_hint_when_dist_missing(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "favicon.svg").write_text("<svg />", encoding="utf-8")

    client = TestClient(create_app(initialize=False, static_dir=str(static_dir)))
    response = client.get("/admin")

    assert response.status_code == 503
    assert "Dashboard not built" in response.text
