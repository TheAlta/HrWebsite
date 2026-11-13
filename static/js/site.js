// Alpine components the page markup refers to by name. Under the site's CSP the
// Alpine build cannot run free JavaScript or reach globals such as confirm(), so
// anything beyond a simple expression lives here. Loaded before Alpine.
document.addEventListener("alpine:init", () => {
  // <form x-data="confirmSubmit" data-confirm="..." @submit="check">
  Alpine.data("confirmSubmit", () => ({
    check(event) {
      if (!window.confirm(this.$el.dataset.confirm)) event.preventDefault();
    },
  }));

  // A button that shows and hides the element named in its aria-controls
  Alpine.data("disclosure", () => ({
    open: false,
    toggle() {
      this.open = !this.open;
    },
    close() {
      this.open = false;
    },
  }));

  // The header: stronger glass once the page scrolls. The mobile menu is a dialog:
  // focus moves into it, stays in it while it is open, and returns to the button.
  Alpine.data("siteHeader", () => ({
    open: false,
    scrolled: false,
    init() {
      const update = () => {
        this.scrolled = window.scrollY > 24;
      };
      update();
      window.addEventListener("scroll", update, { passive: true });
    },
    get headerClass() {
      return this.scrolled || this.open ? "is-solid" : "";
    },
    openMenu() {
      this.open = true;
      this.$nextTick(() => this.$refs.closeButton.focus());
    },
    closeMenu() {
      if (!this.open) return;
      this.open = false;
      this.$nextTick(() => this.$refs.burger.focus());
    },
    // Tab from the last control wraps to the first, Shift+Tab from the first to the last,
    // so focus never reaches the page hidden under the menu
    trapFocus(event) {
      const items = [...this.$refs.menuPanel.querySelectorAll("a[href], button:not([disabled])")];
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    },
  }));

  // Days, hours, minutes and seconds until data-until (an ISO date), in Persian
  // digits, as in the demo. role="timer" keeps screen readers from announcing each tick.
  Alpine.data("countdown", () => ({
    days: "—",
    hours: "—",
    minutes: "—",
    seconds: "—",
    init() {
      const until = Date.parse(this.$el.dataset.until);
      const digits = new Intl.NumberFormat("fa-IR", { useGrouping: false });
      const tick = () => {
        const left = Math.max(0, Math.floor((until - Date.now()) / 1000));
        this.days = digits.format(Math.floor(left / 86400));
        this.hours = digits.format(Math.floor(left / 3600) % 24);
        this.minutes = digits.format(Math.floor(left / 60) % 60);
        this.seconds = digits.format(left % 60);
      };
      tick();
      this.timer = setInterval(tick, 1000);
    },
    destroy() {
      clearInterval(this.timer);
    },
  }));

  // Light or dark. The choice is kept in a cookie so the server can put it on
  // <html> before the page paints; without one the device setting decides.
  Alpine.data("themeSwitch", () => ({
    dark: false,
    init() {
      const chosen = document.documentElement.dataset.theme;
      this.dark = chosen ? chosen === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    },
    toggle() {
      this.dark = !this.dark;
      const theme = this.dark ? "dark" : "light";
      document.documentElement.dataset.theme = theme;
      document.cookie = `theme=${theme}; path=/; max-age=31536000; samesite=lax`;
    },
  }));
});

// Conversions (spec section 14) for whichever analytics tool is chosen later: an
// element with data-conversion="purchase" pushes one event to window.dataLayer,
// the queue that Google Tag Manager, Matomo and others read. Amounts are Rials.
function reportConversions(root) {
  root.querySelectorAll("[data-conversion]:not([data-conversion-sent])").forEach((el) => {
    el.dataset.conversionSent = "1";
    const event = { event: el.dataset.conversion };
    if (el.dataset.conversionForm) event.form = el.dataset.conversionForm;
    if (el.dataset.conversionId) event.transaction_id = el.dataset.conversionId;
    if (el.dataset.conversionValue) {
      event.value = Number(el.dataset.conversionValue);
      event.currency = "IRR";
    }
    (window.dataLayer = window.dataLayer || []).push(event);
  });
}
document.addEventListener("DOMContentLoaded", () => reportConversions(document));
// Lead forms are replaced in place by htmx (an outerHTML swap), without a page load.
// htmx:load fires on the new content; events on the replaced element never reach document
document.addEventListener("htmx:load", () => reportConversions(document));
