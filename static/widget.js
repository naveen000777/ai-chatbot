/**
 * Northwind Cycles chat widget.
 *
 * Install on any page with one line:
 *   <script src="http://127.0.0.1:5000/widget.js" data-api="http://127.0.0.1:5000"></script>
 *
 * Everything renders inside a shadow root, so the host site's CSS cannot
 * leak in and break the widget, and the widget cannot restyle the host.
 */
(function () {
  "use strict";

  var script = document.currentScript;
  var API = (script && script.dataset.api) || window.location.origin;
  var TITLE = (script && script.dataset.title) || "Northwind support";
  var GREETING = (script && script.dataset.greeting) ||
    "Hi. Ask about an order, delivery, returns, sizing or booking a service.";

  var sessionId = null;
  var busy = false;
  var turns = 0;
  var feedbackAsked = false;

  var host = document.createElement("div");
  host.id = "nw-chat-widget";
  var root = host.attachShadow({ mode: "open" });

  root.innerHTML = [
    '<style>',
    ':host { all: initial; }',
    '* { box-sizing: border-box; margin: 0; padding: 0; }',
    '.wrap {',
    '  position: fixed; right: 20px; bottom: 20px; z-index: 2147483000;',
    '  font-family: Karla, "Segoe UI", system-ui, sans-serif;',
    '  --slate: #1d2a38; --chalk: #f2f4f1; --signal: #f2c230;',
    '  --teal: #2e7d72; --line: #cbd2cd; --muted: #5d6b63;',
    '}',
    '.launcher {',
    '  display: flex; align-items: center; gap: 9px;',
    '  background: var(--slate); color: var(--chalk);',
    '  border: 0; border-radius: 26px; padding: 13px 20px 13px 17px;',
    '  font: 600 15px/1 Karla, system-ui, sans-serif; cursor: pointer;',
    '  box-shadow: 0 6px 20px rgba(29,42,56,.28);',
    '  transition: transform .16s ease;',
    '}',
    '.launcher:hover { transform: translateY(-2px); }',
    '.launcher:focus-visible { outline: 3px solid var(--signal); outline-offset: 3px; }',
    '.spoke { width: 15px; height: 15px; border: 2.5px solid var(--signal);',
    '  border-radius: 50%; border-top-color: transparent; }',
    '.panel {',
    '  display: none; flex-direction: column;',
    '  position: fixed; inset: 0; width: 100vw; height: 100vh;',
    '  background: var(--chalk); border-radius: 0; overflow: hidden;',
    '}',
    '.panel.open { display: flex; }',
    '.wrap.open .launcher { display: none; }',
    'header {',
    '  background: var(--slate); color: var(--chalk);',
    '  padding: 16px 20px; display: flex; align-items: center;',
    '  justify-content: space-between; border-bottom: 3px solid var(--signal);',
    '  flex-shrink: 0;',
    '}',
    'header h2 { font: 600 16px/1.3 Karla, system-ui, sans-serif; }',
    'header p { font-size: 12px; color: #9fb0ad; margin-top: 2px; }',
    '.close { background: none; border: 0; color: var(--chalk);',
    '  font-size: 26px; line-height: 1; cursor: pointer; padding: 2px 8px; }',
    '.close:focus-visible { outline: 2px solid var(--signal); }',
    '.log { flex: 1; overflow-y: auto; padding: 20px 16px; display: flex;',
    '  flex-direction: column; gap: 10px;',
    '  padding-left: max(16px, calc((100% - 760px) / 2));',
    '  padding-right: max(16px, calc((100% - 760px) / 2)); }',
    '.msg { max-width: 82%; padding: 10px 13px; font-size: 14px;',
    '  line-height: 1.5; border-radius: 12px; white-space: pre-wrap;',
    '  overflow-wrap: anywhere; }',
    '.bot { background: #fff; color: #23312c; border: 1px solid var(--line);',
    '  border-bottom-left-radius: 3px; align-self: flex-start; }',
    '.user { background: var(--teal); color: #fff;',
    '  border-bottom-right-radius: 3px; align-self: flex-end; }',
    '.chips { display: flex; flex-wrap: wrap; gap: 6px; }',
    '.chip { background: #fff; border: 1px solid var(--teal); color: var(--teal);',
    '  border-radius: 14px; padding: 6px 12px; font: 500 13px Karla, sans-serif;',
    '  cursor: pointer; }',
    '.chip:hover { background: var(--teal); color: #fff; }',
    '.chip:focus-visible { outline: 2px solid var(--slate); outline-offset: 2px; }',
    '.typing { display: flex; gap: 4px; align-self: flex-start;',
    '  padding: 12px 14px; background: #fff; border: 1px solid var(--line);',
    '  border-radius: 12px; }',
    '.typing i { width: 6px; height: 6px; background: var(--muted);',
    '  border-radius: 50%; animation: bob 1s infinite; }',
    '.typing i:nth-child(2) { animation-delay: .15s; }',
    '.typing i:nth-child(3) { animation-delay: .3s; }',
    '@keyframes bob { 0%,60%,100% { opacity: .3 } 30% { opacity: 1 } }',
    '.rate { display: flex; gap: 8px; align-items: center; font-size: 13px;',
    '  color: var(--muted); align-self: flex-start; }',
    '.rate button { border: 1px solid var(--line); background: #fff;',
    '  border-radius: 8px; padding: 4px 10px; cursor: pointer; font-size: 13px; }',
    'form { display: flex; gap: 8px; padding: 14px 16px;',
    '  padding-bottom: max(14px, env(safe-area-inset-bottom, 14px));',
    '  padding-left: max(16px, calc((100% - 760px) / 2));',
    '  padding-right: max(16px, calc((100% - 760px) / 2));',
    '  background: #fff; border-top: 1px solid var(--line); flex-shrink: 0; }',
    'input { flex: 1; border: 1px solid var(--line); border-radius: 9px;',
    '  padding: 11px 12px; font: 14px Karla, system-ui, sans-serif; color: #23312c; }',
    'input:focus { outline: 2px solid var(--teal); outline-offset: -1px; }',
    'button.send { background: var(--slate); color: var(--chalk); border: 0;',
    '  border-radius: 9px; padding: 0 17px; font: 600 14px Karla, sans-serif;',
    '  cursor: pointer; }',
    'button.send:disabled { opacity: .45; cursor: not-allowed; }',
    '@media (prefers-reduced-motion: reduce) {',
    '  .launcher, .typing i { transition: none; animation: none; }',
    '}',
    '</style>',
    '<div class="wrap" part="wrap">',
    '  <button class="launcher" aria-haspopup="dialog">',
    '    <span class="spoke"></span><span>Ask us</span>',
    '  </button>',
    '  <section class="panel" role="dialog" aria-label="Support chat">',
    '    <header>',
    '      <div><h2>' + TITLE + '</h2><p>Replies in a second, staff 9am-6pm</p></div>',
    '      <button class="close" aria-label="Close chat">&times;</button>',
    '    </header>',
    '    <div class="log" role="log" aria-live="polite"></div>',
    '    <form>',
    '      <input type="text" placeholder="Type your question" ',
    '             aria-label="Your message" autocomplete="off" maxlength="500">',
    '      <button type="submit" class="send">Send</button>',
    '    </form>',
    '  </section>',
    '</div>'
  ].join("\n");

  var wrap = root.querySelector(".wrap");
  var panel = root.querySelector(".panel");
  var log = root.querySelector(".log");
  var form = root.querySelector("form");
  var input = root.querySelector("input");
  var send = root.querySelector(".send");

  function scroll() { log.scrollTop = log.scrollHeight; }

  function bubble(text, who) {
    var el = document.createElement("div");
    el.className = "msg " + who;
    el.textContent = text;
    log.appendChild(el);
    scroll();
    return el;
  }

  function chips(options) {
    if (!options || !options.length) return;
    var row = document.createElement("div");
    row.className = "chips";
    options.forEach(function (label) {
      var b = document.createElement("button");
      b.className = "chip";
      b.type = "button";
      b.textContent = label;
      b.addEventListener("click", function () {
        row.remove();
        ask(label);
      });
      row.appendChild(b);
    });
    log.appendChild(row);
    scroll();
  }

  function typing(on) {
    var existing = root.querySelector(".typing");
    if (existing) existing.remove();
    if (!on) return;
    var el = document.createElement("div");
    el.className = "typing";
    el.innerHTML = "<i></i><i></i><i></i>";
    log.appendChild(el);
    scroll();
  }

  function rateBar() {
    if (feedbackAsked) return;
    feedbackAsked = true;
    var row = document.createElement("div");
    row.className = "rate";
    row.innerHTML = "<span>Was this helpful?</span>";
    [["Yes", true], ["No", false]].forEach(function (pair) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = pair[0];
      b.addEventListener("click", function () {
        fetch(API + "/api/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, helpful: pair[1] })
        }).catch(function () {});
        row.textContent = pair[1] ? "Thanks for the vote." : "Noted, I'll pass it on.";
      });
      row.appendChild(b);
    });
    log.appendChild(row);
    scroll();
  }

  function ask(text) {
    if (busy || !text.trim()) return;
    busy = true;
    send.disabled = true;
    bubble(text, "user");
    typing(true);

    fetch(API + "/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: sessionId })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        sessionId = data.session_id;
        // Small delay so replies do not snap in faster than the eye tracks.
        setTimeout(function () {
          typing(false);
          bubble(data.reply, "bot");
          chips(data.quick_replies);
          turns += 1;
          if (turns >= 3) rateBar();
          busy = false;
          send.disabled = false;
          input.focus();
        }, 320);
      })
      .catch(function () {
        typing(false);
        bubble("I can't reach the server. Check your connection and try again, or email help@northwindcycles.example.", "bot");
        busy = false;
        send.disabled = false;
      });
  }

  root.querySelector(".launcher").addEventListener("click", function () {
    wrap.classList.add("open");
    panel.classList.add("open");
    if (!log.children.length) {
      bubble(GREETING, "bot");
      chips(["Track my order", "Return policy", "Book a service"]);
    }
    input.focus();
  });

  root.querySelector(".close").addEventListener("click", function () {
    wrap.classList.remove("open");
    panel.classList.remove("open");
    root.querySelector(".launcher").focus();
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value;
    input.value = "";
    ask(text);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && panel.classList.contains("open")) {
      root.querySelector(".close").click();
    }
  });

  document.body.appendChild(host);
})();
