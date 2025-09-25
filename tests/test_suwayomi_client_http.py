from __future__ import annotations

import responses

from import_mangadex_bookmarks_to_suwayomi_refactored import SuwayomiClient


def test_remove_from_library_fallback_uses_get(responses_mock: responses.RequestsMock):
    client = SuwayomiClient(base_url="http://example.com")
    responses_mock.add(
        responses.DELETE,
        "http://example.com/api/v1/manga/5/library",
        status=404,
    )
    responses_mock.add(
        responses.GET,
        "http://example.com/api/v1/manga/5/library/remove",
        status=200,
    )
    assert client.remove_from_library(5) is True


def test_remove_from_library_returns_false_when_all_paths_fail(responses_mock: responses.RequestsMock):
    client = SuwayomiClient(base_url="http://example.com")
    responses_mock.add(
        responses.DELETE,
        "http://example.com/api/v1/manga/5/library",
        status=404,
    )
    responses_mock.add(
        responses.GET,
        "http://example.com/api/v1/manga/5/library/remove",
        status=500,
    )
    assert client.remove_from_library(5) is False


def test_graphql_fallbacks_to_secondary_endpoint(responses_mock: responses.RequestsMock):
    client = SuwayomiClient(base_url="http://example.com")
    responses_mock.add(
        responses.POST,
        "http://example.com/api/graphql",
        status=500,
    )
    responses_mock.add(
        responses.POST,
        "http://example.com/graphql",
        json={"data": {"ok": True}},
        status=200,
    )
    payload = client.graphql("query { ok }")
    assert payload == {"data": {"ok": True}}
