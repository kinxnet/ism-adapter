"""Share(NAS) 대분류 (share, share_network, share_snapshot 등).

마일스톤 문서(2026H2-ism-migration-milestone.md §1) 기준 분류. share_network/
share_snapshot은 별도 티켓에서 진행 중이라 이 서브패키지에 아직 없을 수 있다.
"""

from ism_adapter.transformers.share.share import ShareTransformer
from ism_adapter.transformers.share.share_snapshot import ShareSnapshotTransformer

TRANSFORMERS = {
    "share": ShareTransformer(),
    "share_snapshot": ShareSnapshotTransformer(),
}

__all__ = ["ShareTransformer", "ShareSnapshotTransformer", "TRANSFORMERS"]
