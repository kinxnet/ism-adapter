"""THAAD가 배치 중 일부만 실패해도 HTTP 400을 내리는 경우를 고정하는 테스트.

2026-10-02 dev 실측: Contract 미등록 project가 섞인 배치를 push했더니
THAAD가 성공/실패가 섞인 리스트를 본문에 담으면서도 HTTP 상태를 400으로
내렸다. 이전 가정("개별 에러는 HTTP 상태코드에 안 섞인다")이 이 경우엔
틀렸다는 걸 재현한다.
"""

import httpx
import pytest
import respx

from ism_adapter.clients.ism_client import ISMClient

_BASE_URL = "https://ism.example.test/v1"


@pytest.fixture
def client():
    return ISMClient(base_url=_BASE_URL)


@respx.mock
def test_put_resources_recovers_mixed_success_error_batch_on_http_400(client):
    mixed_body = [
        {"nResourceSeq": 1, "mID": "ok-1"},
        {
            "error": {
                "classname": "Illuminate\\Database\\Eloquent\\ModelNotFoundException",
                "message": "No query results for model [ServiceMap].",
                "status_code": 400,
            },
            "payload": {"resource": {"mID": "no-contract-1"}},
        },
    ]
    respx.post(f"{_BASE_URL}/resources").mock(
        return_value=httpx.Response(400, json=mixed_body)
    )

    result = client.put_resources(
        [{"resource": {"mID": "ok-1"}}, {"resource": {"mID": "no-contract-1"}}]
    )

    assert result == mixed_body


@respx.mock
def test_put_resources_still_raises_on_non_400_error(client):
    respx.post(f"{_BASE_URL}/resources").mock(
        return_value=httpx.Response(500, text="boom")
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.put_resources([{"resource": {"mID": "x"}}])


@respx.mock
def test_put_resources_raises_on_400_with_non_list_body(client):
    respx.post(f"{_BASE_URL}/resources").mock(
        return_value=httpx.Response(400, json={"error": "not a list"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.put_resources([{"resource": {"mID": "x"}}])


@respx.mock
def test_put_resources_all_success_still_works(client):
    respx.post(f"{_BASE_URL}/resources").mock(
        return_value=httpx.Response(200, json=[{"nResourceSeq": 1, "mID": "ok-1"}])
    )

    result = client.put_resources([{"resource": {"mID": "ok-1"}}])

    assert result == [{"nResourceSeq": 1, "mID": "ok-1"}]


@respx.mock
def test_put_account_handles_single_item_mixed_400(client):
    respx.post(f"{_BASE_URL}/accounts").mock(
        return_value=httpx.Response(
            400,
            json=[{"error": {"message": "No query results for model [ServiceMap]."}}],
        )
    )

    result = client.put_account({"account": "data"})

    assert result == {"error": {"message": "No query results for model [ServiceMap]."}}


@respx.mock
def test_put_resources_no_items_skips_request(client):
    result = client.put_resources([])
    assert result == []
