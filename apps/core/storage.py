from django.core.files.storage import storages


def private_storage():
    """Files no URL reaches directly: paid products and invoices."""
    return storages["private"]
