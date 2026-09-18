(function () {
  "use strict";

  document.documentElement.classList.remove("no-js");

  // ---------- Theme switch (System / Light / Dark) ----------
  var THEME_KEY = "emfm-theme";
  var switches = document.querySelectorAll(".theme-switch");

  function currentChoice() {
    var saved = localStorage.getItem(THEME_KEY);
    return saved === "light" || saved === "dark" ? saved : "system";
  }

  function syncButtons() {
    var choice = currentChoice();
    switches.forEach(function (group) {
      group.querySelectorAll("button").forEach(function (btn) {
        btn.setAttribute("aria-pressed", btn.dataset.themeChoice === choice ? "true" : "false");
      });
    });
  }

  function applyTheme(choice) {
    if (choice === "light" || choice === "dark") {
      document.documentElement.setAttribute("data-theme", choice);
      localStorage.setItem(THEME_KEY, choice);
    } else {
      document.documentElement.removeAttribute("data-theme");
      localStorage.removeItem(THEME_KEY);
    }
    syncButtons();
  }

  switches.forEach(function (group) {
    group.addEventListener("click", function (e) {
      var btn = e.target.closest("button[data-theme-choice]");
      if (!btn) return;
      applyTheme(btn.dataset.themeChoice);
    });
  });

  syncButtons();

  // ---------- Reveal-on-scroll ----------
  var revealEls = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && revealEls.length) {
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("in-view");
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    revealEls.forEach(function (el) { io.observe(el); });
  } else {
    revealEls.forEach(function (el) { el.classList.add("in-view"); });
  }

  // Mobile nav drawer
  var toggle = document.getElementById("navToggle");
  var drawer = document.getElementById("mobileDrawer");
  if (toggle && drawer) {
    toggle.addEventListener("click", function () {
      var open = drawer.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    drawer.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () {
        drawer.classList.remove("open");
        toggle.setAttribute("aria-expanded", "false");
      });
    });
  }

  // Copy quick-start command block
  var copyBtn = document.getElementById("copyCmd");
  var cmdBlock = document.getElementById("cmdBlock");
  if (copyBtn && cmdBlock) {
    copyBtn.addEventListener("click", function () {
      var text = cmdBlock.innerText;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
          var original = copyBtn.textContent;
          copyBtn.textContent = "Copied";
          setTimeout(function () { copyBtn.textContent = original; }, 1800);
        });
      }
    });
  }
})();
