"""Panel roles (ADM-3): what each kind of staff member may see and do.

Run with `manage.py setup_roles`; deployment runs it after every migrate. It only
adds permissions, so anything the owner grants by hand in the panel stays.
Leads and their notes are confidential (spec section 11): only the full admin
role sees them.
"""

from django.contrib.auth.models import Group, Permission
from wagtail.models import Collection, GroupCollectionPermission, GroupPagePermission, Page

FULL_ADMIN = "مدیر کل"
EDITOR = "ویراستار محتوا"
SUPPORT = "پشتیبان"


def _crud(app, *models):
    return [
        f"{app}.{action}_{model}"
        for model in models
        for action in ("add", "change", "delete", "view")
    ]


ROLE_PERMISSIONS = {
    EDITOR: [
        "wagtailadmin.access_admin",
        *_crud("content", "category", "teammember", "articletag"),
        "content.view_comment",
        "content.change_comment",
        "content.delete_comment",
        *_crud("portfolio", "client", "project", "testimonial"),
    ],
    SUPPORT: [
        "wagtailadmin.access_admin",
        "booking.view_booking",
        "booking.change_booking",
        "booking.view_sessiontype",
        *_crud("booking", "availability", "timeoff"),
        "events.view_registration",
        "events.change_registration",
        "certificates.view_certificate",
        "certificates.add_certificate",
        "certificates.change_certificate",
        "shop.view_product",
        "shop.view_shipment",
        "shop.change_shipment",
        "orders.view_order",
        "payments.view_payment",
        "billing.view_invoice",
        "billing.view_proforma",
        "notifications.view_notification",
    ],
}

PAGE_PERMISSIONS = {
    FULL_ADMIN: [
        "add_page",
        "change_page",
        "publish_page",
        "bulk_delete_page",
        "lock_page",
        "unlock_page",
    ],
    EDITOR: ["add_page", "change_page", "publish_page", "lock_page", "unlock_page"],
}

COLLECTION_PERMISSIONS = {
    FULL_ADMIN: [
        "wagtailimages.add_image",
        "wagtailimages.change_image",
        "wagtailimages.delete_image",
        "wagtailimages.choose_image",
        "wagtaildocs.add_document",
        "wagtaildocs.change_document",
        "wagtaildocs.delete_document",
        "wagtaildocs.choose_document",
    ],
    EDITOR: [
        "wagtailimages.add_image",
        "wagtailimages.change_image",
        "wagtailimages.choose_image",
        "wagtaildocs.add_document",
        "wagtaildocs.change_document",
        "wagtaildocs.choose_document",
    ],
    SUPPORT: ["wagtailimages.choose_image", "wagtaildocs.choose_document"],
}


def _permission(dotted: str) -> Permission:
    """Fails loudly on a typo, so a role never silently misses a permission."""
    app_label, codename = dotted.split(".")
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def setup_roles() -> list[Group]:
    groups = []
    root_page = Page.get_first_root_node()
    root_collection = Collection.get_first_root_node()
    for name in (FULL_ADMIN, EDITOR, SUPPORT):
        group, _ = Group.objects.get_or_create(name=name)
        if name == FULL_ADMIN:
            group.permissions.add(*Permission.objects.all())
        else:
            group.permissions.add(*(_permission(code) for code in ROLE_PERMISSIONS[name]))
        for codename in PAGE_PERMISSIONS.get(name, []):
            GroupPagePermission.objects.get_or_create(
                group=group,
                page=root_page,
                permission=_permission(f"wagtailcore.{codename}"),
            )
        for dotted in COLLECTION_PERMISSIONS.get(name, []):
            GroupCollectionPermission.objects.get_or_create(
                group=group, collection=root_collection, permission=_permission(dotted)
            )
        groups.append(group)
    return groups
