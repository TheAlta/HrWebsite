# Django-Q2 schedule: email follow-up reminders for lead notes every 15 minutes (LEAD-5).
from django.db import migrations

FUNC = "apps.crm.services.send_followup_reminders"


def create_schedule(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.update_or_create(
        func=FUNC,
        defaults={"name": "یادآور پیگیری سرنخ‌ها", "schedule_type": "I", "minutes": 15, "repeats": -1},
    )


def remove_schedule(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.filter(func=FUNC).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0001_initial"),
        ("django_q", "0019_alter_task_options_alter_ormq_key_alter_ormq_lock_and_more"),
    ]

    operations = [migrations.RunPython(create_schedule, remove_schedule)]
