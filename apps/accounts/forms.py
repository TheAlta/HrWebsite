from django import forms

from apps.core.fields import MobileFormField
from apps.core.text import normalize_fa, to_en_digits

from .models import User


class MobileForm(forms.Form):
    mobile = MobileFormField(
        label="شماره موبایل",
        max_length=11,
        widget=forms.TextInput(
            attrs={"inputmode": "tel", "autocomplete": "tel", "placeholder": "۰۹۱۲۱۲۳۴۵۶۷"}
        ),
    )


class CodeForm(forms.Form):
    mobile = MobileFormField(max_length=11, widget=forms.HiddenInput)
    code = forms.CharField(
        label="کد تأیید",
        max_length=5,
        min_length=5,
        widget=forms.TextInput(
            attrs={"inputmode": "numeric", "autocomplete": "one-time-code", "dir": "ltr"}
        ),
    )

    def clean_code(self):
        code = to_en_digits(self.cleaned_data["code"].strip())
        if not code.isdigit():
            raise forms.ValidationError("کد فقط از عدد تشکیل شده است.")
        return code


class TwoFactorForm(forms.Form):
    """The authenticator app's 6 digits, or one 8-character backup code."""

    code = forms.CharField(
        label="کد",
        max_length=20,
        widget=forms.TextInput(
            attrs={"inputmode": "text", "autocomplete": "one-time-code", "dir": "ltr"}
        ),
    )

    def clean_code(self):
        return "".join(to_en_digits(self.cleaned_data["code"]).lower().split())


class ProfileForm(forms.ModelForm):
    """Name and email appear on invoices. The mobile is the login, so it is not editable here."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        labels = {"first_name": "نام", "last_name": "نام خانوادگی", "email": "ایمیل"}

    def clean_first_name(self):
        return normalize_fa(self.cleaned_data["first_name"])

    def clean_last_name(self):
        return normalize_fa(self.cleaned_data["last_name"])
