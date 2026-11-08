# Django-Q2 schedule: read the owner's calendars every 10 minutes (BOOK-6).
# The job does nothing while BUSY_CALENDAR_URLS is empty.
from django.db import migrations

FUNC = "apps.booking.services.sync_calendars"


def create_schedule(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.update_or_create(
        func=FUNC,
        defaults={
            "name": "خواندن زمان‌های اشغال تقویم",
            "schedule_type": "I",
            "minutes": 10,
            "repeats": -1,
        },
    )


def remove_schedule(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.filter(func=FUNC).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("booking", "0004_calendarbusy_calendarsync"),
        ("django_q", "0019_alter_task_options_alter_ormq_key_alter_ormq_lock_and_more"),
    ]

    operations = [migrations.RunPython(create_schedule, remove_schedule)]
