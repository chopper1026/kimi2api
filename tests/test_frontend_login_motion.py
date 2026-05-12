from pathlib import Path


def test_login_page_has_submit_success_transition_before_navigation():
    source = Path("web/src/pages/LoginPage.tsx").read_text()

    assert "LOGIN_BRIDGE_DURATION_MS" in source
    assert 'useState<"idle" | "submitting" | "bridge">' in source
    assert "data-login-state={loginState}" in source
    assert 'loginState === "bridge"' in source
    assert "login-panel-layer" in source
    assert "login-bridge-page" in source
    assert "login-bridge-progress" in source
    assert "login-card" in source
    assert "login-brand" in source
    assert "正在进入控制台" in source
    assert "正在建立安全会话" in source
    assert "setTimeout" in source
    assert 'navigate("/admin/dashboard", { replace: true })' in source


def test_admin_shell_animates_after_login_mount():
    source = Path("web/src/components/layout/AppLayout.tsx").read_text()

    assert "data-admin-shell" in source
    assert "admin-shell-enter" in source


def test_login_and_shell_motion_css_respects_reduced_motion():
    source = Path("web/src/index.css").read_text()

    for name in (
        "@keyframes login-page-enter",
        "@keyframes login-brand-enter",
        "@keyframes login-card-enter",
        "@keyframes login-panel-exit",
        "@keyframes login-bridge-enter",
        "@keyframes login-bridge-progress",
        "@keyframes admin-shell-enter",
    ):
        assert name in source

    assert ".login-page-shell" in source
    assert ".login-panel-layer" in source
    assert ".login-panel-exit" in source
    assert ".login-bridge-page" in source
    assert ".login-card" in source
    assert ".admin-shell-enter" in source
    assert "prefers-reduced-motion: reduce" in source
    assert ".login-page-shell," in source
    assert ".admin-shell-enter" in source.rsplit(
        "prefers-reduced-motion: reduce", 1
    )[-1]


def test_login_page_entry_motion_does_not_create_transient_scrollbar():
    login_source = Path("web/src/pages/LoginPage.tsx").read_text()
    css_source = Path("web/src/index.css").read_text()
    page_enter_block = css_source.split("@keyframes login-page-enter", 1)[
        1
    ].split("@keyframes", 1)[0]

    assert "login-page-shell" in login_source
    assert "overflow-hidden" in login_source
    assert "transform:" not in page_enter_block


def test_login_bridge_motion_is_internal_and_non_scroll_creating():
    css_source = Path("web/src/index.css").read_text()
    bridge_enter_block = css_source.split("@keyframes login-bridge-enter", 1)[
        1
    ].split("@keyframes", 1)[0]
    panel_exit_block = css_source.split("@keyframes login-panel-exit", 1)[
        1
    ].split("@keyframes", 1)[0]

    assert "position: absolute" in css_source.split(".login-bridge-page", 1)[1]
    assert "inset: 0" in css_source.split(".login-bridge-page", 1)[1]
    assert "translateY(-" in panel_exit_block
    assert "transform:" in bridge_enter_block


def test_admin_shell_entry_motion_does_not_create_transient_scrollbar():
    css_source = Path("web/src/index.css").read_text()
    shell_enter_block = css_source.split("@keyframes admin-shell-enter", 1)[
        1
    ].split(".login-page-shell", 1)[0]

    assert "transform:" not in shell_enter_block
