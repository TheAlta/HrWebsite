# Django-Q2 schedules: free unpaid seats every minute (spec section 8.3), send event
# reminders every 5 minutes and recordings every 15 (EVT-4).
from django.db import migrations

SCHEDULES = [
    ("apps.events.services.housekeeping", "آزادسازی صندلی و لیست انتظار", 1),
    ("apps.events.services.send_reminders", "یادآور رویدادها", 5),
    ("apps.events.services.send_recordings", "اطلاع‌رسانی ضبط رویدادها", 15),
]


def create_schedules(apps, schema_editor):
    Schedule = apps.get_model("django_q", "Schedule")
    for func, name, minutes in SCHEDULES:
        Schedule.objects.update_or_create(
            func=func,
            defaults={"name": name, "schedule_type": "I", "minutes": minutes, "repeats": -1},
        )


def remove_schedules(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.filter(
        func__in=[func for func, _, _ in SCHEDULES]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0001_initial"),
        ("django_q", "0019_alter_task_options_alter_ormq_key_alter_ormq_lock_and_more"),
    ]

    operations = [migrations.RunPython(create_schedules, remove_schedules)]
