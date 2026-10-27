from django import forms

from apps.core.text import normalize_fa


class CommentForm(forms.Form):
    name = forms.CharField(label="نام", max_length=80)
    email = forms.EmailField(label="ایمیل (اختیاری، نمایش داده نمی‌شود)", required=False)
    text = forms.CharField(
        label="نظر شما", min_length=3, max_length=2000, widget=forms.Textarea(attrs={"rows": 4})
    )
    # Honeypot: hidden from people with CSS; bots tend to fill every field
    website = forms.CharField(required=False, label="وب‌سایت")

    def clean_name(self):
        return normalize_fa(self.cleaned_data["name"])

    def clean_text(self):
        return normalize_fa(self.cleaned_data["text"])

    @property
    def is_bot(self):
        return bool(self.data.get("website"))
