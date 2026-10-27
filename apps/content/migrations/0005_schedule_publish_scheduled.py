# Registers a Django-Q2 schedule that publishes pages whose go-live time has
# passed, once a minute (CMS-2 scheduled publishing).
from django.db import migrations

FUNC = "apps.core.tasks.publish_scheduled"


def create_schedule(apps, schema_editor):
    Schedule = apps.get_model("django_q", "Schedule")
    Schedule.objects.update_or_create(
        func=FUNC,
        defaults={"name": "انتشار صفحات زمان‌بندی‌شده", "schedule_type": "I", "minutes": 1, "repeats": -1},
    )


def remove_schedule(apps, schema_editor):
    apps.get_model("django_q", "Schedule").objects.filter(func=FUNC).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0004_servicepage_case_study_servicepage_cover_image_and_more"),
        ("django_q", "0019_alter_task_options_alter_ormq_key_alter_ormq_lock_and_more"),
    ]

    operations = [migrations.RunPython(create_schedule, remove_schedule)]
