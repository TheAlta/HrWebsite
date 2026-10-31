# Django-Q2 schedule: re-check open payments every 10 minutes (spec section 8.2, step 8).
from django.db import migrations

FUNC = "apps.payments.services.reconcile"


def create_schedule(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.update_or_create(
        func=FUNC,
        defaults={"name": "بررسی پرداخت‌های معلق", "schedule_type": "I", "minutes": 10, "repeats": -1},
    )


def remove_schedule(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.filter(func=FUNC).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0001_initial"),
        ("django_q", "0019_alter_task_options_alter_ormq_key_alter_ormq_lock_and_more"),
    ]

    operations = [migrations.RunPython(create_schedule, remove_schedule)]
