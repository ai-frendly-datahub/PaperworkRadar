from __future__ import annotations

from typing import Any
from unittest.mock import patch

from paperworkradar.collector import collect_sources
from paperworkradar.models import Source


class _FakeApiResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.content = b""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._payload


def test_collect_sources_supports_gov24_api_source_pagination(monkeypatch: Any) -> None:
    monkeypatch.setenv("GOV24_API_KEY", "test-key")
    source = Source(
        name="Gov24 Open API",
        type="api_source",
        url="https://api.odcloud.kr/api/gov24/v3/serviceList?perPage=2&page=1",
    )

    page1 = {
        "data": [
            {
                "serviceName": "전입신고",
                "serviceSummary": "전입 관련 민원 신청",
                "serviceId": "GOV24-1",
            },
            {
                "serviceName": "주민등록등본 발급",
                "serviceSummary": "주민등록 서류 발급 절차",
                "serviceId": "GOV24-2",
            },
        ]
    }
    page2 = {
        "data": [
            {
                "serviceName": "사업자 등록 신청",
                "serviceSummary": "사업자 등록 민원",
                "serviceId": "GOV24-3",
            }
        ]
    }

    calls: list[dict[str, Any]] = []

    def _fake_get(url: str, *, params: dict[str, Any], timeout: int) -> _FakeApiResponse:
        calls.append({"url": url, "params": params, "timeout": timeout})
        if params.get("page") == 1:
            return _FakeApiResponse(page1)
        return _FakeApiResponse(page2)

    with patch("paperworkradar.collector.requests.get", side_effect=_fake_get), patch(
        "paperworkradar.collector.time.sleep", return_value=None
    ):
        articles, errors = collect_sources([source], category="paperwork", limit_per_source=10, timeout=5)

    assert errors == []
    assert len(articles) == 3
    assert articles[0].source == "Gov24 Open API"
    assert articles[0].category == "paperwork"
    assert calls[0]["params"]["serviceKey"] == "test-key"
    assert calls[0]["params"]["returnType"] == "JSON"
    assert calls[0]["params"]["page"] == 1
    assert calls[1]["params"]["page"] == 2
