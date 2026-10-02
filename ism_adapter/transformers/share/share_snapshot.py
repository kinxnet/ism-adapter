"""share_snapshot usage -> THAAD push payload 변환.

**resource_type 이중 표기** — `share.py`(NAS 본체)와 동일한 이유로
`SimpleResourceTransformer`를 상속하지 않는다. 이 클래스의 `resource_type`
속성(`"share_snapshot"`)은 metering-api 쪽 자원 키 이름이고, THAAD
`arDetailInfo.detail.resource_type`은 legacy `run_share_snapshot`이 실제로
보내던 값이자 THAAD에 등록된 상품(nProductSeq=352, "NAS 스냅샷")의
`attribute.resource_type`과 일치해야 하는 `"nas_snapshot"`이다 — 2026-10-02
dev 실전 검증에서 `self.resource_type`을 그대로 썼다가 "Product not found"로
전건 실패한 뒤 발견해 수정함(`share.py`가 처음부터 이렇게 되어있던 것과
동일한 이유).

mID는 legacy와 동일하게 resource_id 그대로(스펙 인코딩 없음).
"""

from ism_adapter.repositories import ProjectInfo
from ism_adapter.transformers.base import ResourcePayload, _to_kst

_THAAD_RESOURCE_TYPE = "nas_snapshot"


class ShareSnapshotTransformer:
    resource_type = "share_snapshot"

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
                        "resource_type": _THAAD_RESOURCE_TYPE,
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
                        "resource_type": _THAAD_RESOURCE_TYPE,
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
