"""os_image usage(dict) -> ISM(THAAD) push payload 변환.

os_image는 instance_history를 (resource_id, base_image_ref) 기준으로 재집계한
인스턴스 파생 자원이라, metering-api usage에는 별도 image_id 필드가 없다 —
`usage["resource_id"]`가 곧 instance_id다(`OsImageMeteringDTO` 참고).

legacy `ixcloud_service/common/ixcdaemon/ism/resource.py::run_os_image`,
`ism/metering.py::run_os_image`가 실제로 쓰던 mID 포맷
(`"os_image-instance_id::{instance_id}"`, 이미지 참조는 인코딩하지 않음)을
그대로 재현한다. 리빌드 등으로 인스턴스의 이미지가 바뀌어도 동일 mID로
push되어 이전 기간을 덮어쓰는 것 역시 legacy와 동일한 동작이다(의도적
재현이지 버그가 아니다).

현재는 legacy와 동일하게 instance_id만 인코딩한다. THAAD는 mID를 opaque
문자열로 취급해 포맷 검증을 하지 않으므로, 추후 base_image_ref를 추가
인코딩해 이미지별 기간을 분리 보존하는 개선이 가능함(이번 스코프 아님).

resource/metering item 구조 자체는 `base.py::SimpleResourceTransformer`
(network/router)와 동일하다 — mID 조립 방식만 달라 새 베이스 클래스를 두지
않고 `ResourcePayload`/`_to_kst` 헬퍼만 재사용해 여기서 직접 조합한다.
"""

from ism_adapter.repositories import ProjectInfo
from ism_adapter.transformers.base import ResourcePayload, _to_kst

_RESOURCE_TYPE = "os_image"
_MID_PREFIX = "os_image-instance_id::"


class OsImageTransformer:
    resource_type = _RESOURCE_TYPE

    def to_resource_payload(self, usage: dict, project: ProjectInfo) -> ResourcePayload:
        instance_id = usage["resource_id"]
        mid = f"{_MID_PREFIX}{instance_id}"

        resource_item = {
            "service_type": "cloud",
            "contract_service_map": {
                "sService": "cloud",
                "sType": "Contract",
                "sServiceKey": project.project_id,
            },
            "resource": {
                "mID": mid,
                "sServiceType": "I",
                "dtStart": _to_kst(usage["created_at"]),
                "dtEnd": _to_kst(usage.get("deleted_at")),
                "arDetailInfo": {
                    "detail": {
                        "created_at": usage["created_at"],
                        "deleted_at": usage.get("deleted_at"),
                        "tenant_id": usage["tenant_id"],
                        "resource_id": instance_id,
                        "display_name": usage.get("display_name"),
                        "resource_type": _RESOURCE_TYPE,
                    }
                },
            },
        }

        metering_item = {
            "service_type": "cloud",
            "metering": {
                "sResourceId": mid,
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
                        "resource_id": instance_id,
                        "display_name": usage.get("display_name"),
                        "duration_sec": usage["durations"]["total"]["seconds"],
                        "resource_type": _RESOURCE_TYPE,
                        "charge_type": "Reserved",
                    }
                },
            },
        }

        return ResourcePayload(
            mid=mid, resource_item=resource_item, metering_item=metering_item
        )
