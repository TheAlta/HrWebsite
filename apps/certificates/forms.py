from django import forms

from apps.core.text import to_fa_digits


class VerifyForm(forms.Form):
    code = forms.CharField(
        label="کد استعلام",
        max_length=20,
        help_text="کد روی گواهی، مثل 7K3MQ-9XPRT",
        widget=forms.TextInput(
            attrs={"dir": "ltr", "autocomplete": "off", "autocapitalize": "characters"}
        ),
    )


class AttendeeChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, registration):
        user = registration.user
        return f"{user.get_full_name() or 'بدون نام'} — {to_fa_digits(user.mobile)}"


class IssueForm(forms.Form):
    def __init__(self, *args, registrations, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["registrations"] = AttendeeChoiceField(
            label="حاضران",
            queryset=registrations,
            widget=forms.CheckboxSelectMultiple,
            initial=list(registrations),
            help_text="برای هر نفری که تیک دارد گواهی صادر و پیامک می‌شود.",
            error_messages={"required": "دست‌کم یک نفر را انتخاب کنید."},
        )
