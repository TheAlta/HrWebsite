# Django-Q2 schedule: drop login records older than 90 days, once a day (spec section 11).
from django.db import migrations

FUNC = "apps.accounts.services.trim_login_logs"


def create_schedule(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.update_or_create(
        func=FUNC,
        defaults={
            "name": "پاک کردن سوابق ورود قدیمی",
            "schedule_type": "D",
            "repeats": -1,
        },
    )


def remove_schedule(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.filter(func=FUNC).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_organization"),
        ("django_q", "0019_alter_task_options_alter_ormq_key_alter_ormq_lock_and_more"),
    ]

    operations = [migrations.RunPython(create_schedule, remove_schedule)]
