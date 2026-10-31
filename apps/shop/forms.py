from django import forms

from apps.core.fields import MobileFormField
from apps.core.text import normalize_fa, to_en_digits


class AddressForm(forms.Form):
    """Shipping details, only for printed books (spec section 8.4). Keys are Shipment fields."""

    recipient = forms.CharField(label="نام گیرنده", max_length=120)
    mobile = MobileFormField(
        label="موبایل گیرنده",
        max_length=11,
        widget=forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel"}),
    )
    province = forms.CharField(label="استان", max_length=60)
    city = forms.CharField(label="شهر", max_length=60)
    address = forms.CharField(
        label="نشانی کامل", max_length=500, widget=forms.Textarea(attrs={"rows": 3})
    )
    postal_code = forms.CharField(
        label="کد پستی",
        max_length=10,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "dir": "ltr"}),
    )

    def clean_recipient(self):
        return normalize_fa(self.cleaned_data["recipient"])

    def clean_postal_code(self):
        code = to_en_digits(self.cleaned_data["postal_code"]).strip()
        if len(code) != 10 or not code.isdigit():
            raise forms.ValidationError("کد پستی ۱۰ رقم است.")
        return code
