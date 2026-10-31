from django import forms

from apps.core.fields import MobileFormField
from apps.core.text import to_en_digits


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
