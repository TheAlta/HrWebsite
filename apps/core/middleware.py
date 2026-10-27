UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content")


class UTMMiddleware:
    """Remember the first campaign that brought a visitor, so leads show their source."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if "utm" not in request.session:
            utm = {k: request.GET[k][:100] for k in UTM_KEYS if request.GET.get(k)}
            if utm:
                request.session["utm"] = utm
        return self.get_response(request)
