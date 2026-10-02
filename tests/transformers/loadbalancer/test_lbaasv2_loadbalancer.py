"""lbaasv2_loadbalancer mID 조립 규칙과 KLB 필터 기본 동작 고정.

mID는 legacy `ism/resource.py::run_lbaas` rocky 분기
(`"{resource_id}-lbaas-provider::standard"`, 접미사는 usage 데이터가 아니라
항상 고정값)와 정확히 일치해야 한다(issue #11 acceptance criteria).

KLB 필터는 이번 티켓 스코프상 실제 API를 호출하지 않는 스텁이므로, 기본
구현(`_NoOpKlbLinkChecker`)이 "아무도 KLB 연동으로 판정하지 않는다"(=
전건 push, 필터링 없음)를 보장하는지를 고정한다 — 인증 방식·동기화 주기가
확정되어 실제 구현으로 교체될 때까지 이 동작이 기본값이어야 한다.
"""

from ism_adapter.repositories import ProjectInfo
from ism_adapter.transformers.loadbalancer.lbaasv2_loadbalancer import (
    KlbLinkChecker,
    LbaasV2LoadbalancerTransformer,
    _NoOpKlbLinkChecker,
)

_RESOURCE_ID = "a1a1a1a1-2222-3333-4444-555555555555"

_PROJECT = ProjectInfo(
    project_id="project-uuid-1",
    tenant_id="tenant-1",
    provider_id="provider-1",
)

_USAGE = {
    "resource_id": _RESOURCE_ID,
    "tenant_id": "tenant-1",
    "display_name": "lb-01",
    "created_at": "2026-08-01T00:00:00+00:00",
    "deleted_at": None,
    "min_started_at": "2026-08-01T00:00:00+00:00",
    "max_ended_at": "2026-08-31T00:00:00+00:00",
    "durations": {"total": {"seconds": 2592000}},
    # legacy에서는 kilo 분기만 실제 lb_provider 값을 썼고 rocky 분기는
    # "standard"를 하드코딩했다 — usage에 다른 값이 와도 무시되어야 한다.
    "lb_provider": "haproxy",
}


def test_mid_matches_legacy_fixed_suffix_format():
    payload = LbaasV2LoadbalancerTransformer().to_resource_payload(_USAGE, _PROJECT)

    assert payload.mid == f"{_RESOURCE_ID}-lbaas-provider::standard"


def test_mid_suffix_is_fixed_not_from_usage_data():
    """usage에 다른 lb_provider 값이 있어도 접미사는 항상 "standard" —
    legacy rocky 분기가 하드코딩한 값이지 usage 데이터가 아니다."""
    payload = LbaasV2LoadbalancerTransformer().to_resource_payload(_USAGE, _PROJECT)

    assert "haproxy" not in payload.mid
    assert payload.mid.endswith("::standard")


def test_resource_item_uses_composed_mid():
    payload = LbaasV2LoadbalancerTransformer().to_resource_payload(_USAGE, _PROJECT)

    assert payload.resource_item["resource"]["mID"] == payload.mid
    assert (
        payload.resource_item["resource"]["arDetailInfo"]["detail"]["resource_type"]
        == "loadbalancer"
    )
    assert (
        payload.resource_item["resource"]["arDetailInfo"]["detail"]["resource_id"]
        == _RESOURCE_ID
    )


def test_metering_item_sresourceid_matches_mid():
    payload = LbaasV2LoadbalancerTransformer().to_resource_payload(_USAGE, _PROJECT)

    assert payload.metering_item["metering"]["sResourceId"] == payload.mid
    assert payload.metering_item["metering"]["nActiveSec"] == 2592000
    assert payload.metering_item["metering"]["nSuspendSec"] == 0


def test_default_klb_checker_never_links_anything():
    """캐시/동기화 메커니즘이 아직 없으므로 기본 구현은 전부 False(=
    KLB 미연동)를 반환해야 한다 — 즉 기본값은 "전건 push, 필터링 없음"."""
    checker = _NoOpKlbLinkChecker()

    assert checker.is_klb_linked(_RESOURCE_ID) is False
    assert checker.is_klb_linked("any-other-resource-id") is False


def test_transformer_is_excluded_defaults_to_not_filtering():
    transformer = LbaasV2LoadbalancerTransformer()

    assert transformer.is_excluded(_USAGE) is False


def test_transformer_delegates_exclusion_to_injected_checker():
    """실제 KLB API 연동 구현이 준비되면 이 생성자 인자만 교체하면 되도록,
    transformer는 판별 로직을 직접 갖지 않고 주입받은 checker에 위임한다."""

    class _AlwaysLinkedChecker:
        def is_klb_linked(self, resource_id: str) -> bool:
            return True

    transformer = LbaasV2LoadbalancerTransformer(klb_checker=_AlwaysLinkedChecker())

    assert transformer.is_excluded(_USAGE) is True


def test_klb_link_checker_protocol_is_satisfied_by_default_impl():
    checker: KlbLinkChecker = _NoOpKlbLinkChecker()

    assert checker.is_klb_linked(_RESOURCE_ID) is False
