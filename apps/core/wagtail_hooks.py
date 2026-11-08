from wagtail import hooks

from .panel import LOG_ACTIONS


@hooks.register("register_log_actions")
def register_panel_actions(actions):
    """Labels for the panel actions in the history, such as a refund (spec section 11)."""
    for action, label in LOG_ACTIONS.items():
        actions.register_action(action, label, label)
