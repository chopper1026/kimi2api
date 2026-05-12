from pathlib import Path


def test_shared_page_skeleton_components_are_available():
    source = Path("web/src/components/shared/PageSkeletons.tsx").read_text()

    for name in (
        "PageSkeleton",
        "CardSkeleton",
        "MetricGridSkeleton",
        "TableSkeleton",
        "MobileListSkeleton",
        "DetailSkeleton",
        "TokenStatusSkeleton",
    ):
        assert f"function {name}" in source
        assert name in source.rsplit("export {", 1)[-1]


def test_data_pages_use_shared_desktop_and_mobile_loading_skeletons():
    keys_source = Path("web/src/pages/KeysPage.tsx").read_text()
    logs_source = Path("web/src/pages/LogsPage.tsx").read_text()

    for source in (keys_source, logs_source):
        assert "@/components/shared/PageSkeletons" in source
        assert "TableSkeleton" in source
        assert "MobileListSkeleton" in source
        assert "hidden md:block" in source
        assert "md:hidden" in source


def test_token_and_log_detail_use_structured_skeletons():
    token_source = Path("web/src/pages/TokenPage.tsx").read_text()
    detail_source = Path("web/src/pages/LogDetailPage.tsx").read_text()

    assert "TokenStatusSkeleton" in token_source
    assert "<TokenStatusSkeleton />" in token_source
    assert "加载中..." not in token_source
    assert "DetailSkeleton" in detail_source
    assert 'from "@/components/ui/skeleton"' not in detail_source
