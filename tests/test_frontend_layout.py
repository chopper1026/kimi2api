from pathlib import Path


def test_admin_primary_pages_center_content_region():
    expected_classes = {
        "web/src/pages/DashboardPage.tsx": 'className="mx-auto w-full max-w-[1320px] space-y-5"',
        "web/src/pages/KeysPage.tsx": 'className="mx-auto w-full max-w-[1320px] space-y-5"',
        "web/src/pages/LogsPage.tsx": 'className="mx-auto w-full max-w-[1320px] space-y-4"',
    }

    for path, class_name in expected_classes.items():
        assert class_name in Path(path).read_text()


def test_admin_layout_adds_mobile_navigation_without_removing_desktop_sidebar():
    source = Path("web/src/components/layout/AppLayout.tsx").read_text()

    assert 'aria-label="移动端导航"' in source
    assert "md:hidden" in source
    assert "hidden w-60" in source
    assert "md:flex" in source


def test_data_pages_keep_desktop_tables_and_add_mobile_cards():
    keys_source = Path("web/src/pages/KeysPage.tsx").read_text()
    logs_source = Path("web/src/pages/LogsPage.tsx").read_text()

    assert "KeyMobileCard" in keys_source
    assert "md:hidden" in keys_source
    assert "hidden md:block" in keys_source
    assert "LogMobileCard" in logs_source
    assert "md:hidden" in logs_source
    assert "hidden md:block" in logs_source


def test_token_page_has_mobile_first_actions():
    source = Path("web/src/pages/TokenPage.tsx").read_text()

    assert "grid grid-cols-1 gap-2 md:flex" in source
    assert "w-full md:w-auto" in source
