"""metering-api GET /metering 호출 클라이언트.

인증 헤더는 metering-worker의 MeteringAPIClient와 동일한 방식
(IXcloud-Apikey + Authorization-Type: server)을 사용한다.
"""

from loguru import logger

from ism_adapter.core.rest_client import RestClient


class MeteringAPIClient(RestClient):
    def __init__(self, base_url: str, master_apikey: str):
        super().__init__(base_url=base_url)
        self._master_apikey = master_apikey

    def _default_headers(self) -> dict:
        headers = super()._default_headers()
        headers.update(
            {
                "Authorization-Type": "server",
                "IXcloud-Apikey": self._master_apikey,
            }
        )
        return headers

    def list_metering(
        self,
        resource_type: str,
        period_start: str,
        period_end: str,
        tzname: str = "UTC",
    ) -> list[dict]:
        """지정 기간의 전체 사용량(usage)을 조회한다.

        `is_all=true`로 페이지네이션 없이 전량 조회한다 — 어댑터는 상태를
        갖지 않고 매 실행마다 기간 전체를 다시 push하므로, 페이지 경계에서
        일부 자원이 누락되는 사고를 피하기 위함이다.
        """
        params = {
            "resource_type": resource_type,
            "period_start": period_start,
            "period_end": period_end,
            "tzname": tzname,
            "is_all": "true",
        }
        res = self.send_request("GET", "/metering", params=params)
        data = res.json()
        usages = data.get("usages") or []
        logger.info(
            "Fetched {} usage row(s) for resource_type={} period=[{}, {})",
            len(usages),
            resource_type,
            period_start,
            period_end,
        )
        return usages
