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
