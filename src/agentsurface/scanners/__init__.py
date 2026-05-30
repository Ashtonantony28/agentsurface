"""Scanner registry: maps dimension_id to Scanner class."""
from agentsurface.scanners.base import Scanner
from agentsurface.scanners.base import Target as Target
from agentsurface.scanners.base import make_signal as make_signal

# Registry populated lazily on first import of each scanner module
_REGISTRY: dict[str, type[Scanner]] = {}


def register(cls: type[Scanner]) -> type[Scanner]:
    """Decorator to register a Scanner subclass."""
    _REGISTRY[cls.dimension_id] = cls
    return cls


def get_all_scanner_classes() -> list[type[Scanner]]:
    """Return all registered Scanner classes, in dimension order."""
    # Import all scanner modules to trigger registration
    from agentsurface.scanners import auth, discovery, docs, errors, openapi, sdk  # noqa: F401
    return list(_REGISTRY.values())
