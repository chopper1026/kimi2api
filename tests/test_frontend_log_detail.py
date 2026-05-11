from pathlib import Path


def test_log_detail_keeps_parsed_response_and_reasoning_sections():
    source = Path("web/src/pages/LogDetailPage.tsx").read_text()

    assert "解析正文" in source
    assert "思维链" in source
    assert "shouldShowParsedResponse" in source
