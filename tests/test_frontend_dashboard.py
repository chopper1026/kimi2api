from pathlib import Path


def test_dashboard_page_contains_operations_workbench_sections():
    source = Path("web/src/pages/DashboardPage.tsx").read_text()

    assert "最近 24 小时" in source
    assert "最近异常请求" in source
    assert "日志策略" in source
    assert "快捷操作" in source
