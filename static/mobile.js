/* 해운물류 데일리 — 모바일(안드로이드 기준) 전용 동작
   (max-width: 640px) and (pointer: coarse) 일 때만 실행된다. 데스크톱에선 즉시 종료.
   상태는 app.js 의 window.SB(읽음·스크랩)와 localStorage 'sb:settings' 를 쓴다. */
(function () {
  "use strict";
  var MQ = "(max-width: 640px) and (pointer: coarse)";
  if (!window.matchMedia || !matchMedia(MQ).matches) return;

  var html = document.documentElement, root = html.dataset.root || "", page = html.dataset.page || "";
  var SB = window.SB || { load: function (k, d) { return d; }, save: function () {} };
  var REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;
  var STANDALONE = matchMedia("(display-mode: standalone)").matches;
  var $ = function (s, el) { return (el || document).querySelector(s); };
  var $$ = function (s, el) { return Array.prototype.slice.call((el || document).querySelectorAll(s)); };
  html.classList.add("is-mobile");

  // ── 설정 ─────────────────────────────────────────────────────
  var DEFAULTS = { font: "md", theme: "system", expand: "summary", haptic: "on" };
  var S = Object.assign({}, DEFAULTS, SB.load("sb:settings", {}));
  function applySettings() {
    html.style.fontSize = { sm: "93.75%", lg: "112.5%" }[S.font] || "";
    if (S.theme === "light" || S.theme === "dark") html.setAttribute("data-theme", S.theme);
    else html.removeAttribute("data-theme");
    html.classList.toggle("m-expand-all", S.expand === "full");
    // 상태 표시줄 색 = 앱 바 색
    var dark = S.theme === "dark" || (S.theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
    $$('meta[name="theme-color"]').forEach(function (m) {
      if (S.theme === "system") m.setAttribute("content", /dark/.test(m.media) ? "#182230" : "#ffffff");
      else m.setAttribute("content", dark ? "#182230" : "#ffffff");
    });
  }
  applySettings();
  function haptic() { if (S.haptic !== "off" && navigator.vibrate) { try { navigator.vibrate(8); } catch (e) {} } }

  // ── 스낵바 ───────────────────────────────────────────────────
  var snackEl = $(".m-snackbar"), snackTimer;
  function snackbar(msg, opt) {
    if (!snackEl) return;
    opt = opt || {};
    snackEl.innerHTML = "";
    var span = document.createElement("span"); span.textContent = msg; snackEl.appendChild(span);
    if (opt.action) {
      var b = document.createElement("button"); b.type = "button"; b.textContent = opt.action;
      b.style.cssText = "float:right;margin:-10px -6px -10px 8px;min-height:40px;padding:0 10px;border:0;background:none;color:var(--gold);font:inherit;font-weight:700;pointer-events:auto";
      b.onclick = function () { opt.onAction(); hide(); };
      snackEl.appendChild(b);
    }
    snackEl.classList.add("is-on"); document.body.classList.add("has-snack");
    clearTimeout(snackTimer); snackTimer = setTimeout(hide, opt.ms || (opt.action ? 5000 : 2800));
    function hide() { snackEl.classList.remove("is-on"); document.body.classList.remove("has-snack"); }
  }

  // ── 레이어(시트·선택 모드)와 안드로이드 뒤로 가기 ──────────────────
  // 열 때 history.pushState, 시스템 뒤로 가기(popstate)는 맨 위 레이어만 닫는다.
  // UI로 닫을 때는 history.back()을 불러 쌓은 기록을 정리한다(실제 닫기는 popstate에서).
  var layers = [];
  function pushLayer(name, onClose) {
    layers.push({ name: name, onClose: onClose });
    history.pushState({ sbLayer: name, depth: layers.length }, "");
  }
  function closeLayer(name) {
    var top = layers[layers.length - 1];
    if (top && top.name === name) history.back();
  }
  window.addEventListener("popstate", function () {
    var top = layers.pop();
    if (top) top.onClose();
  });

  // ── 바텀 시트 ─────────────────────────────────────────────────
  var sheetSeq = 0;
  var OUTSIDE = ".masthead, main, .foot, .m-nav, .m-fab, .m-cta";
  function openSheet(opt) {
    var id = "m-sheet-" + (++sheetSeq);
    var returnTo = opt.from || document.activeElement;
    var scrim = document.createElement("div"); scrim.className = "m-scrim";
    var el = document.createElement("section");
    el.className = "m-sheet"; el.id = id;
    el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true"); el.setAttribute("aria-labelledby", id + "-t");
    if (opt.snap === "half") el.dataset.snap = "half";
    el.innerHTML = '<button type="button" class="m-sheet-handle" aria-label="시트 크기 조절"></button>' +
      '<div class="m-sheet-head"><h2 id="' + id + '-t" tabindex="-1"></h2>' +
      '<button type="button" class="m-sheet-close" aria-label="닫기">✕</button></div><div class="m-sheet-body"></div>';
    $("h2", el).textContent = opt.title || "";
    var body = $(".m-sheet-body", el);
    if (opt.body) body.appendChild(opt.body);
    document.body.appendChild(scrim); document.body.appendChild(el);
    $$(OUTSIDE).forEach(function (n) { n.inert = true; });
    requestAnimationFrame(function () { scrim.classList.add("is-open"); el.classList.add("is-open"); });
    setTimeout(function () { $("h2", el).focus({ preventScroll: true }); }, REDUCE ? 0 : 60);

    var closed = false;
    function finalize() {
      if (closed) return; closed = true;
      el.classList.remove("is-open"); scrim.classList.remove("is-open");
      $$(OUTSIDE).forEach(function (n) { n.inert = false; });
      setTimeout(function () {
        if (opt.onClose) opt.onClose(body);
        el.remove(); scrim.remove();
        if (returnTo && returnTo.focus && document.contains(returnTo)) returnTo.focus({ preventScroll: true });
        if (opt.after) opt.after();
      }, REDUCE ? 0 : 260);
    }
    pushLayer(id, finalize);
    var api = { el: el, body: body, close: function () { closeLayer(id); } };
    scrim.addEventListener("click", api.close);
    $(".m-sheet-close", el).addEventListener("click", api.close);
    el.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { api.close(); return; }
      if (e.key !== "Tab") return;                       // 포커스 가두기
      var f = $$('a[href], button:not([disabled]), input, [tabindex]:not([tabindex="-1"])', el).filter(function (n) { return n.offsetParent; });
      if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    });
    // 드래그: 손잡이·제목 줄을 끌어 크기 조절/닫기 (반 → 전체 → 반 → 닫기)
    [$(".m-sheet-handle", el), $(".m-sheet-head", el)].forEach(function (h) {
      var y0 = null, dy = 0;
      h.addEventListener("pointerdown", function (e) {
        if (e.target.closest(".m-sheet-close")) return;
        y0 = e.clientY; dy = 0; el.classList.add("is-dragging"); h.setPointerCapture(e.pointerId);
      });
      h.addEventListener("pointermove", function (e) {
        if (y0 === null) return;
        dy = e.clientY - y0;
        el.style.transform = "translateY(" + Math.max(dy, -40) + "px)";
      });
      function end() {
        if (y0 === null) return;
        y0 = null; el.classList.remove("is-dragging"); el.style.transform = "";
        if (dy > 90) {
          if (el.dataset.snap === "full") el.dataset.snap = "half"; else api.close();
        } else if (dy < -50 && el.dataset.snap === "half") el.dataset.snap = "full";
      }
      h.addEventListener("pointerup", end); h.addEventListener("pointercancel", end);
      h.addEventListener("click", function () {   // 키보드·TalkBack: 손잡이 누르면 반↔전체
        if (h.classList.contains("m-sheet-handle") && el.dataset.snap) el.dataset.snap = el.dataset.snap === "half" ? "full" : "half";
      });
    });
    return api;
  }

  // ── 상단 앱 바: 아래로 스크롤하면 숨고 위로 하면 나타남 ──────────────
  var mast = $(".masthead"), mnav = $(".m-nav");
  // 글자 크기(안드로이드 설정·앱 설정)에 따라 바 높이가 달라지므로 실제 높이를 재서 고정 요소 위치에 쓴다
  var measure = function () {
    if (mast) html.style.setProperty("--m-bar-real", mast.offsetHeight + "px");
    if (mnav) html.style.setProperty("--m-nav-real", (mnav.offsetHeight - (parseFloat(getComputedStyle(mnav).paddingBottom) || 0) + 6) + "px");
  };
  measure(); window.addEventListener("resize", measure);
  if (window.ResizeObserver) { var ro = new ResizeObserver(measure); if (mast) ro.observe(mast); if (mnav) ro.observe(mnav); }
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(measure);
  if (mast && !REDUCE) {
    var lastY = window.scrollY, hidden = false, ticking = false;
    var setHidden = function (h) {
      if (h === hidden) return; hidden = h;
      mast.classList.toggle("m-hide", h);
      html.classList.toggle("m-scrolling-down", h);
      if (h) html.style.setProperty("--m-top", "0px"); else html.style.removeProperty("--m-top");
    };
    window.addEventListener("scroll", function () {
      if (ticking) return; ticking = true;
      requestAnimationFrame(function () {
        var y = window.scrollY, dy = y - lastY;
        if (y < 64 || layers.length) setHidden(false);
        else if (dy > 6) setHidden(true);
        else if (dy < -6) setHidden(false);
        lastY = y; ticking = false;
      });
    }, { passive: true });
  }

  // ── 하단 내비 배지 · 진행 막대 · 완료 스낵바 ────────────────────────
  var todayIds = (html.dataset.todayIds || "").split("|").filter(Boolean);
  var items = $$("[data-article]");
  var wasDone = null;
  function refresh() {
    var unread = todayIds.filter(function (id) { return !SB.isRead(id); }).length;
    var ub = $("#m-unread"); if (ub) { ub.hidden = !unread; ub.textContent = unread > 99 ? "99+" : unread; }
    var nStar = Object.keys(SB.stars ? SB.stars() : {}).length;
    var sb = $("#m-stars"); if (sb) { sb.hidden = !nStar; sb.textContent = nStar; }
    var ubLabel = $('.m-nav a[href$="today.html"]');
    if (ubLabel) ubLabel.setAttribute("aria-label", "오늘" + (unread ? ", 안 읽은 기사 " + unread + "건" : ""));
    if (page === "today" && items.length) {
      var done = items.filter(function (el) { return SB.isRead(el.dataset.article); }).length;
      var bar = $(".m-progress");
      if (bar) { bar.firstElementChild.style.width = (done / items.length * 100) + "%"; bar.classList.toggle("is-done", done === items.length); }
      var all = done === items.length;
      if (wasDone === false && all) {
        var key = "sb:doneSnack", shown = SB.load(key, {});
        if (!shown[location.pathname]) {
          shown[location.pathname] = Date.now(); SB.save(key, shown);
          snackbar("오늘 완료 · 연속 " + (SB.streak ? SB.streak() : 1) + "일");
        }
      }
      wasDone = all;
    }
    var cta = $(".m-cta");
    if (cta && todayIds.length) {
      var d2 = todayIds.length - unread;
      $("small", cta).textContent = d2 + "/" + todayIds.length;
      cta.classList.toggle("is-done", !unread);
      $("span", cta).textContent = unread ? "오늘 브리핑 읽기" : "오늘 완료";
    }
  }
  document.addEventListener("sb:render", refresh);
  refresh();

  // ── 기사 카드: 해설 펼치기 · 공유 · 햅틱 ──────────────────────────
  document.addEventListener("click", function (e) {
    var more = e.target.closest(".m-more-btn");
    if (more) {
      var card = more.closest("[data-article]");
      var open = !card.classList.contains("is-expanded");
      card.classList.toggle("is-expanded", open);
      more.setAttribute("aria-expanded", open); more.textContent = open ? "해설 접기" : "해설 보기";
      if (!open) { var r = card.getBoundingClientRect(); if (r.top < 0) card.scrollIntoView({ block: "start" }); }
      return;
    }
    var share = e.target.closest(".btn-share");
    if (share) { shareArticle(share.closest("[data-article]")); return; }
    var rd = e.target.closest(".btn-read");
    if (rd) setTimeout(function () { if (rd.getAttribute("aria-pressed") === "true") haptic(); }, 0);
  });
  function shareArticle(el) {
    if (!el) return;
    var d = el.dataset, text = (d.summary || "").split(/(?<=다\.)\s|(?<=\.)\s/)[0];
    if (navigator.share) {
      navigator.share({ title: d.title, text: text, url: d.url }).catch(function () {});
    } else copy(d.url, "링크를 복사했어요");
  }
  function copy(text, msg) {
    (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject())
      .then(function () { snackbar(msg); }, function () { snackbar("복사하지 못했어요"); });
  }

  // ── 카드 스와이프: 오른쪽 = 읽음, 왼쪽 = 스크랩 (버튼과 같은 동작) ─────────
  if (page !== "scrap") items.forEach(attachSwipe);
  function attachSwipe(el) {
    var x0, y0, dx = 0, state = 0, bg = null, w = 0, pid = null, swallow = false;   // state: 0 판정 전, 1 스와이프 중, -1 세로 스크롤
    // 링크(제목·칩) 위에서 시작한 스와이프도 받는다. 스와이프 직후의 클릭은 삼켜서 링크가 열리지 않게.
    el.addEventListener("click", function (e) { if (swallow) { e.preventDefault(); e.stopPropagation(); swallow = false; } }, true);
    el.addEventListener("pointerdown", function (e) {
      if (e.pointerType !== "touch" || e.target.closest("button, input")) return;
      if (e.clientX < 24 || e.clientX > innerWidth - 24) return;    // 안드로이드 뒤로 가기 제스처 영역
      x0 = e.clientX; y0 = e.clientY; dx = 0; state = 0; pid = e.pointerId; w = el.offsetWidth;
    });
    el.addEventListener("pointermove", function (e) {
      if (e.pointerId !== pid || state === -1) return;
      var mx = e.clientX - x0, my = e.clientY - y0;
      if (state === 0) {
        if (Math.abs(mx) < 10 && Math.abs(my) < 10) return;
        if (Math.abs(mx) > Math.abs(my) * 1.5) { state = 1; el.setPointerCapture(pid); start(); }
        else { state = -1; return; }
      }
      dx = mx;
      el.style.transform = "translateX(" + dx + "px)";
      bg.className = "m-swipe-bg " + (dx > 0 ? "read" : "star") + (Math.abs(dx) > w * 0.3 ? " armed" : "");
      bg.textContent = dx > 0 ? (SB.isRead(el.dataset.article) ? "↺ 안 읽음" : "✓ 읽음") : (SB.isStarred(el.dataset.article) ? "스크랩 해제" : "★ 스크랩");
    });
    function start() {
      var r = el.getBoundingClientRect();
      bg = document.createElement("div");
      bg.style.cssText = "left:" + (r.left + scrollX) + "px;top:" + (r.top + scrollY) + "px;width:" + r.width + "px;height:" + r.height + "px";
      document.body.appendChild(bg);
      el.classList.add("m-swiping");
    }
    function finish() {
      if (state !== 1) { state = 0; pid = null; return; }
      var act = Math.abs(dx) > w * 0.3 ? (dx > 0 ? "read" : "star") : null;
      swallow = true; setTimeout(function () { swallow = false; }, 400);
      el.classList.add("m-swipe-back"); el.style.transform = "";
      setTimeout(function () { el.classList.remove("m-swipe-back", "m-swiping"); if (bg) { bg.remove(); bg = null; } }, REDUCE ? 0 : 230);
      if (act === "read") { SB.toggleRead(el); if (SB.isRead(el.dataset.article)) haptic(); }
      if (act === "star") { SB.toggleStar(el); haptic(); snackbar(SB.isStarred(el.dataset.article) ? "스크랩했어요" : "스크랩을 해제했어요"); }
      state = 0; pid = null;
    }
    el.addEventListener("pointerup", finish);
    el.addEventListener("pointercancel", function () { if (state === 1) { dx = 0; finish(); } state = 0; pid = null; });
  }

  // ── 오늘: 개요 3줄 접기 · 필터 FAB + 시트 ──────────────────────────
  var ov = $(".brief-head .overview");
  if (ov && ov.scrollHeight > ov.clientHeight + 2) {
    var ob = document.createElement("button"); ob.type = "button"; ob.className = "m-clamp-btn"; ob.textContent = "더 보기";
    ob.setAttribute("aria-expanded", "false");
    ob.onclick = function () { var o = ov.classList.toggle("is-open"); ob.textContent = o ? "접기" : "더 보기"; ob.setAttribute("aria-expanded", o); };
    ov.after(ob);
  }
  var toolbar = $(".toolbar");
  if (page === "today" && toolbar) {
    var fab = document.createElement("button");
    fab.type = "button"; fab.className = "m-fab"; fab.setAttribute("aria-haspopup", "dialog");
    fab.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4"/></svg><b class="m-badge" hidden></b>';
    document.body.appendChild(fab);
    var fabBadge = $(".m-badge", fab);
    var filterCount = function () {
      var f = SB.load("sb:filter", {}); var n = (f.source && f.source !== "all" ? 1 : 0) + (f.hideRead ? 1 : 0) + (f.showLow ? 1 : 0);
      fabBadge.hidden = !n; fabBadge.textContent = n;
      fab.setAttribute("aria-label", "필터" + (n ? ", " + n + "개 적용됨" : ""));
    };
    filterCount(); document.addEventListener("sb:render", filterCount);
    fab.addEventListener("click", function () {
      var wrap = document.createElement("div"); wrap.className = "m-settings";
      var srcSet = document.createElement("fieldset"); srcSet.innerHTML = "<legend>출처</legend>";
      $$("[data-filter-source]", toolbar).forEach(function (orig) {
        srcSet.appendChild(proxy(orig.textContent.trim(), function () { return orig.getAttribute("aria-pressed") === "true"; }, function () { orig.click(); }));
      });
      var viewSet = document.createElement("fieldset"); viewSet.innerHTML = "<legend>보기</legend>";
      var hr = $("#toggle-hide-read"), low = $("#toggle-low"), all = $("#mark-all-read");
      if (hr) viewSet.appendChild(proxy("읽은 것 숨기기", function () { return hr.getAttribute("aria-pressed") === "true"; }, function () { hr.click(); }));
      if (low && low.style.display !== "none") viewSet.appendChild(proxy("낮은 관련도 기사도 보기", function () { return !!SB.load("sb:filter", {}).showLow; }, function () { low.click(); }));
      wrap.appendChild(srcSet); wrap.appendChild(viewSet);
      if (all) {
        var ab = document.createElement("button"); ab.type = "button"; ab.className = "chip wide"; ab.textContent = "모두 읽음으로 표시";
        ab.onclick = function () { all.click(); haptic(); sheet.close(); };
        wrap.appendChild(ab);
      }
      var sheet = openSheet({ title: "필터", body: wrap, from: fab });
      function proxy(label, get, act) {
        var l = document.createElement("label"), i = document.createElement("input");
        i.type = "checkbox"; i.checked = get();
        i.onchange = function () { act(); $$("input", wrap).forEach(function (x) { if (x._get) x.checked = x._get(); }); };
        i._get = get; l.appendChild(i); l.appendChild(document.createTextNode(" " + label)); return l;
      }
    });
  }

  // ── 정세: 지도 점·지역 칩·요충지 → 바텀 시트 ─────────────────────────
  var geoRoot = $("#geo-root");
  if (geoRoot) {
    var dateShort = (($("#map-h .muted") || {}).textContent || "").replace(" 브리핑 기준", "");
    var openRegion = function (slugName, from) {
      var panel = document.getElementById("map-" + slugName);
      if (!panel) return;
      var home = panel.parentNode, next = panel.nextSibling;
      $$("[data-map-region]").forEach(function (d) { d.setAttribute("aria-pressed", d.dataset.mapRegion === slugName); });
      var dot = $('.map-dot[data-map-region="' + slugName + '"]');
      var name = (($(".mp-name", panel) || {}).textContent || slugName);
      var n = $$(".mp-list > li", panel).length;
      var head = document.createElement("div");
      head.className = "muted small"; head.style.margin = "0 0 12px";
      head.textContent = (dateShort ? dateShort + " · " : "") + (dot ? dot.title.replace(name + ": ", "") : n + "건");
      var box = document.createElement("div"); box.appendChild(head); box.appendChild(panel);
      openSheet({ title: name, body: box, snap: "half", from: from,
        onClose: function () { home.insertBefore(panel, next); } });
    };
    window.addEventListener("click", function (e) {
      var d = e.target.closest("[data-map-region]");
      if (d) { e.preventDefault(); e.stopPropagation(); openRegion(d.dataset.mapRegion, d); return; }
      var sum = e.target.closest(".cp-card > summary");
      if (sum) { e.preventDefault(); e.stopPropagation(); openCp(sum.parentNode, sum); }
    }, true);   // 캡처 단계: app.js의 데스크톱 동작(패널 전환·스크롤)보다 먼저
    var openCp = function (card, from) {
      var p = geoRoot.dataset.period || "30";
      var src = $(".cp-body.p" + p, card); if (!src) return;
      var body = src.cloneNode(true); body.classList.remove("p7", "p30");
      var stat = $(".cp-stat.p" + p, card);
      var head = document.createElement("div"); head.className = "muted small"; head.style.margin = "0 0 12px";
      var cnt = stat ? $(".cp-count", stat).textContent.trim() : "", imp = stat ? $(".imp-chip", stat).textContent.trim() : "–";
      head.textContent = "최근 " + p + "일 · " + cnt + (imp !== "–" ? " · 평균 영향 " + imp : "");
      var box = document.createElement("div"); box.appendChild(head); box.appendChild(body);
      openSheet({ title: $(".cp-name", card).textContent, body: box, snap: "half", from: from });
    };
    var fromHash = function () {
      var id = decodeURIComponent(location.hash.slice(1));
      if (id.indexOf("map-") === 0) openRegion(id.slice(4));
      else if (id.indexOf("cp-") === 0 && document.getElementById(id)) openCp(document.getElementById(id));
    };
    if (location.hash) setTimeout(fromHash, 120);
    window.addEventListener("hashchange", fromHash);
    // 히트맵: 기본 최근 4주, 버튼으로 8주
    var heat = $(".heat");
    if (heat) {
      var hb = document.createElement("button"); hb.type = "button"; hb.className = "chip wide m-heat-more"; hb.textContent = "8주 모두 보기";
      hb.setAttribute("aria-expanded", "false");
      hb.onclick = function () { var o = heat.classList.toggle("show-all"); hb.textContent = o ? "최근 4주만 보기" : "8주 모두 보기"; hb.setAttribute("aria-expanded", o); };
      heat.closest(".table-scroll").after(hb);
    }
  }

  // ── 더보기 시트 · 설정 시트 ─────────────────────────────────────
  var moreBtn = $("#m-more-btn");
  function openSettings(from) {
    var tpl = $("#tpl-settings"); if (!tpl) return;
    var form = tpl.content.firstElementChild.cloneNode(true);
    $$("input", form).forEach(function (i) {
      i.checked = S[i.name] === i.value;
      i.addEventListener("change", function () {
        S[i.name] = i.value; SB.save("sb:settings", S); applySettings(); measure();
        if (i.name === "haptic" && i.value === "on") haptic();
      });
    });
    openSheet({ title: "설정", body: form, from: from || moreBtn });
  }
  if (moreBtn) moreBtn.addEventListener("click", function () {
    var list = $("#tpl-more").content.firstElementChild.cloneNode(true);
    var next = null;
    var sh = openSheet({ title: "더보기", body: list, from: moreBtn, after: function () { if (next) next(); } });
    $("[data-open-settings]", list).addEventListener("click", function () { next = openSettings; sh.close(); });
  });

  // ── 대문: 설치 배너 ───────────────────────────────────────────
  var deferredInstall = null;
  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault(); deferredInstall = e;
    if (page !== "home" || STANDALONE) return;
    var dismissed = SB.load("sb:installDismissed", 0);
    if (dismissed && Date.now() - dismissed < 30 * 864e5) return;
    if ($(".m-install")) return;
    var box = document.createElement("div"); box.className = "m-install"; box.setAttribute("role", "region"); box.setAttribute("aria-label", "앱 설치");
    box.innerHTML = '<p><b>홈 화면에 추가</b><br>앱처럼 열고, 오프라인에서도 마지막 브리핑을 볼 수 있어요.</p>' +
      '<button type="button" class="no">나중에</button><button type="button" class="go">추가</button>';
    $(".hero").after(box);
    $(".go", box).onclick = function () {
      deferredInstall.prompt();
      deferredInstall.userChoice.finally(function () { box.remove(); deferredInstall = null; });
    };
    $(".no", box).onclick = function () { SB.save("sb:installDismissed", Date.now()); box.remove(); };
  });
  window.addEventListener("appinstalled", function () { var b = $(".m-install"); if (b) b.remove(); snackbar("홈 화면에 추가했어요"); });

  // ── 스크랩: 길게 눌러 다중 선택 → 공유 · 삭제 ──────────────────────
  var scrapList = $("#scrap-list");
  if (scrapList) {
    var selecting = false, sel = {}, selbar = null;
    var cards = function () { return $$(".card[data-scrap]", scrapList); };
    var updateBar = function () {
      var n = Object.keys(sel).length;
      $("b", selbar).textContent = n + "개 선택";
      $$("[data-need]", selbar).forEach(function (b) { b.disabled = !n; });
    };
    var enter = function (first) {
      if (selecting) return;
      selecting = true; sel = {}; document.body.classList.add("m-selecting");
      selbar = document.createElement("div"); selbar.className = "m-selbar"; selbar.setAttribute("role", "toolbar"); selbar.setAttribute("aria-label", "선택한 스크랩");
      selbar.innerHTML = '<button type="button" data-x aria-label="선택 끝내기">✕</button><b aria-live="polite"></b>' +
        '<button type="button" data-need data-share>공유</button><button type="button" data-need data-del class="danger">삭제</button>';
      document.body.appendChild(selbar);
      $("[data-x]", selbar).onclick = function () { closeLayer("select"); };
      $("[data-share]", selbar).onclick = function () { shareScraps(Object.keys(sel)); };
      $("[data-del]", selbar).onclick = function () {
        var ids = Object.keys(sel), removed = ids.map(function (id) { return [id, SB.unstar(id)]; });
        ids.forEach(function (id) { var c = $('.card[data-scrap="' + CSS.escape(id) + '"]', scrapList); if (c) c.remove(); });
        closeLayer("select");
        snackbar(ids.length + "건을 삭제했어요", { action: "되돌리기", onAction: function () {
          removed.forEach(function (p) { if (p[1]) SB.restar(p[0], p[1]); }); location.reload();
        } });
      };
      pushLayer("select", exit);
      toggle(first); haptic();
    };
    var exit = function () {
      selecting = false; sel = {}; document.body.classList.remove("m-selecting");
      cards().forEach(function (c) { c.classList.remove("is-selected"); c.removeAttribute("aria-selected"); });
      if (selbar) { selbar.remove(); selbar = null; }
    };
    var toggle = function (c) {
      var id = c.dataset.scrap;
      if (sel[id]) delete sel[id]; else sel[id] = 1;
      c.classList.toggle("is-selected", !!sel[id]); c.setAttribute("aria-selected", !!sel[id]);
      updateBar();
    };
    var pressT = null, px = 0, py = 0, longFired = false;
    scrapList.addEventListener("pointerdown", function (e) {
      var c = e.target.closest(".card[data-scrap]"); if (!c) return;
      px = e.clientX; py = e.clientY; longFired = false;
      pressT = setTimeout(function () { longFired = true; if (!selecting) enter(c); }, 500);
    });
    scrapList.addEventListener("pointermove", function (e) { if (pressT && Math.hypot(e.clientX - px, e.clientY - py) > 10) { clearTimeout(pressT); pressT = null; } });
    ["pointerup", "pointercancel"].forEach(function (t) { scrapList.addEventListener(t, function () { clearTimeout(pressT); pressT = null; }); });
    scrapList.addEventListener("contextmenu", function (e) { if (e.target.closest(".card[data-scrap]")) e.preventDefault(); });
    scrapList.addEventListener("click", function (e) {
      var c = e.target.closest(".card[data-scrap]"); if (!c) return;
      if (longFired) { e.preventDefault(); e.stopPropagation(); longFired = false; return; }
      if (selecting) { e.preventDefault(); e.stopPropagation(); toggle(c); }
    }, true);
    var md = function (ids) {
      var st = SB.stars();
      return ids.map(function (id) { return st[id]; }).filter(Boolean).map(function (a) {
        return "- [" + a.title + "](" + a.url + ") — " + a.source + " · " + a.date + (a.summary ? "\n  " + a.summary : "");
      }).join("\n");
    };
    var shareScraps = function (ids) {
      var text = md(ids), name = "scrap-" + new Date().toISOString().slice(0, 10) + ".md";
      var file = typeof File === "function" ? new File([text], name, { type: "text/markdown" }) : null;
      if (file && navigator.canShare && navigator.canShare({ files: [file] })) {
        navigator.share({ files: [file], title: "해운물류 스크랩" }).catch(function () {});
      } else if (navigator.share) {
        navigator.share({ title: "해운물류 스크랩", text: text }).catch(function () {});
      } else copy(text, "Markdown으로 복사했어요");
    };
    var expMd = $("#export-scrap-md");
    if (expMd) expMd.addEventListener("click", function (e) {
      var ids = Object.keys(SB.stars()); if (!ids.length) return;
      var probe = typeof File === "function" ? new File(["x"], "x.md", { type: "text/markdown" }) : null;
      if (probe && navigator.canShare && navigator.canShare({ files: [probe] })) {
        e.preventDefault(); e.stopImmediatePropagation(); shareScraps(ids);
      }   // 공유 불가면 app.js의 다운로드가 그대로 실행된다
    }, true);
    var hint = document.createElement("p"); hint.className = "muted small"; hint.textContent = "카드를 길게 누르면 여러 개를 골라 공유하거나 지울 수 있어요.";
    scrapList.before(hint);
  }

  // ── 태그 · 지난 브리핑 검색 ────────────────────────────────────
  var search = $(".m-search input");
  if (search) {
    var targets = $$(search.dataset.target);
    var none = document.createElement("p"); none.className = "m-noresult"; none.textContent = "검색 결과가 없습니다."; none.hidden = true;
    (targets[0] && targets[0].parentNode.parentNode || document.body).appendChild(none);
    search.addEventListener("input", function () {
      var q = search.value.trim().toLowerCase(), shown = 0;
      targets.forEach(function (t) { var hit = !q || t.textContent.toLowerCase().indexOf(q) >= 0; t.hidden = !hit; if (hit) shown++; });
      none.hidden = !!shown;
    });
  }

  // ── 오프라인 띠 ───────────────────────────────────────────────
  var off = $(".m-offline");
  var net = function () { if (off) off.hidden = navigator.onLine; };
  window.addEventListener("online", net); window.addEventListener("offline", net); net();

  // ── 당겨서 새로고침 (홈 화면 앱 모드에서만, 오늘 화면) ──────────────────
  if (STANDALONE && page === "today") {
    var ptr = document.createElement("div"); ptr.className = "m-ptr"; ptr.setAttribute("aria-hidden", "true");
    ptr.innerHTML = '<svg viewBox="0 0 24 24"><path d="M20 12a8 8 0 1 1-2.34-5.66M20 4v5h-5"/></svg>';
    document.body.appendChild(ptr);
    var sy = null, pull = 0;
    window.addEventListener("touchstart", function (e) { if (window.scrollY <= 0 && !layers.length) { sy = e.touches[0].clientY; pull = 0; } }, { passive: true });
    window.addEventListener("touchmove", function (e) {
      if (sy === null) return;
      pull = Math.max(0, e.touches[0].clientY - sy);
      var p = Math.min(pull, 110);
      ptr.style.transform = "translateY(" + (p - 60) + "px) rotate(" + p * 3 + "deg)";
      ptr.classList.toggle("is-ready", pull > 72);
    }, { passive: true });
    window.addEventListener("touchend", function () {
      if (sy === null) return;
      sy = null;
      if (pull > 72) { ptr.classList.add("is-loading"); ptr.style.transform = "translateY(20px)"; location.reload(); }
      else ptr.style.transform = "";
    });
  }
})();
