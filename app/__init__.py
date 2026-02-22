"""Celluloid Vision API Application Package"""

__all__ = ["app"]


def __getattr__(name):
    """Lazy import to avoid circular dependencies"""
    if name == "app":
        from app.main import app

        return app
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
