"""OmniRiff host control runtime. No network or device work on import."""
from .router import Router
from .runtime import Runtime
__all__ = ['Router', 'Runtime']
