from pathlib import Path


def test_admin_primary_pages_center_content_region():
    expected_classes = {
        "web/src/pages/DashboardPage.tsx": 'className="mx-auto w-full max-w-[1320px] space-y-5"',
        "web/src/pages/KeysPage.tsx": 'className="mx-auto w-full max-w-[1320px] space-y-5"',
        "web/src/pages/LogsPage.tsx": 'className="mx-auto w-full max-w-[1320px] space-y-4"',
    }

    for path, class_name in expected_classes.items():
        assert class_name in Path(path).read_text()
