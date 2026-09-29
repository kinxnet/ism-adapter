"""Compute 대분류 (instance, os_image 등).

마일스톤 문서(2026H2-ism-migration-milestone.md §1) 기준 분류. os_image는
mID에 고정 접두사(`os_image-instance_id::`)만 인코딩하면 legacy와 동일해
이관 완료(os_image.py). instance는 여전히 별도 mID 스펙 인코딩 설계가
필요해 착수 시점에 남겨둠(ism-adapter-project-decisions 메모리 참고).
"""

from ism_adapter.transformers.compute.instance import InstanceTransformer
from ism_adapter.transformers.compute.os_image import OsImageTransformer

TRANSFORMERS = {
    "instance": InstanceTransformer(),
    "os_image": OsImageTransformer(),
}

__all__ = ["InstanceTransformer", "OsImageTransformer", "TRANSFORMERS"]
