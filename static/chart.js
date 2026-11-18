/* 해운물류 데일리 — 리뉴얼 인터랙션
   시작 페이지 항해 연출 · 해도 핀 ↔ 기사 카드 연동 · 읽기 진행 바 · 용어 해설 팝업
   읽음 상태는 app.js 의 window.SB 를 쓴다. */
(function () {
  "use strict";
  var html = document.documentElement;
  var REDUCE = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (REDUCE) html.classList.add("reduce-motion");
  var $ = function (s, el) { return (el || document).querySelector(s); };
  var $$ = function (s, el) { return Array.prototype.slice.call((el || document).querySelectorAll(s)); };

  // ── 시작 페이지: 스크롤하면 배가 항해한다 ─────────────────────────
  var ship = $("[data-sail]"), harbor = $(".harbor");
  if (ship && harbor && !REDUCE) {
    var ticking = false;
    var sail = function () {
      ticking = false;
      var h = harbor.offsetHeight || 1;
      var p = Math.max(0, Math.min(1, window.scrollY / h));
      ship.style.setProperty("--sail", p.toFixed(3));
    };
    window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(sail); } }, { passive: true });
    sail();
  }

  // ── 메인: 해도 핀 ↔ 기사 카드 ─────────────────────────────────
  var pins = $$(".daychart .pin[data-region]");
  if (pins.length) {
    var cards = $$("[data-regions]");
    var hot = function (regions, on) {
      pins.forEach(function (p) { if (regions.indexOf(p.dataset.region) >= 0) p.classList.toggle("is-hot", on); });
    };
    cards.forEach(function (c) {
      var rs = (c.dataset.regions || "").split(" ").filter(Boolean);
      if (!rs.length) return;
      c.addEventListener("mouseenter", function () { hot(rs, true); });
      c.addEventListener("mouseleave", function () { hot(rs, false); });
      c.addEventListener("focusin", function () { hot(rs, true); });
      c.addEventListener("focusout", function () { hot(rs, false); });
    });
    pins.forEach(function (p) {
      var on = function (v) {
        cards.forEach(function (c) {
          if ((" " + c.dataset.regions + " ").indexOf(" " + p.dataset.region + " ") >= 0) c.classList.toggle("is-hot", v);
        });
      };
      p.addEventListener("mouseenter", function () { on(true); });
      p.addEventListener("mouseleave", function () { on(false); });
      p.addEventListener("focus", function () { on(true); });
      p.addEventListener("blur", function () { on(false); });
    });
  }

  // ── 기사: 읽기 진행 바 (끝까지 읽으면 자동 읽음) ─────────────────
  var bar = $(".read-progress i"), body = $(".ed-body"), art = $("article.ed[data-article]");
  if (bar && body) {
    var marked = false, t2 = false, scrolled = false;
    var prog = function () {
      t2 = false;
      var r = body.getBoundingClientRect();
      var total = r.height - window.innerHeight * 0.6;
      var p = total > 0 ? Math.max(0, Math.min(1, -r.top / total)) : 1;
      bar.style.setProperty("--p", p.toFixed(3));
      if (scrolled && p >= 0.98 && !marked && art && window.SB && !window.SB.isRead(art.dataset.article)) {
        marked = true; window.SB.setRead(art.dataset.article, true);
      }
    };
    window.addEventListener("scroll", function () { scrolled = true; if (!t2) { t2 = true; requestAnimationFrame(prog); } }, { passive: true });
    window.addEventListener("resize", prog);
    prog();
  }

  // ── 기사: 용어 해설 팝업 ───────────────────────────────────────
  var pop = $("#term-pop");
  if (pop) {
    var cur = null;
    var title = $("b", pop), text = $("p", pop), img = $("img", pop);
    var close = function (focusBack) {
      if (!cur) return;
      cur.setAttribute("aria-expanded", "false");
      pop.hidden = true;
      if (focusBack) cur.focus();
      cur = null;
    };
    var open = function (btn) {
      var def = document.getElementById("term-" + btn.dataset.term);
      if (!def) return;
      if (cur === btn) { close(false); return; }
      close(false);
      cur = btn;
      title.textContent = $("dt", def).textContent;
      text.textContent = $("dd", def).textContent;
      var dimg = $(".ed-diagram img", def);
      if (dimg) { img.src = dimg.currentSrc || dimg.src; img.alt = dimg.alt; img.hidden = false; }
      else { img.hidden = true; img.removeAttribute("src"); }
      pop.hidden = false;
      var r = btn.getBoundingClientRect(), w = pop.offsetWidth;
      var left = Math.max(16, Math.min(r.left + window.scrollX, window.scrollX + document.documentElement.clientWidth - w - 16));
      pop.style.left = left + "px";
      pop.style.top = (r.bottom + window.scrollY + 8) + "px";
      btn.setAttribute("aria-expanded", "true");
    };
    document.addEventListener("click", function (e) {
      var t = e.target.closest(".term");
      if (t) { e.preventDefault(); open(t); return; }
      if (e.target.closest(".term-pop-x")) { close(true); return; }
      if (cur && !e.target.closest("#term-pop")) close(false);
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(true); });
    window.addEventListener("resize", function () { close(false); });
  }
})();
