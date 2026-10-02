"""Storage 대분류 (volume, volume_snapshot 등).

마일스톤 문서(2026H2-ism-migration-milestone.md §1) 기준 분류. volume_snapshot은
별도 티켓에서 진행 중이라 이 서브패키지에 아직 없을 수 있다.
"""

from ism_adapter.transformers.storage.volume import VolumeTransformer
from ism_adapter.transformers.storage.volume_snapshot import VolumeSnapshotTransformer

TRANSFORMERS = {
    "volume": VolumeTransformer(),
    "volume_snapshot": VolumeSnapshotTransformer(),
}

__all__ = ["VolumeTransformer", "VolumeSnapshotTransformer", "TRANSFORMERS"]
