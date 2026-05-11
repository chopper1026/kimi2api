def test_logout_with_csrf_clears_session(authenticated_admin_client):
    session = authenticated_admin_client.get("/admin/api/session")

    assert session.status_code == 200
    csrf_token = session.json()["csrf_token"]
    assert csrf_token

    response = authenticated_admin_client.post(
        "/admin/api/logout",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert authenticated_admin_client.get("/admin/api/session").status_code == 401
