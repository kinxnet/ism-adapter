"""lbaasv2_loadbalancer usage(dict) -> ISM(THAAD) push payload 변환.

**mID 포맷** — legacy `ixcloud_service/common/ixcdaemon/ism/resource.py::run_lbaas`의
rocky 분기(`ResourceLbaas` 기준)를 그대로 재현한다:

    "{resource_id}-lbaas-provider::standard"

접미사는 usage 데이터의 `lb_provider` 값이 아니라 **항상 고정 문자열
`"standard"`**다 — legacy rocky 분기도 `lb_provider="standard"`를 하드코딩해
호출한다(kilo 분기만 실제 `lb_provider` 컬럼값을 썼다). mID에 variable
lb_provider를 인코딩하는 `EncodedMidResourceTransformer` 패턴(os_image 등)과
달리 이 자원은 고정 접미사라 그 베이스를 쓰지 않고, `base.py`의
`ResourcePayload`/`_to_kst` 헬퍼만 재사용해 여기서 직접 조합한다(PR #15
os_image.py와 동일한 결정).

resource/metering item 구조 자체(mID 조합 방식을 제외한 나머지 필드)는
`base.py::SimpleResourceTransformer`(network/router)와 동일하다 — metering-api
의 `LoadbalancerMeteringDTO`가 "존재 기간만 계산, 추가 필드 없음"이라고
명시하기 때문이다(listener/pool 등 종속 자원은 별도 과금 없음, loadbalancer
1개가 과금 단위).

**KLB 연동 필터 — 현재는 스텁, 실제 KLB API 호출 없음**:

legacy는 `ResourceLbaas.klb_id IS NULL` 조건으로 KLB(공유 로드밸런서)에
연동된 LB를 push 대상에서 제외했다(KLB 쪽에서 별도로 과금하므로 중복 과금
방지). metering-api의 `loadbalancer_history`는 Kafka 이벤트 payload 자체에
klb_id 정보가 없어 이 값을 전혀 모른다.

KLB 연동 여부를 판별하려면 외부 KLB API를 호출해야 하는데, 선행 조사
(이슈 #9)에서 다음 두 가지가 사람 확인 없이는 확정 불가능한 것으로
남았다:
    1. 서비스 계정으로 KLB API를 직접 호출할 수 있는 인증 방식인지
       (기존 클라이언트 `ixcloud_service/common_v2/portal_api/.../klb_api.py`는
       사람 세션 토큰 인증을 전제로 함)
    2. 캐시/동기화 주기 — legacy 자체가 레포 안에서 확인 가능한 고정
       주기를 쓴 게 아니라 외부 배치(추정)에 맡겼던 값이라 기준치가 없음

따라서 이번 구현은 실제로 KLB API를 호출하지 않는다. 대신 판별 지점을
`KlbLinkChecker` 프로토콜로 분리해, transformer가 구체적인 호출 방식에
의존하지 않도록 했다. 기본 구현(`_NoOpKlbLinkChecker`)은 캐시가 아직 없으므로
전부 False(= KLB 미연동)를 반환한다 — 즉 **현재는 전건을 필터링 없이
push한다. KLB에 실제로 연동된 LB가 있다면 legacy와 달리 중복 과금될 수
있다.** 인증 방식과 동기화 주기가 사람 확인으로 확정되면
`_NoOpKlbLinkChecker`를 실제 캐시 조회 구현으로 교체해야 한다.
"""

from typing import Protocol

from ism_adapter.repositories import ProjectInfo
from ism_adapter.transformers.base import ResourcePayload, _to_kst

_RESOURCE_TYPE = "loadbalancer"
_MID_SUFFIX = "-lbaas-provider::standard"


class KlbLinkChecker(Protocol):
    """KLB(공유 로드밸런서) 연동 여부 판별 인터페이스.

    `LbaasV2LoadbalancerTransformer`는 이 프로토콜에만 의존하고, 실제
    판별 방법(API 호출, 캐시 조회 등)은 알지 못한다 — 인증 방식·동기화
    주기가 확정되기 전까지 transformer 쪽 설계를 바꾸지 않고 구현만
    교체할 수 있게 하기 위함이다.
    """

    def is_klb_linked(self, resource_id: str) -> bool: ...


class _NoOpKlbLinkChecker:
    """KLB API 인증 방식·동기화 주기 확정 전까지는 임시로 전건
    push함(KLB 중복 과금 가능성 있음) — 인증 방식 확정되면 이 부분을
    실제 캐시 조회로 교체.

    모든 resource_id에 대해 항상 False(= KLB 미연동)를 반환한다. 이슈 #9의
    조사 결과, 캐시/동기화 배치를 먼저 두는 방식(옵션 3)이 권고되었으나
    서비스 계정 인증 가능 여부와 동기화 주기가 사람 확인 없이는 정해질 수
    없어, 이번 티켓에서는 그 캐시 자체를 구현하지 않는다.
    """

    def is_klb_linked(self, resource_id: str) -> bool:
        return False


class LbaasV2LoadbalancerTransformer:
    resource_type = _RESOURCE_TYPE

    def __init__(self, klb_checker: KlbLinkChecker | None = None):
        self._klb_checker = klb_checker or _NoOpKlbLinkChecker()

    def is_excluded(self, usage: dict) -> bool:
        """KLB에 연동된 LB면 True — 호출자는 이 경우 push 대상에서 빼야 한다."""
        return self._klb_checker.is_klb_linked(usage["resource_id"])

    def to_resource_payload(self, usage: dict, project: ProjectInfo) -> ResourcePayload:
        resource_id = usage["resource_id"]
        mid = f"{resource_id}{_MID_SUFFIX}"

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
                        "resource_id": resource_id,
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
                        "resource_id": resource_id,
                        "display_name": usage.get("display_name"),
                        "duration_sec": usage["durations"]["total"]["seconds"],
                        "resource_type": _RESOURCE_TYPE,
                        "charge_type": "Reserved",
                    }
                },
            },
        }

        return ResourcePayload(
            mid=mid,
            resource_item=resource_item,
            metering_item=metering_item,
        )
