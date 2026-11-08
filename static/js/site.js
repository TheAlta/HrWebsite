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
