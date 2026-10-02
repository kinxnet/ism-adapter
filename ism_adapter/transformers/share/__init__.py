"""Share(NAS) 대분류 (share, share_network, share_snapshot 등).

마일스톤 문서(2026H2-ism-migration-milestone.md §1) 기준 분류. 아직 이관된
자원 없음.
"""

from ism_adapter.transformers.share.share_snapshot import ShareSnapshotTransformer

TRANSFORMERS = {
    "share_snapshot": ShareSnapshotTransformer(),
}

__all__ = ["ShareSnapshotTransformer", "TRANSFORMERS"]
