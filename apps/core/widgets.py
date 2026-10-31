import datetime as dt

from django import forms

from . import jalali


class JalaliDateTimeInput(forms.TextInput):
    """Date and time entry in the panel, in the Shamsi calendar (spec section 4).

    The form field stays a normal DateTimeField: this widget turns what the owner
    typed into a Gregorian string on the way in and back into Shamsi on the way out.
    Text it cannot read passes through unchanged, so the field reports the error.
    """

    GREGORIAN_FORMAT = "%Y-%m-%d %H:%M"

    def __init__(self, attrs=None):
        super().__init__({"dir": "ltr", "placeholder": "۱۴۰۵/۰۸/۲۰ ۱۸:۳۰", **(attrs or {})})

    def value_from_datadict(self, data, files, name):
        value = super().value_from_datadict(data, files, name)
        if not value:
            return value
        try:
            return jalali.parse_datetime(value).strftime(self.GREGORIAN_FORMAT)
        except ValueError:
            return value

    def format_value(self, value):
        if isinstance(value, str):
            # A form shown again after an error holds the converted string
            try:
                value = dt.datetime.strptime(value, self.GREGORIAN_FORMAT)
            except ValueError:
                return value
        if isinstance(value, dt.datetime):
            return jalali.format_input(value)
        return super().format_value(value)
