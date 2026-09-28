"""REST 클라이언트 공통 요청 처리.

metering-worker의 MeteringAPIClient 패턴(httpx.Client + send_request)을 그대로
따른다 — 예외 발생 시 원인(DNS/connection refused/timeout 등)까지 로깅해
운영 중 장애 원인 파악을 돕는다.
"""

import httpx
from loguru import logger


class RestClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        if not base_url:
            raise ValueError("base_url is required")
        self.client = httpx.Client(base_url=base_url, timeout=timeout)

    def _default_headers(self) -> dict:
        return {"Content-Type": "application/json"}

    def send_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        headers = self._default_headers()
        headers.update(kwargs.pop("headers", None) or {})
        kwargs["headers"] = headers

        logger.debug("Sending {} request to {}{}", method, self.client.base_url, url)

        try:
            res = self.client.request(method, url, **kwargs)
            res.raise_for_status()
        except httpx.TimeoutException as e:
            logger.error("Request timeout while requesting {} {}: {}", method, url, e)
            raise
        except httpx.ConnectError as e:
            logger.error("Connection error while requesting {} {}: {}", method, url, e)
            raise
        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP {} error while requesting {} {}: {}",
                e.response.status_code,
                method,
                url,
                e,
            )
            logger.error("Response text: {}", e.response.text)
            raise
        except httpx.RequestError as e:
            logger.error("Request error while requesting {} {}: {}", method, url, e)
            raise

        return res

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "RestClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
