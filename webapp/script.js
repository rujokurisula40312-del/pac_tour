(function () {
    "use strict";

    var tg = window.Telegram && window.Telegram.WebApp;
    if (tg) {
        tg.ready();
        tg.expand();
        try { tg.enableClosingConfirmation(); } catch (e) {}
    }

    var managerBar = document.getElementById("manager-bar");
    var managerBtn = document.getElementById("manager-btn");
    var shown = false;

    function buildPayload() {
        var payload = { action: "contact_manager" };
        try {
            var selected = document.querySelector(
                "#ces-app .selected, #ces-app .is-selected, #ces-app [aria-selected=\"true\"]"
            );
            if (selected) {
                payload.details = {
                    text: (selected.innerText || "").trim().slice(0, 500)
                };
            }
        } catch (e) { /* widget DOM may differ — игнорируем */ }
        return payload;
    }

    function contactManager() {
        var payload = buildPayload();
        if (tg && typeof tg.sendData === "function") {
            tg.sendData(JSON.stringify(payload));
            tg.close();
        } else {
            // fallback вне Telegram
            window.location.href = "https://t.me/your_manager";
        }
    }

    function showManagerUI() {
        if (shown) return;
        shown = true;
        if (managerBar) managerBar.hidden = false;
        if (tg && tg.MainButton) {
            tg.MainButton.setText("✉️ Написать менеджеру");
            tg.MainButton.onClick(contactManager);
            tg.MainButton.show();
        }
    }

    if (managerBtn) managerBtn.addEventListener("click", contactManager);

    // Показываем кнопку после первого взаимодействия с виджетом
    // (клик/тач/изменение поля — индикатор «пользователь что-то выбрал»).
    var widgetHost = document.getElementById("ces-app") || document.body;
    var onInteract = function () { showManagerUI(); };
    widgetHost.addEventListener("click", onInteract, { passive: true });
    widgetHost.addEventListener("change", onInteract, { passive: true });
    widgetHost.addEventListener("touchend", onInteract, { passive: true });

    // Подстраховка: если пользователь просто долистал до результатов —
    // тоже показываем кнопку.
    window.addEventListener("scroll", function () {
        if (window.scrollY > 200) showManagerUI();
    }, { passive: true });

    // Если виджет не успел проинициализироваться за 8с — показываем всё равно.
    setTimeout(showManagerUI, 8000);
})();
