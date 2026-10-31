from wagtail import hooks
from wagtail.admin.viewsets.model import ModelViewSet, ModelViewSetGroup

from .models import Availability, Booking, SessionType, TimeOff


class BookingViewSet(ModelViewSet):
    model = Booking
    name = "panel_bookings"
    url_prefix = "bookings"
    icon = "date"
    menu_label = "رزروها"
    list_display = ["start_display", "session_type", "user", "status"]
    list_filter = ["status", "session_type"]
    search_fields = ["user__mobile", "user__first_name", "user__last_name"]
    ordering = ["-start_at"]
    copy_view_enabled = False
    inspect_view_enabled = True


class SessionTypeViewSet(ModelViewSet):
    model = SessionType
    name = "panel_session_types"
    url_prefix = "session-types"
    icon = "time"
    menu_label = "انواع جلسه"
    list_display = ["title", "mode", "duration_min", "is_active"]
    form_fields = [
        "title",
        "description",
        "mode",
        "duration_min",
        "price",
        "buffer_min",
        "meeting_link",
        "is_active",
        "sort_order",
    ]


class AvailabilityViewSet(ModelViewSet):
    model = Availability
    name = "panel_availability"
    url_prefix = "availability"
    icon = "calendar"
    menu_label = "ساعات کاری"
    list_display = ["weekday", "start_time", "end_time"]
    form_fields = ["weekday", "start_time", "end_time"]


class TimeOffViewSet(ModelViewSet):
    model = TimeOff
    name = "panel_time_off"
    url_prefix = "time-off"
    icon = "warning"
    menu_label = "مرخصی و تعطیلی"
    list_display = ["reason", "start", "end"]
    form_fields = ["start", "end", "reason"]


class BookingGroup(ModelViewSetGroup):
    menu_label = "رزرو جلسه"
    menu_icon = "date"
    menu_order = 160
    items = (BookingViewSet, SessionTypeViewSet, AvailabilityViewSet, TimeOffViewSet)


@hooks.register("register_admin_viewset")
def register_booking_group():
    return BookingGroup()
