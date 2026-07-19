(function () {
  "use strict";

  var MEASUREMENT_ID = "G-BE2TVMMPX7";
  var CONSENT_KEY = "lrdf_analytics_consent";

  function readConsent() {
    try {
      return window.localStorage.getItem(CONSENT_KEY);
    } catch (error) {
      return null;
    }
  }

  function saveConsent(value) {
    try {
      window.localStorage.setItem(CONSENT_KEY, value);
    } catch (error) {
      // If storage is unavailable, the choice applies to the current page only.
    }
  }

  function loadAnalytics() {
    if (window.__lrdfAnalyticsLoaded) return;
    window.__lrdfAnalyticsLoaded = true;

    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function () {
      window.dataLayer.push(arguments);
    };

    window.gtag("js", new Date());
    window.gtag("config", MEASUREMENT_ID, { send_page_view: true });

    var script = document.createElement("script");
    script.async = true;
    script.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(MEASUREMENT_ID);
    document.head.appendChild(script);
  }

  function injectStyles() {
    if (document.getElementById("lrdf-cookie-styles")) return;

    var style = document.createElement("style");
    style.id = "lrdf-cookie-styles";
    style.textContent =
      ".lrdf-cookie-banner{position:fixed;z-index:2147483646;left:18px;right:18px;bottom:18px;max-width:760px;margin:0 auto;padding:20px 22px;background:#fffdf8;color:#45413a;border:1px solid #d9d1c4;border-radius:4px;box-shadow:0 10px 35px rgba(0,0,0,.22);font:14px/1.55 Arial,sans-serif;text-align:left}" +
      ".lrdf-cookie-banner p{margin:0 0 14px}.lrdf-cookie-banner a{color:#6f5c45;text-decoration:underline}" +
      ".lrdf-cookie-actions{display:flex;flex-wrap:wrap;gap:10px}.lrdf-cookie-actions button,.lrdf-cookie-settings{border:1px solid #6f5c45;border-radius:3px;padding:9px 15px;font:600 13px Arial,sans-serif;cursor:pointer}" +
      ".lrdf-cookie-accept{background:#6f5c45;color:#fff}.lrdf-cookie-reject{background:#fff;color:#554735}" +
      ".lrdf-cookie-settings{position:fixed;z-index:2147483645;left:12px;bottom:12px;background:#fffdf8;color:#554735;padding:7px 10px;font-size:12px;box-shadow:0 3px 12px rgba(0,0,0,.16)}" +
      "@media(max-width:560px){.lrdf-cookie-banner{left:10px;right:10px;bottom:10px;padding:17px}.lrdf-cookie-actions button{flex:1 1 130px}}";
    document.head.appendChild(style);
  }

  function removeBanner() {
    var banner = document.getElementById("lrdf-cookie-banner");
    if (banner) banner.remove();
  }

  function showSettingsButton(copy) {
    if (document.getElementById("lrdf-cookie-settings")) return;

    var button = document.createElement("button");
    button.id = "lrdf-cookie-settings";
    button.className = "lrdf-cookie-settings";
    button.type = "button";
    button.textContent = copy.settings;
    button.addEventListener("click", function () {
      button.remove();
      showBanner(copy);
    });
    document.body.appendChild(button);
  }

  function showBanner(copy) {
    if (document.getElementById("lrdf-cookie-banner")) return;
    injectStyles();

    var banner = document.createElement("section");
    banner.id = "lrdf-cookie-banner";
    banner.className = "lrdf-cookie-banner";
    banner.setAttribute("role", "dialog");
    banner.setAttribute("aria-label", copy.title);
    banner.setAttribute("data-nosnippet", "");

    var text = document.createElement("p");
    text.appendChild(document.createTextNode(copy.message + " "));
    var link = document.createElement("a");
    link.href = copy.privacyUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = copy.more;
    text.appendChild(link);

    var actions = document.createElement("div");
    actions.className = "lrdf-cookie-actions";

    var reject = document.createElement("button");
    reject.type = "button";
    reject.className = "lrdf-cookie-reject";
    reject.textContent = copy.reject;
    reject.addEventListener("click", function () {
      saveConsent("denied");
      removeBanner();
      showSettingsButton(copy);
    });

    var accept = document.createElement("button");
    accept.type = "button";
    accept.className = "lrdf-cookie-accept";
    accept.textContent = copy.accept;
    accept.addEventListener("click", function () {
      saveConsent("granted");
      removeBanner();
      showSettingsButton(copy);
      loadAnalytics();
    });

    actions.appendChild(reject);
    actions.appendChild(accept);
    banner.appendChild(text);
    banner.appendChild(actions);
    document.body.appendChild(banner);
  }

  function start() {
    var isEnglish = (document.documentElement.lang || "").toLowerCase().indexOf("en") === 0;
    var copy = isEnglish
      ? {
          title: "Analytics cookies",
          message: "We use Google Analytics to measure visits and improve this website. It will only be activated if you accept.",
          more: "Google privacy information",
          privacyUrl: "https://policies.google.com/privacy?hl=en",
          reject: "Reject",
          accept: "Accept analytics",
          settings: "Cookie settings"
        }
      : {
          title: "Cookies de analítica",
          message: "Usamos Google Analytics para medir las visitas y mejorar esta web. Solo se activará si aceptas.",
          more: "Información de privacidad de Google",
          privacyUrl: "https://policies.google.com/privacy?hl=es",
          reject: "Rechazar",
          accept: "Aceptar analítica",
          settings: "Configurar cookies"
        };

    injectStyles();
    var consent = readConsent();
    if (consent === "granted") {
      loadAnalytics();
      showSettingsButton(copy);
    } else if (consent === "denied") {
      showSettingsButton(copy);
    } else {
      showBanner(copy);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
