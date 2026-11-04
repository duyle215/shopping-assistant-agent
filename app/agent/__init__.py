"""Agent package - export ShoppingAgent (nap luoi de tranh import vong voi services)."""

__all__ = ["ShoppingAgent"]


def __getattr__(name):
    if name == "ShoppingAgent":
        from .core import ShoppingAgent

        return ShoppingAgent
    raise AttributeError(name)
