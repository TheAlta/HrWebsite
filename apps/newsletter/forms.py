from django import forms

from apps.core.fields import MobileFormField


class SubscribeForm(forms.Form):
    email = forms.EmailField(label="ایمیل", required=False)
    mobile = MobileFormField(
        label="موبایل",
        required=False,
        max_length=11,
        widget=forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel"}),
    )
    consent = forms.BooleanField(
        label="موافقم خبر دوره‌ها و مطالب تازه برایم فرستاده شود.",
        error_messages={"required": "برای عضویت، این گزینه را تأیید کنید."},
    )
    # Honeypot (no captcha, REPORT #023)
    website = forms.CharField(required=False)

    @property
    def is_bot(self):
        return bool(self.data.get("website"))

    def clean(self):
        data = super().clean()
        if not data.get("email") and not data.get("mobile") and not self.errors:
            raise forms.ValidationError("ایمیل یا موبایل را وارد کنید.")
        return data
