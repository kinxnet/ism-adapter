"""ISM(THAAD) push 클라이언트.

2026-09-15 THAAD(ism-master) 실측 확인: `/v1/resources`, `/v1/meterings`는
요청 body가 dict(단건)인지 list(JSON 배열)인지를 `is_assoc()`으로 자동
구분한다 — list면 서버가 foreach로 각 항목을 개별 try/catch로 처리하고,
같은 순서의 결과 배열(성공/에러 섞임)을 반환한다. legacy(ism/resource.py,
ism/metering.py)가 20건씩 나눠 보내는 것은 "한 POST 요청 body에 최대 20개
짜리 JSON 배열을 담아 보낸다"는 뜻이며, 20번 개별 POST가 아니다.

ISM API는 인증 헤더가 없다(2026-09-15 조사 확인 — TLS 검증도 꺼져 있고
사내망 위치가 유일한 접근 통제로 보임). 이 무인증 방식을 그대로 이어받을지는
별도로 인프라/보안팀과 상의가 필요하다(ism-adapter-project-decisions 메모리
참고) — 이 클라이언트는 일단 legacy와 동일하게 인증 없이 호출한다.
"""

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
        res = self.send_request("POST", "/accounts", json=[item])
        result = res.json()
        return result[0] if isinstance(result, list) else result

    def put_contract(self, item: dict) -> dict:
        """계약 1건 등록/갱신.

        2026-09-17 실측(legacy `ism/contract.py::ContractClass.main()`) 확인:
        put_account와 동일하게 **project 1건당 1회 개별 POST**다
        (`requests.post(url, json=[project_data])`). legacy는 한 project
        실패 시 즉시 raise해서 나머지 반복을 중단시켰다 — 호출부
        (contract_service.py)도 이 방식(첫 실패 시 즉시 중단)을 그대로
        재현한다(account push와도 통일됨).
        """
        res = self.send_request("POST", "/contracts", json=[item])
        result = res.json()
        return result[0] if isinstance(result, list) else result

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
            res = self.send_request("POST", path, json=batch)
            batch_result = res.json()
            results.extend(batch_result if isinstance(batch_result, list) else [batch_result])
            logger.info(
                "Pushed batch {}-{} of {} to ISM {}",
                i,
                i + len(batch),
                len(items),
                path,
            )

        return results
