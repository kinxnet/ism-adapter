"""자원 타입 -> transformer 매핑.

마일스톤 문서(2026H2-ism-migration-milestone.md §1) 대분류를 그대로 폴더로
반영했다: compute, storage, network, share, loadbalancer, managed,
third_party. (Keymanager는 유일한 자원 secret이 "과금 무관, 대상 아님"으로
명시되어 있어 폴더를 만들지 않았다.)

각 대분류 서브패키지가 자신의 `TRANSFORMERS` dict를 노출하면 여기서 합친다
— 새 대분류에 자원을 추가할 때 이 파일을 건드릴 필요 없이 해당 서브패키지의
`__init__.py`에 dict 항목만 추가하면 된다.
"""

from ism_adapter.transformers.base import ResourcePayload, SimpleResourceTransformer
from ism_adapter.transformers.compute import TRANSFORMERS as _COMPUTE_TRANSFORMERS
from ism_adapter.transformers.network import TRANSFORMERS as _NETWORK_TRANSFORMERS
from ism_adapter.transformers.share import TRANSFORMERS as _SHARE_TRANSFORMERS
from ism_adapter.transformers.storage import TRANSFORMERS as _STORAGE_TRANSFORMERS

TRANSFORMERS: dict[str, SimpleResourceTransformer] = {
    **_NETWORK_TRANSFORMERS,
    **_STORAGE_TRANSFORMERS,
    **_SHARE_TRANSFORMERS,
    **_COMPUTE_TRANSFORMERS,
}

__all__ = ["ResourcePayload", "SimpleResourceTransformer", "TRANSFORMERS"]
