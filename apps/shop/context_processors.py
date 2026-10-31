from .cart import Cart


def cart(request):
    """Item count for the header. Views use `Cart` directly."""
    if not hasattr(request, "session"):
        return {}
    return {"cart_count": Cart(request.session).count}
