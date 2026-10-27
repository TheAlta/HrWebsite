# Django-Q2 schedule: hourly check for abnormal SMS volume (OTP abuse without captcha, REPORT #023).
from django.db import migrations

FUNC = "apps.notifications.services.check_sms_volume"


def create_schedule(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.update_or_create(
        func=FUNC,
        defaults={"name": "بررسی حجم پیامک", "schedule_type": "H", "repeats": -1},
    )


def remove_schedule(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.filter(func=FUNC).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0001_initial"),
        ("django_q", "0019_alter_task_options_alter_ormq_key_alter_ormq_lock_and_more"),
    ]

    operations = [migrations.RunPython(create_schedule, remove_schedule)]
