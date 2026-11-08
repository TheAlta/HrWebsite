"""Content-Security-Policy headers (spec section 11, REPORT #051)."""

from csp.middleware import CSPMiddleware, PolicyParts
from django.conf import settings

from .http import is_panel_path


class SiteCSPMiddleware(CSPMiddleware):
    """The strict policy for the site; the panel's own looser one for the panel.

    Wagtail's admin needs inline scripts and styles that the public pages never
    use, so the panel gets its own policy instead of the site's being loosened.
    """

    def get_policy_parts(self, request, response, report_only=False) -> PolicyParts:
        parts = super().get_policy_parts(request, response, report_only)
        if not report_only and parts.config is None and is_panel_path(request.path_info):
            parts.config = settings.PANEL_CONTENT_SECURITY_POLICY
        return parts
