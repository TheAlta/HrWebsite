from django import forms

from apps.core.fields import MobileFormField


class _Form(forms.Form):
    mobile = MobileFormField(max_length=11)


def test_form_field_normalises_before_length_check():
    form = _Form(data={"mobile": "+98 912 123 4567"})
    assert form.is_valid(), form.errors
    assert form.cleaned_data["mobile"] == "09121234567"


def test_form_field_rejects_invalid_number_with_persian_message():
    form = _Form(data={"mobile": "12"})
    assert not form.is_valid()
    assert form.errors["mobile"] == ["شماره موبایل معتبر نیست."]
