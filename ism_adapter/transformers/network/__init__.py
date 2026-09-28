from ism_adapter.transformers.network.network import NetworkTransformer
from ism_adapter.transformers.network.router import RouterTransformer

TRANSFORMERS = {
    "network": NetworkTransformer(),
    "router": RouterTransformer(),
}

__all__ = ["NetworkTransformer", "RouterTransformer", "TRANSFORMERS"]
