"""Loadbalancer 대분류 (lbaasv2_loadbalancer 등. listener/pool/member/healthmonitor는
과금 대상이 아니라 history만 수집 — ISM push 대상 아님).

마일스톤 문서(2026H2-ism-migration-milestone.md §1) 기준 분류. 이번 자원이
첫 이관 대상(lbaasv2_loadbalancer.py) — mID는 legacy rocky 분기를 그대로
재현한 고정 접미사 포맷(`{resource_id}-lbaas-provider::standard`)이고,
KLB 연동 필터는 인증 방식·동기화 주기 미확정(이슈 #9)으로 아직 스텁(전건
통과) 상태다. 상세는 lbaasv2_loadbalancer.py 모듈 docstring 참고.
"""

from ism_adapter.transformers.loadbalancer.lbaasv2_loadbalancer import (
    LbaasV2LoadbalancerTransformer,
)

TRANSFORMERS = {
    "loadbalancer": LbaasV2LoadbalancerTransformer(),
}

__all__ = ["LbaasV2LoadbalancerTransformer", "TRANSFORMERS"]
