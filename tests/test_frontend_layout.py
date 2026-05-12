from pathlib import Path


def test_admin_primary_pages_center_content_region():
    expected_classes = {
        "web/src/pages/DashboardPage.tsx": 'className="mx-auto w-full max-w-[1320px] space-y-5"',
        "web/src/pages/KeysPage.tsx": 'className="mx-auto w-full max-w-[1320px] space-y-5"',
        "web/src/pages/LogsPage.tsx": 'className="mx-auto w-full max-w-[1320px] space-y-4"',
        "web/src/pages/TokenPage.tsx": 'className="mx-auto w-full max-w-[1320px] space-y-5"',
    }

    for path, class_name in expected_classes.items():
        assert class_name in Path(path).read_text()


def test_admin_layout_adds_mobile_navigation_without_removing_desktop_sidebar():
    source = Path("web/src/components/layout/AppLayout.tsx").read_text()

    assert 'aria-label="移动端导航"' in source
    assert "md:hidden" in source
    assert "hidden w-60" in source
    assert "md:flex" in source


def test_admin_content_uses_route_transition_animation():
    layout_source = Path("web/src/components/layout/AppLayout.tsx").read_text()
    css_source = Path("web/src/index.css").read_text()

    assert 'key={location.pathname}' in layout_source
    assert 'data-route-content' in layout_source
    assert 'className="admin-route-content min-h-full"' in layout_source
    assert "@keyframes admin-route-enter" in css_source
    assert ".admin-route-content" in css_source
    assert "prefers-reduced-motion: reduce" in css_source


def test_data_pages_keep_desktop_tables_and_add_mobile_cards():
    keys_source = Path("web/src/pages/KeysPage.tsx").read_text()
    logs_source = Path("web/src/pages/LogsPage.tsx").read_text()

    assert "KeyMobileCard" in keys_source
    assert "md:hidden" in keys_source
    assert "hidden md:block" in keys_source
    assert "LogMobileCard" in logs_source
    assert "md:hidden" in logs_source
    assert "hidden md:block" in logs_source


def test_logs_desktop_key_columns_are_width_constrained_and_truncated():
    source = Path("web/src/pages/LogsPage.tsx").read_text()

    assert '<col className="w-[12%]" />' in source
    assert 'title={log.api_key_name || "-"}' in source
    assert 'title={log.kimi_account_name || "-"}' in source
    assert "max-w-0 truncate text-xs text-muted-foreground" in source


def test_token_page_has_mobile_first_actions():
    source = Path("web/src/pages/TokenPage.tsx").read_text()

    assert "grid grid-cols-2 gap-2 border-t border-border/60 pt-3 sm:flex" in source
    assert "w-full whitespace-nowrap" in source
    assert "sm:w-auto" in source


def test_token_page_places_status_actions_at_card_bottom():
    source = Path("web/src/pages/TokenPage.tsx").read_text()

    assert '<CardHeader className="pb-3">' in source
    assert 'data-token-actions' in source
    assert "AccountDetail" in source
    assert "lg:grid-cols-5" in source
    assert "sm:justify-end" in source
    assert "md:flex-row md:items-start md:justify-between" not in source


def test_token_page_renders_account_pool_controls():
    source = Path("web/src/pages/TokenPage.tsx").read_text()

    assert "账号池" in source
    assert "accounts.map" in source
    assert "api.getTokens" in source
    assert "api.createTokenAccount" in source
    assert "api.updateTokenAccount" in source
    assert "api.deleteTokenAccount" in source
