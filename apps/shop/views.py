import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.payments.views import begin_payment

from . import services
from .cart import Cart
from .forms import AddressForm
from .models import DownloadToken, Product, Shipment


def product(request, page, slug):
    item = get_object_or_404(Product.objects.on_sale(), slug=slug)
    return page.render(
        request,
        context_overrides={"product": item, "schema": _schema(request, item)},
        template="shop/product.html",
    )


def _schema(request, item):
    return {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": item.title,
        "description": item.summary,
        "url": request.build_absolute_uri(item.url),
        "offers": {
            "@type": "Offer",
            "price": item.price,
            "priceCurrency": "IRR",
            "availability": "https://schema.org/" + ("InStock" if item.in_stock else "OutOfStock"),
        },
    }


def _cart_response(request):
    """HTMX swaps the cart in place; without JavaScript the page reloads."""
    if not request.htmx:
        return redirect("shop:cart")
    return render(request, "shop/includes/cart_body.html", _cart_context(request))


def _cart_context(request):
    cart = Cart(request.session)
    quote, coupon_error = services.quote_cart(cart)
    return {"quote": quote, "cart": cart, "coupon_error": coupon_error}


@require_GET
def cart_view(request):
    return render(request, "shop/cart.html", _cart_context(request))


@require_POST
def cart_add(request, pk):
    item = get_object_or_404(Product.objects.on_sale(), pk=pk)
    if not item.in_stock:
        messages.error(request, "این محصول موجود نیست.")
        return redirect(item.url)
    Cart(request.session).add(item)
    return redirect("shop:cart")


@require_POST
def cart_update(request, pk):
    item = get_object_or_404(Product, pk=pk)
    try:
        qty = int(request.POST.get("qty", 0))
    except ValueError:
        qty = 0
    Cart(request.session).set(item, qty)
    return _cart_response(request)


@require_POST
def cart_coupon(request):
    cart = Cart(request.session)
    cart.coupon_code = services.normalize_code(request.POST.get("code", ""))[:40]
    return _cart_response(request)


def _last_address(user):
    shipment = Shipment.objects.filter(order__user=user).first()
    if shipment is None:
        return {"mobile": user.mobile}
    return {name: getattr(shipment, name) for name in AddressForm.base_fields}


@login_required
@require_http_methods(["GET", "POST"])
def checkout(request):
    cart = Cart(request.session)
    quote, coupon_error = services.quote_cart(cart)
    if not quote.lines:
        return redirect("shop:cart")
    if coupon_error:
        # The discount changed since the customer saw the cart: never charge without showing it
        messages.error(request, coupon_error)
        cart.coupon_code = ""
        return redirect("shop:cart")

    form = None
    if quote.needs_shipping:
        form = AddressForm(request.POST or None, initial=_last_address(request.user))
    if request.method == "POST" and (form is None or form.is_valid()):
        try:
            order = services.place_order(request.user, cart, form.cleaned_data if form else None)
        except services.ShopError as exc:
            messages.error(request, str(exc))
            return redirect("shop:cart")
        if order.total == 0:
            return redirect("orders:detail", number=order.number)
        return begin_payment(request, order)
    return render(request, "shop/checkout.html", {"quote": quote, "form": form})


@login_required
@require_GET
def download(request, token):
    """The only way to a paid file (spec section 8.4): owner only, limited and expiring."""
    row = get_object_or_404(
        DownloadToken.objects.select_related("product"), token=token, user=request.user
    )
    if not row.is_valid:
        return render(request, "shop/download_expired.html", {"token": row}, status=410)
    try:
        handle = row.product.file.open("rb")
    except FileNotFoundError:
        raise Http404 from None
    if not services.consume_download(row):
        handle.close()
        return render(request, "shop/download_expired.html", {"token": row}, status=410)
    extension = os.path.splitext(row.product.file.name)[1]
    response = FileResponse(handle, as_attachment=True, filename=f"{row.product.slug}{extension}")
    response["Cache-Control"] = "private, no-store"
    return response
