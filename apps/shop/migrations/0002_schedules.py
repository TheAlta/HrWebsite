# Django-Q2 schedule: give back the stock of unpaid orders every 5 minutes.
from django.db import migrations

FUNC = "apps.shop.services.release_unpaid"


def create_schedule(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.update_or_create(
        func=FUNC,
        defaults={
            "name": "آزادسازی موجودی سفارش‌های پرداخت‌نشده",
            "schedule_type": "I",
            "minutes": 5,
            "repeats": -1,
        },
    )


def remove_schedule(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.filter(func=FUNC).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0001_initial"),
        ("django_q", "0019_alter_task_options_alter_ormq_key_alter_ormq_lock_and_more"),
    ]

    operations = [migrations.RunPython(create_schedule, remove_schedule)]
