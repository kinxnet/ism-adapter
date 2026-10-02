"""ISM(THAAD) push 클라이언트.

2026-09-15 THAAD(ism-master) 실측 확인: `/v1/resources`, `/v1/meterings`는
요청 body가 dict(단건)인지 list(JSON 배열)인지를 `is_assoc()`으로 자동
구분한다 — list면 서버가 foreach로 각 항목을 개별 try/catch로 처리하고,
같은 순서의 결과 배열(성공/에러 섞임)을 반환한다. legacy(ism/resource.py,
ism/metering.py)가 20건씩 나눠 보내는 것은 "한 POST 요청 body에 최대 20개
짜리 JSON 배열을 담아 보낸다"는 뜻이며, 20번 개별 POST가 아니다.

**2026-10-02 실측 정정 — 배치 안에 에러가 섞이면 HTTP 상태코드도 그
에러 성격을 따라간다.** 이전 가정("개별 에러는 HTTP 상태코드에 안
섞인다")은 dev 환경 실제 push로 재확인한 결과 틀렸다 — THAAD는 배치 중
하나라도 실패하면 전체 응답 상태를 그 실패의 severity로 내리면서도(실측
확인: Contract 미등록 "ServiceMap not found"는 400, 등록 안 된
volume_type/product를 가리키는 "Product not found"는 500), 본문에는
성공/실패가 섞인 리스트를 그대로 담아 돌려준다. `send_request()`가
`raise_for_status()`를 먼저 호출해버리면 이 본문(성공 건 포함)이 전부
유실되고 예외로 크래시한다 — `_send_list_request()`가 400/500 + 리스트
조합만 예외로 취급하지 않고 결과로 복원한다(그 외 상태코드/파싱 불가
본문은 그대로 올림, 진짜 장애와 구분하기 위함).

ISM API는 인증 헤더가 없다(2026-09-15 조사 확인 — TLS 검증도 꺼져 있고
사내망 위치가 유일한 접근 통제로 보임). 이 무인증 방식을 그대로 이어받을지는
별도로 인프라/보안팀과 상의가 필요하다(ism-adapter-project-decisions 메모리
참고) — 이 클라이언트는 일단 legacy와 동일하게 인증 없이 호출한다.
"""

import httpx
from loguru import logger

from ism_adapter.core.rest_client import RestClient

_BATCH_SIZE = 20


class ISMClient(RestClient):
    def put_account(self, item: dict) -> dict:
        """계정 1건 등록/갱신.

        2026-09-16 실측(legacy `ism/account.py::register_accounts`) 확인:
        account push는 resource/metering과 달리 **계정 1건당 1회 개별 POST**다
        (`requests.post(url, json=[account_data])` — 배열로 감싸긴 하지만
        원소가 항상 1개, 20건 배치가 아님). 반복/실패 시 중단 여부는 호출부
        (account_service.py, 2026-09-17부터 첫 실패 시 즉시 중단)가 담당한다.
        """
        result = self._send_list_request("/accounts", [item])
        return result[0] if result else {}

    def put_contract(self, item: dict) -> dict:
        """계약 1건 등록/갱신.

        2026-09-17 실측(legacy `ism/contract.py::ContractClass.main()`) 확인:
        put_account와 동일하게 **project 1건당 1회 개별 POST**다
        (`requests.post(url, json=[project_data])`). legacy는 한 project
        실패 시 즉시 raise해서 나머지 반복을 중단시켰다 — 호출부
        (contract_service.py)도 이 방식(첫 실패 시 즉시 중단)을 그대로
        재현한다(account push와도 통일됨).
        """
        result = self._send_list_request("/contracts", [item])
        return result[0] if result else {}

    def put_resources(self, items: list[dict]) -> list[dict]:
        """자원 등록/속성 갱신. 각 item은 transformer가 만든
        `{"service_type": "cloud", "contract_service_map": ..., "resource": ...}`
        형태여야 한다."""
        return self._put_in_batches("/resources", items)

    def put_meterings(self, items: list[dict]) -> list[dict]:
        """일별 사용량 push. 각 item은
        `{"service_type": "cloud", "metering": ...}` 형태여야 한다."""
        return self._put_in_batches("/meterings", items)

    def _put_in_batches(self, path: str, items: list[dict]) -> list[dict]:
        if not items:
            logger.info("No items to push to ISM {}, skipping", path)
            return []

        results: list[dict] = []
        for i in range(0, len(items), _BATCH_SIZE):
            batch = items[i : i + _BATCH_SIZE]
            results.extend(self._send_list_request(path, batch))
            logger.info(
                "Pushed batch {}-{} of {} to ISM {}",
                i,
                i + len(batch),
                len(items),
                path,
            )

        return results

    # THAAD가 배치 중 일부 항목 실패 시 본문에 실어 보내는 전체 HTTP 상태
    # 코드들 — 2026-10-02 dev 실측으로 둘 다 확인됨("ServiceMap" 미존재는
    # 400, "Product" 미존재는 500으로 나왔다). 그 외 상태코드는 이 배치별
    # 개별 에러 패턴과 무관한 진짜 장애로 간주해 그대로 예외를 올린다.
    _MIXED_BATCH_STATUS_CODES = frozenset({400, 500})

    def _send_list_request(self, path: str, items: list[dict]) -> list[dict]:
        """`items`를 JSON 배열로 POST하고, 결과를 항상 리스트로 반환한다.

        THAAD가 배치 중 일부만 실패해도 HTTP 상태 자체를 400 또는 500으로
        내리는 경우(모듈 docstring 참고)를 예외로 취급하지 않고, 본문의
        리스트를 그대로 결과로 쓴다 — 그래야 같은 배치 안의 성공 건이
        유실되지 않는다. 위 두 상태코드가 아니거나 본문이 리스트가
        아니면(진짜 장애) 그대로 예외를 올린다.
        """
        try:
            res = self.send_request("POST", path, json=items)
            body = res.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in self._MIXED_BATCH_STATUS_CODES:
                raise
            try:
                body = e.response.json()
            except ValueError:
                raise e from None
            if not isinstance(body, list):
                raise e from None
            logger.warning(
                "ISM {} 배치에 실패 항목이 섞여 HTTP {}가 반환됨 — "
                "본문의 {}건 결과(성공 포함)는 그대로 사용합니다",
                path,
                e.response.status_code,
                len(body),
            )
        return body if isinstance(body, list) else [body]
