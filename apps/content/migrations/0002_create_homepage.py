# Replaces Wagtail's default "Welcome" page with our HomePage and makes it the
# site root. Adapted from Wagtail's project template.
from django.db import migrations


def create_homepage(apps, schema_editor):
    ContentType = apps.get_model("contenttypes.ContentType")
    Page = apps.get_model("wagtailcore.Page")
    Site = apps.get_model("wagtailcore.Site")
    HomePage = apps.get_model("content.HomePage")

    # Delete the default homepage created by wagtailcore.0002_initial_data
    page_content_type = ContentType.objects.get(model="page", app_label="wagtailcore")
    Page.objects.filter(content_type=page_content_type, slug="home", depth=2).delete()

    homepage_content_type, __ = ContentType.objects.get_or_create(
        model="homepage", app_label="content"
    )
    homepage = HomePage.objects.create(
        title="مشاوره منابع انسانی",
        draft_title="مشاوره منابع انسانی",
        slug="home",
        content_type=homepage_content_type,
        path="00010001",
        depth=2,
        numchild=0,
        url_path="/home/",
    )
    Site.objects.create(hostname="localhost", root_page=homepage, is_default_site=True)


def remove_homepage(apps, schema_editor):
    ContentType = apps.get_model("contenttypes.ContentType")
    HomePage = apps.get_model("content.HomePage")
    # Page and Site rows cascade
    HomePage.objects.filter(slug="home", depth=2).delete()
    ContentType.objects.filter(model="homepage", app_label="content").delete()


class Migration(migrations.Migration):
    run_before = [
        ("wagtailcore", "0053_locale_model"),
    ]

    dependencies = [
        ("content", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_homepage, remove_homepage),
    ]
