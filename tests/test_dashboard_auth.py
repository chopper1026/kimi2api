import re


def test_logout_form_posts_csrf_and_clears_session(authenticated_admin_client):
    page = authenticated_admin_client.get("/admin/dashboard")

    assert page.status_code == 200
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert match is not None

    response = authenticated_admin_client.post(
        "/admin/logout",
        data={"csrf_token": match.group(1)},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/admin/login"
    assert authenticated_admin_client.get("/admin/dashboard", follow_redirects=False).status_code == 302
