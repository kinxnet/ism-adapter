"""metering-api usage(dict) -> ISM(THAAD) push payload 변환.

2026-09-15 실측 확정 — legacy `ixcloud_service/common/ixcdaemon/ism/resource.py`
의 `run_network`/`run_router`, `ism/metering.py`의 `run_network`/`run_router`를
그대로 대조했다. THAAD(`ism-master`) `/v1/resources`, `/v1/meterings` 쪽 수신
스펙(별도 조사)과도 필드명이 일치함을 확인했다.

**요청 body는 항목의 리스트(JSON 배열)다** — THAAD는 dict(단건)와 list(여러
건)를 `is_assoc()`으로 자동 구분해 list면 foreach로 순회 처리한다. legacy가
20건씩 나눠 보내는 것은 "한 POST 요청 body에 최대 20개짜리 JSON 배열을 담아
보낸다"는 뜻이다(ism_client.py에서 처리).

**resource 항목** (`ism/resource.py::run_network`/`run_router`, 완전히 동일한
구조, `resource_type`/모델만 다름):
    {
      "service_type": "cloud",
      "contract_service_map": {
          "sService": "cloud", "sType": "Contract", "sServiceKey": <project.id>
      },
      "resource": {
          "mID": <resource_id>,
          "sServiceType": "I",
          "dtStart": <created_at, KST>,
          "dtEnd": <deleted_at, KST, nullable>,
          "arDetailInfo": {"detail": {
              "created_at": ..., "deleted_at": ..., "tenant_id": ...,
              "resource_id": ..., "display_name": ..., "resource_type": "network"|"router"
          }}
      }
    }

**metering 항목** (`ism/metering.py::run_network`/`run_router`):
    {
      "service_type": "cloud",
      "metering": {
          "sResourceId": <resource_id>,       # resource의 mID와 동일값
          "sProviderId": <project.provider_id>,
          "sTenantId": <tenant_id>,
          "dtPeriodStart": <period_start, KST>,
          "dtPeriodEnd": <period_end, KST>,
          "nActiveSec": <int(duration_sec)>,
          "nSuspendSec": 0,                    # network/router는 suspend 개념 없음, 항상 0
          "arDetailInfo": {"detail": {
              "id": ..., "inserted_at": ..., "period_start": ..., "period_end": ...,
              "created_at": ..., "tenant_id": ..., "resource_id": ..., "display_name": ...,
              "duration_sec": ..., "resource_type": "network"|"router", "charge_type": "Reserved"
          }}
      }
    }

`arDetailInfo.detail`은 legacy가 DB 컬럼을 그대로 실은 것이라 metering-api
usage 응답 전체가 아니라 이 필드들만 채운다 — 나머지 usage 필드를 그대로
욱여넣지 않는다(THAAD tProduct 속성 매칭에 불필요한 키가 섞이는 것을 피함).

no_pay/insider_use는 이 push 스펙에 없다(THAAD 실측 확인 — no_pay는 별도
`/v1/contracts` 계약 레벨 속성, insider_use는 THAAD에 없는 개념). project는
오직 `project.id`(contract_service_map.sServiceKey)와
`project.provider_id`(metering.sProviderId)만 쓰인다.

volume/instance/share처럼 mID에 여러 필드(size, IOPS, flavor 등)를 조합
인코딩해야 하는 자원은 `EncodedMidResourceTransformer`(아래)를 쓴다 — 서브
클래스가 `mid_fields`로 필드 조합 순서만 선언하면 legacy 포맷(예:
`{resource_id}-size::{size}-mIOPS::{max_iops}`)과 동일한 mID 문자열을
조립해준다. resource_item/metering_item 구성과 실제 자원(volume/instance/
share) 연결은 각 자원의 후속 티켓에서 진행한다.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import arrow

from ism_adapter.repositories import ProjectInfo

_KST = "Asia/Seoul"


def _to_kst(value: str | None) -> str | None:
    if value is None:
        return None
    return arrow.get(value).to(_KST).format("YYYY-MM-DD HH:mm:ss")


@dataclass(frozen=True)
class ResourcePayload:
    mid: str
    resource_item: dict
    metering_item: dict


class SimpleResourceTransformer:
    """mID = resource_id 그대로, resource/metering 둘 다 존재기간만 쓰는
    단순 자원(network, router)의 변환기."""

    resource_type: str

    def to_resource_payload(self, usage: dict, project: ProjectInfo) -> ResourcePayload:
        resource_id = usage["resource_id"]

        resource_item = {
            "service_type": "cloud",
            "contract_service_map": {
                "sService": "cloud",
                "sType": "Contract",
                "sServiceKey": project.project_id,
            },
            "resource": {
                "mID": resource_id,
                "sServiceType": "I",
                "dtStart": _to_kst(usage["created_at"]),
                "dtEnd": _to_kst(usage.get("deleted_at")),
                "arDetailInfo": {
                    "detail": {
                        "created_at": usage["created_at"],
                        "deleted_at": usage.get("deleted_at"),
                        "tenant_id": usage["tenant_id"],
                        "resource_id": resource_id,
                        "display_name": usage.get("display_name"),
                        "resource_type": self.resource_type,
                    }
                },
            },
        }

        metering_item = {
            "service_type": "cloud",
            "metering": {
                "sResourceId": resource_id,
                "sProviderId": project.provider_id,
                "sTenantId": usage["tenant_id"],
                "dtPeriodStart": _to_kst(usage["min_started_at"]),
                "dtPeriodEnd": _to_kst(usage["max_ended_at"]),
                "nActiveSec": int(usage["durations"]["total"]["seconds"]),
                "nSuspendSec": 0,
                "arDetailInfo": {
                    "detail": {
                        "period_start": usage["min_started_at"],
                        "period_end": usage["max_ended_at"],
                        "created_at": usage["created_at"],
                        "tenant_id": usage["tenant_id"],
                        "resource_id": resource_id,
                        "display_name": usage.get("display_name"),
                        "duration_sec": usage["durations"]["total"]["seconds"],
                        "resource_type": self.resource_type,
                        "charge_type": "Reserved",
                    }
                },
            },
        }

        return ResourcePayload(
            mid=resource_id,
            resource_item=resource_item,
            metering_item=metering_item,
        )


class EncodedMidResourceTransformer(ABC):
    """mID에 여러 필드를 `-key::value` 형식으로 조합 인코딩해야 하는 자원
    (volume, instance, share)을 위한 변환기 베이스.

    legacy mID 포맷은 `{resource_id}` 뒤에 고정된 (label, usage 필드) 쌍을
    선언 순서대로 `-label::value`로 이어붙인 구조다:
        - volume: `{resource_id}-size::{size}-mIOPS::{max_iops}-bIOPS::{burst_iops}`
        - instance: `{resource_id}-flavor::{flavor_id}-charge_type::{charge_type}`
        - share: `{resource_id}-size::{size}`

    서브클래스는 `mid_fields`에 `(label, usage_key)` 튜플을 순서대로 선언하면
    `build_mid()`가 이 문자열을 조립해준다. resource_item/metering_item을
    어떻게 구성할지는 자원마다 다를 수 있어(예: instance는 suspend 개념이
    있음) 이 베이스에서 강제하지 않는다 — 서브클래스가 `to_resource_payload`
    안에서 `build_mid()`를 호출해 mID를 채우고 나머지 payload를 구성한다.
    """

    resource_type: str
    mid_fields: tuple[tuple[str, str], ...]

    def build_mid(self, usage: dict) -> str:
        segments = [usage["resource_id"]]
        for label, usage_key in self.mid_fields:
            segments.append(f"{label}::{usage[usage_key]}")
        return "-".join(segments)

    @abstractmethod
    def to_resource_payload(self, usage: dict, project: ProjectInfo) -> ResourcePayload:
        """`SimpleResourceTransformer.to_resource_payload`와 동일한 시그니처.

        서브클래스가 `build_mid(usage)`로 mID를 조립하고 자원별
        resource_item/metering_item을 구성해 구현한다."""
