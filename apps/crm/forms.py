"""Public lead forms. Common contact fields are stored as Lead columns; every
other cleaned field goes into Lead.payload (see services.create_lead)."""

from django import forms

from apps.core.fields import MobileFormField
from apps.core.text import normalize_fa

from .models import LeadType

TOPICS = [
    ("performance", "ارزیابی عملکرد"),
    ("structure", "ساختار سازمانی"),
    ("recruitment", "جذب و استخدام"),
    ("training", "آموزش و توسعه"),
    ("career", "مسیر شغلی"),
    ("other", "سایر"),
]
COMPANY_SIZES = [
    ("", "انتخاب کنید"),
    ("1-10", "۱ تا ۱۰ نفر"),
    ("11-50", "۱۱ تا ۵۰ نفر"),
    ("51-200", "۵۱ تا ۲۰۰ نفر"),
    ("201-1000", "۲۰۱ تا ۱۰۰۰ نفر"),
    ("1000+", "بیش از ۱۰۰۰ نفر"),
]
TIMEFRAMES = [
    ("", "انتخاب کنید"),
    ("asap", "هرچه زودتر"),
    ("1-month", "تا یک ماه آینده"),
    ("3-months", "تا سه ماه آینده"),
    ("exploring", "فعلاً در حال بررسی"),
]
BUDGETS = [
    ("", "انتخاب کنید"),
    ("unknown", "هنوز مشخص نیست"),
    ("lt-50", "کمتر از ۵۰ میلیون تومان"),
    ("50-200", "۵۰ تا ۲۰۰ میلیون تومان"),
    ("gt-200", "بیش از ۲۰۰ میلیون تومان"),
]
DELIVERY = [("in_person", "حضوری"), ("online", "آنلاین"), ("hybrid", "ترکیبی")]

# Labels for payload keys, used when showing a lead in emails and the panel
PAYLOAD_LABELS = {
    "audience": "نوع",
    "topics": "موضوع‌ها",
    "description": "توضیح",
    "company_size": "اندازه سازمان",
    "timeframe": "زمان",
    "headcount": "تعداد شرکت‌کنندگان",
    "topic": "موضوع آموزش",
    "budget": "بودجه",
    "delivery": "نحوه برگزاری",
    "document": "فایل",
}

CONTACT_FIELDS = ("name", "mobile", "email", "company", "marketing_consent")


class LeadForm(forms.Form):
    lead_type: str
    name = forms.CharField(label="نام و نام خانوادگی", max_length=120)
    mobile = MobileFormField(
        label="موبایل",
        max_length=11,
        widget=forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel"}),
    )
    email = forms.EmailField(label="ایمیل", required=False)
    marketing_consent = forms.BooleanField(
        label="مایلم خبر دوره‌ها و مطالب جدید را با پیامک یا ایمیل دریافت کنم.", required=False
    )
    # Honeypot (no captcha, REPORT #023)
    website = forms.CharField(required=False)

    @property
    def is_bot(self):
        return bool(self.data.get("website"))

    def clean_name(self):
        return normalize_fa(self.cleaned_data["name"])

    def payload(self):
        """Readable form answers that are not Lead columns."""
        data = {}
        for name, value in self.cleaned_data.items():
            if name in CONTACT_FIELDS or name == "website" or value in ("", None, []):
                continue
            field = self.fields[name]
            if isinstance(field, forms.MultipleChoiceField):
                labels = dict(field.choices)
                value = [labels.get(v, v) for v in value]
            elif isinstance(field, forms.ChoiceField):
                value = dict(field.choices).get(value, value)
            data[name] = value
        return data


class CallbackForm(LeadForm):
    """«با من تماس بگیرید» — name and mobile only (LEAD-3)."""

    lead_type = LeadType.CALLBACK

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields["email"]


class ConsultationForm(LeadForm):
    """Multi-step consultation request (LEAD-1). Steps are grouped in the template."""

    lead_type = LeadType.CONSULTATION

    audience = forms.ChoiceField(
        label="درخواست برای",
        choices=[("individual", "خودم (مشاوره فردی)"), ("corporate", "سازمانم")],
        widget=forms.RadioSelect,
        initial="corporate",
    )
    topics = forms.MultipleChoiceField(
        label="در چه زمینه‌ای؟", choices=TOPICS, widget=forms.CheckboxSelectMultiple
    )
    description = forms.CharField(
        label="کمی توضیح دهید",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    company = forms.CharField(label="نام سازمان", required=False, max_length=200)
    company_size = forms.ChoiceField(label="اندازه سازمان", choices=COMPANY_SIZES, required=False)
    timeframe = forms.ChoiceField(label="چه زمانی؟", choices=TIMEFRAMES, required=False)

    # Field order defines the steps: need → organisation → contact
    STEPS = [
        ("نیاز شما", ["audience", "topics", "description"]),
        ("سازمان و زمان", ["company", "company_size", "timeframe"]),
        ("اطلاعات تماس", ["name", "mobile", "email", "marketing_consent"]),
    ]

    def clean(self):
        data = super().clean()
        if data.get("audience") == "corporate" and not data.get("company"):
            self.add_error("company", "برای درخواست سازمانی، نام سازمان را بنویسید.")
        return data

    def steps(self):
        return [(title, [self[name] for name in names]) for title, names in self.STEPS]

    def first_error_step(self):
        """Index of the first step with an error, so the form reopens there."""
        if self.is_bound and self.errors:
            for index, (_, names) in enumerate(self.STEPS):
                if any(name in self.errors for name in names):
                    return index
        return 0


class CorporateTrainingForm(LeadForm):
    """Corporate training request (LEAD-2)."""

    lead_type = LeadType.CORPORATE_TRAINING

    company = forms.CharField(label="نام سازمان", max_length=200)
    topic = forms.CharField(label="موضوع آموزش", max_length=200)
    headcount = forms.IntegerField(label="تعداد شرکت‌کنندگان", min_value=1, max_value=100000)
    delivery = forms.ChoiceField(
        label="نحوه برگزاری", choices=DELIVERY, widget=forms.RadioSelect, initial="in_person"
    )
    budget = forms.ChoiceField(label="بودجه تقریبی", choices=BUDGETS, required=False)
    timeframe = forms.ChoiceField(label="زمان برگزاری", choices=TIMEFRAMES, required=False)


class DownloadForm(LeadForm):
    """Catalog / CV download in exchange for contact details (LEAD-4)."""

    lead_type = LeadType.DOWNLOAD

    document = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mobile"].required = False

    def clean(self):
        data = super().clean()
        if not data.get("mobile") and not data.get("email"):
            raise forms.ValidationError("موبایل یا ایمیل را وارد کنید.")
        return data

    def clean_document(self):
        from wagtail.documents import get_document_model

        doc = get_document_model().objects.filter(pk=self.cleaned_data["document"]).first()
        if doc is None:
            raise forms.ValidationError("فایل پیدا نشد.")
        self.document_obj = doc
        return doc.pk

    def payload(self):
        data = super().payload()
        data["document"] = self.document_obj.title
        return data


FORMS = {
    LeadType.CONSULTATION: ConsultationForm,
    LeadType.CORPORATE_TRAINING: CorporateTrainingForm,
    LeadType.CALLBACK: CallbackForm,
    LeadType.DOWNLOAD: DownloadForm,
}
