from .forms import SubscribeForm


def newsletter(request):
    """The empty footer form; the form after a submit comes from the view."""
    return {"newsletter_form": SubscribeForm()}
