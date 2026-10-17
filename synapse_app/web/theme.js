(() => {
  "use strict";
  const key = "synapse.theme";
  const valid = (value) => value === "dark" || value === "light";
  let theme = "dark";
  let warning = "";
  try {
    const stored = window.localStorage.getItem(key);
    if (valid(stored)) theme = stored;
    else if (stored !== null) {
      warning = "Saved theme was invalid. Choose Dark or Light to reset it.";
      console.warn(warning);
    }
  } catch (error) {
    warning = "Theme changes cannot be saved in this browser.";
    console.warn("Theme preference could not be read:", error);
  }

  function apply(value) {
    theme = value;
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]').setAttribute("content",
      theme === "light" ? "#f5f7fb" : "#0b0e14");
  }
  apply(theme);

  document.addEventListener("DOMContentLoaded", () => {
    const select = document.getElementById("theme-selector");
    const status = document.getElementById("theme-status");
    const render = () => {
      select.value = theme;
      status.textContent = warning;
      status.hidden = !warning;
    };
    render();
    select.addEventListener("change", () => {
      if (!valid(select.value)) {
        warning = "Choose Dark or Light.";
        console.warn(warning);
        render();
        return;
      }
      apply(select.value);
      try {
        window.localStorage.setItem(key, theme);
        warning = "";
      } catch (error) {
        warning = "Theme changed, but cannot be saved in this browser.";
        console.warn("Theme preference could not be saved:", error);
      }
      render();
    });
    window.addEventListener("storage", (event) => {
      if (event.key !== key && event.key !== null) return;
      if (event.newValue === null || valid(event.newValue)) {
        apply(event.newValue || "dark");
        warning = "";
      }
      else {
        warning = "A saved theme change was invalid. Choose Dark or Light.";
        console.warn(warning);
      }
      render();
    });
  });
})();
