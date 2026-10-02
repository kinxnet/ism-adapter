"""Compute 대분류 (instance, os_image 등).

마일스톤 문서(2026H2-ism-migration-milestone.md §1) 기준 분류. os_image는
별도 티켓에서 진행 중이라 이 서브패키지에 아직 없을 수 있다.
"""

from ism_adapter.transformers.compute.instance import InstanceTransformer

TRANSFORMERS = {
    "instance": InstanceTransformer(),
}

__all__ = ["InstanceTransformer", "TRANSFORMERS"]
