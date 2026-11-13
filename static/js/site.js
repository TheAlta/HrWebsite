// Alpine components the page markup refers to by name. Under the site's CSP the
// Alpine build cannot run free JavaScript or reach globals such as confirm(), so
// anything beyond a simple expression lives here. Loaded before Alpine.

// Keeps Tab inside an open dialog: from the last control it wraps to the first,
// and Shift+Tab from the first to the last, so focus never reaches the page under it
function trapFocus(container, event) {
  const items = [...container.querySelectorAll("a[href], button:not([disabled])")].filter(
    (el) => el.offsetParent !== null,
  );
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
}

const faDigits = new Intl.NumberFormat("fa-IR", { useGrouping: false });

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
    trapFocus(event) {
      trapFocus(this.$refs.menuPanel, event);
    },
  }));

  // The home page quiz (blocks/quiz.html): one question at a time in a dialog; the
  // answers are worth 0, 1 and 2, and the total opens the first result whose
  // data-up-to is not below it. Its button fills the consultation form's topic and note.
  Alpine.data("quiz", () => ({
    open: false,
    step: 0,
    scores: [],
    start() {
      this.open = true;
      this.restart();
    },
    restart() {
      this.step = 0;
      this.scores = [];
      this.show();
    },
    close() {
      if (!this.open) return;
      this.open = false;
      this.$nextTick(() => this.$refs.opener.focus());
    },
    choose(event) {
      this.scores[this.step] = Number(event.currentTarget.dataset.score);
      this.step += 1;
      this.show();
    },
    back() {
      this.step = Math.max(0, this.step - 1);
      this.show();
    },
    trapFocus(event) {
      trapFocus(this.$refs.dialog, event);
    },
    show() {
      const dialog = this.$refs.dialog;
      const questions = [...dialog.querySelectorAll("[data-question]")];
      const total = questions.length;
      const done = this.step >= total;
      questions.forEach((question, index) => {
        question.hidden = index !== this.step;
      });
      dialog.querySelector("[data-quiz-back]").hidden = done || this.step === 0;
      dialog.querySelector("[data-quiz-counter]").textContent = done
        ? "نتیجهٔ شما"
        : `سؤال ${faDigits.format(this.step + 1)} از ${faDigits.format(total)}`;
      dialog.querySelector("[data-quiz-progress]").style.width = `${(Math.min(this.step, total) / total) * 100}%`;

      const results = [...dialog.querySelectorAll("[data-result]")];
      results.forEach((result) => {
        result.hidden = true;
      });
      if (!done) {
        this.$nextTick(() => questions[this.step].querySelector("button").focus());
        return;
      }
      const score = this.scores.reduce((sum, value) => sum + value, 0);
      const max = total * 2;
      const result =
        results.find((item) => score <= Number(item.dataset.upTo)) || results[results.length - 1];
      result.hidden = false;
      result.querySelector("[data-result-bar]").style.width = `${(score / max) * 100}%`;
      result.querySelector("[data-result-score]").textContent =
        `امتیاز ${faDigits.format(score)} از ${faDigits.format(max)}`;
      const link = result.querySelector("[data-result-link]");
      if (link) {
        const url = new URL(link.getAttribute("href"), window.location.origin);
        if (result.dataset.topic) url.searchParams.set("topic", result.dataset.topic);
        url.searchParams.set(
          "note",
          `نتیجهٔ آزمون: ${result.dataset.name} (امتیاز ${faDigits.format(score)} از ${faDigits.format(max)})`,
        );
        link.href = url.pathname + url.search;
      }
      this.$nextTick(() => result.querySelector("[data-result-heading]").focus());
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

  // Free resources (blocks/free_resources.html): a topic button shows only its files;
  // pressing it again shows them all
  Alpine.data("resourceFilter", () => ({
    pick(event) {
      const button = event.currentTarget;
      const on = button.getAttribute("aria-pressed") !== "true";
      this.$root.querySelectorAll("[data-topic]").forEach((el) => el.setAttribute("aria-pressed", "false"));
      button.setAttribute("aria-pressed", String(on));
      this.$root.querySelectorAll("[data-resource]").forEach((card) => {
        card.hidden = on && card.dataset.resource !== button.dataset.topic;
      });
    },
  }));

  // The free-event bar above the header: closing it is remembered for this visit,
  // in a cookie the server reads, so later pages arrive without it (no jump on load)
  Alpine.data("eventBar", () => ({
    open: true,
    close() {
      this.open = false;
      document.cookie = `event_bar_closed=${this.$root.dataset.event}; path=/; samesite=lax`;
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
