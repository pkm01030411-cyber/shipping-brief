/* 해운물류 데일리 — 클라이언트 편의 기능
   읽음 체크 · 진행 바 · 출처 필터 · 낮은 관련도 접기 · 키보드 내비 · 스크랩
   모든 상태는 localStorage에만 저장됩니다 (서버 없음). */
(function () {
  "use strict";
  var KEY_READ = "sb:read", KEY_STAR = "sb:star", KEY_FILTER = "sb:filter", KEY_DAYS = "sb:days";

  function load(k, d) { try { return JSON.parse(localStorage.getItem(k)) || d; } catch (e) { return d; } }
  function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }

  var read = load(KEY_READ, {});     // {articleId: timestamp}
  var star = load(KEY_STAR, {});     // {articleId: {title,url,...}}
  var items = Array.prototype.slice.call(document.querySelectorAll("[data-article]"));

  // ── 읽음 ────────────────────────────────────────────────
  function isRead(id) { return !!read[id]; }
  function todayKey() { var d = new Date(); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
  function noteDay() { var days = load(KEY_DAYS, {}); days[todayKey()] = 1; save(KEY_DAYS, days); }
  function streak() {
    var days = load(KEY_DAYS, {}), n = 0, d = new Date();
    // 오늘 아직 안 읽었으면 어제부터 센다
    if (!days[todayKey()]) d.setDate(d.getDate() - 1);
    for (;;) {
      var k = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
      if (!days[k]) break; n++; d.setDate(d.getDate() - 1);
    }
    return n;
  }
  function setRead(id, v) {
    if (v) { read[id] = Date.now(); noteDay(); } else delete read[id];
    save(KEY_READ, read); render();
  }
  function toggleRead(el) { var id = el.dataset.article; setRead(id, !isRead(id)); }

  // ── 스크랩 ──────────────────────────────────────────────
  function articleData(el) {
    var d = el.dataset;
    return { id: d.article, title: d.title, url: d.url, source: d.sourceName || d.source, date: d.date,
             summary: d.summary || "", tags: (d.tags || "").split("|").filter(Boolean), savedAt: Date.now() };
  }
  function toggleStar(el) {
    var id = el.dataset.article;
    if (star[id]) delete star[id]; else star[id] = articleData(el);
    save(KEY_STAR, star); render();
  }

  // ── 필터 / 접기 ──────────────────────────────────────────
  var filter = load(KEY_FILTER, { source: "all", showLow: false, hideRead: false });
  function setFilter(patch) { Object.assign(filter, patch); save(KEY_FILTER, filter); render(); }

  // ── 렌더 ───────────────────────────────────────────────
  function render() {
    var total = 0, done = 0, visibleEls = [];
    // 홈: 오늘 기사 id 목록으로 진행률 계산
    var home = document.querySelector("[data-today-ids]");
    if (home && !items.length) {
      var ids = home.dataset.todayIds.split("|").filter(Boolean);
      total = ids.length; done = ids.filter(isRead).length;
    }
    var st = document.getElementById("streak"); if (st) st.textContent = streak();
    var hs = document.getElementById("home-star"); if (hs) hs.textContent = Object.keys(star).length;
    items.forEach(function (el) {
      var id = el.dataset.article;
      var r = isRead(id), s = !!star[id];
      el.classList.toggle("is-read", r);
      el.classList.toggle("is-starred", s);
      var rb = el.querySelector(".btn-read"); if (rb) { rb.setAttribute("aria-pressed", r); rb.title = r ? "읽지 않음으로" : "읽음으로 표시"; }
      var sb = el.querySelector(".btn-star"); if (sb) { sb.setAttribute("aria-pressed", s); sb.textContent = s ? "★" : "☆"; sb.title = s ? "스크랩 해제" : "스크랩"; }

      var low = el.dataset.low === "1";
      var hidden = !el.hasAttribute("data-solo") && (filter.source !== "all" && el.dataset.source !== filter.source)
                || (!el.hasAttribute("data-solo") && low && !filter.showLow)
                || (!el.hasAttribute("data-solo") && filter.hideRead && r);
      el.classList.toggle("is-hidden", hidden);
      total++; if (r) done++;
      if (!hidden) visibleEls.push(el);
    });
    // 진행 바
    var bar = document.getElementById("progress");
    if (bar) {
      var pct = total ? Math.round(done / total * 100) : 0;
      bar.querySelector(".progress-fill").style.width = pct + "%";
      bar.querySelector(".progress-text").textContent = done + " / " + total + " 읽음" + (done === total && total ? " · 오늘 완료 ✓" : "");
      bar.classList.toggle("is-done", done === total && total > 0);
    }
    // 필터 칩 상태
    document.querySelectorAll("[data-filter-source]").forEach(function (c) {
      c.setAttribute("aria-pressed", c.dataset.filterSource === filter.source);
    });
    var hr = document.getElementById("toggle-hide-read"); if (hr) hr.setAttribute("aria-pressed", filter.hideRead);
    var lowBtn = document.getElementById("toggle-low");
    if (lowBtn) {
      var lowCount = items.filter(function (e) { return e.dataset.low === "1"; }).length;
      lowBtn.textContent = (filter.showLow ? "낮은 관련도 접기" : "낮은 관련도 " + lowCount + "건 더 보기");
      lowBtn.style.display = lowCount ? "" : "none";
    }
    var sc = document.getElementById("star-count"); if (sc) sc.textContent = Object.keys(star).length || "";
    window.__visible = visibleEls;
    try { document.dispatchEvent(new CustomEvent("sb:render", { detail: { total: total, done: done } })); } catch (e) {}
  }

  // ── 이벤트 ─────────────────────────────────────────────
  document.addEventListener("click", function (e) {
    var t = e.target.closest("button, a");
    if (!t) return;
    if (t.classList.contains("btn-read")) { toggleRead(t.closest("[data-article]")); e.preventDefault(); }
    else if (t.classList.contains("btn-star")) { toggleStar(t.closest("[data-article]")); e.preventDefault(); }
    else if (t.dataset.filterSource) { setFilter({ source: t.dataset.filterSource }); }
    else if (t.id === "toggle-low") { setFilter({ showLow: !filter.showLow }); }
    else if (t.id === "toggle-hide-read") { setFilter({ hideRead: !filter.hideRead }); }
    else if (t.id === "mark-all-read") { items.forEach(function (el) { read[el.dataset.article] = Date.now(); }); noteDay(); save(KEY_READ, read); render(); }
    else if (t.classList.contains("origin-link")) {
      // 원문을 열면 자동으로 읽음 처리
      var el = t.closest("[data-article]"); if (el && !isRead(el.dataset.article)) setRead(el.dataset.article, true);
    }
  });

  // ── 키보드: j/k 이동, o 원문, x 읽음, s 스크랩, ? 도움말 ──
  var cursor = -1;
  function focusAt(i) {
    var vis = window.__visible || [];
    if (!vis.length) return;
    cursor = Math.max(0, Math.min(vis.length - 1, i));
    items.forEach(function (el) { el.classList.remove("is-cursor"); });
    var el = vis[cursor]; el.classList.add("is-cursor");
    el.scrollIntoView({ block: "center", behavior: "smooth" });
  }
  document.addEventListener("keydown", function (e) {
    if (e.target.matches("input, textarea") || e.metaKey || e.ctrlKey || e.altKey) return;
    var vis = window.__visible || [], cur = vis[cursor];
    switch (e.key) {
      case "j": focusAt(cursor + 1); break;
      case "k": focusAt(cursor - 1); break;
      case "x": if (cur) toggleRead(cur); break;
      case "s": if (cur) toggleStar(cur); break;
      case "o": if (cur) { window.open(cur.dataset.url, "_blank", "noopener"); if (!isRead(cur.dataset.article)) setRead(cur.dataset.article, true); } break;
      case "?": var h = document.getElementById("kbd-help"); if (h) h.classList.toggle("is-open"); break;
      default: return;
    }
    e.preventDefault();
  });

  // ── 스크랩 페이지 ────────────────────────────────────────
  var SOURCE_NAMES = { ksg: "코리아쉬핑가제트", cargonews: "카고뉴스" };
  Object.keys(star).forEach(function (k) { var a = star[k]; if (a && SOURCE_NAMES[a.source]) a.source = SOURCE_NAMES[a.source]; });
  var scrapRoot = document.getElementById("scrap-list");
  if (scrapRoot) {
    var list = Object.keys(star).map(function (k) { return star[k]; }).sort(function (a, b) { return b.savedAt - a.savedAt; });
    if (!list.length) {
      scrapRoot.innerHTML = '<p class="muted">아직 스크랩한 기사가 없습니다. 브리핑에서 ☆ 를 누르면 여기에 모입니다.</p>';
    } else {
      scrapRoot.innerHTML = list.map(function (a) {
        return '<article class="card" data-scrap="' + a.id + '">' +
          '<div class="kicker"><span class="src">' + esc(a.source) + '</span> · ' + esc(a.date) +
          '<button class="btn-unstar" title="스크랩 해제">✕</button></div>' +
          '<h3><a href="' + esc(a.url) + '" target="_blank" rel="noopener">' + esc(a.title) + '</a></h3>' +
          (a.summary ? '<p class="summary">' + esc(a.summary) + '</p>' : '') +
          (a.tags.length ? '<div class="tags">' + a.tags.map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; }).join("") + '</div>' : '') +
          '</article>';
      }).join("");
      scrapRoot.addEventListener("click", function (e) {
        var b = e.target.closest(".btn-unstar"); if (!b) return;
        var card = b.closest("[data-scrap]"); delete star[card.dataset.scrap]; save(KEY_STAR, star); card.remove();
        var sc = document.getElementById("star-count"); if (sc) sc.textContent = Object.keys(star).length || "";
        if (!Object.keys(star).length) scrapRoot.innerHTML = '<p class="muted">스크랩이 비었습니다.</p>';
      });
    }
    var exp = document.getElementById("export-scrap");
    if (exp) exp.addEventListener("click", function () {
      var blob = new Blob([JSON.stringify(list, null, 2)], { type: "application/json" });
      var a = document.createElement("a"); a.href = URL.createObjectURL(blob);
      a.download = "scrap-" + new Date().toISOString().slice(0, 10) + ".json"; a.click();
    });
    var expMd = document.getElementById("export-scrap-md");
    if (expMd) expMd.addEventListener("click", function () {
      var md = list.map(function (a) { return "- [" + a.title + "](" + a.url + ") — " + a.source + " · " + a.date + (a.summary ? "\n  " + a.summary : ""); }).join("\n");
      var blob = new Blob([md], { type: "text/markdown" });
      var a = document.createElement("a"); a.href = URL.createObjectURL(blob);
      a.download = "scrap-" + new Date().toISOString().slice(0, 10) + ".md"; a.click();
    });
  }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }

  // ── 정세 대시보드: 기간 토글, 앵커로 카드 열기 ─────────────────
  var geoRoot = document.getElementById("geo-root");
  if (geoRoot) {
    var setPeriod = function (p) {
      geoRoot.dataset.period = p;
      document.querySelectorAll("[data-geo-period]").forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.geoPeriod === p); });
      save("sb:geoPeriod", p);
    };
    setPeriod(load("sb:geoPeriod", "30"));
    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-geo-period]"); if (b) setPeriod(b.dataset.geoPeriod);
    });
    // 지도: JS가 있을 때만 패널을 하나씩 보여준다 (없으면 전부 펼쳐진 채)
    geoRoot.classList.add("js-map");
    var selectRegion = function (slugName, focusPanel) {
      var panel = document.getElementById("map-" + slugName); if (!panel) return false;
      document.querySelectorAll(".map-panel").forEach(function (p) { p.classList.toggle("is-active", p === panel); });
      document.querySelectorAll("[data-map-region]").forEach(function (d) { d.setAttribute("aria-pressed", d.dataset.mapRegion === slugName); });
      if (focusPanel) panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
      return true;
    };
    document.addEventListener("click", function (e) {
      var d = e.target.closest("[data-map-region]"); if (!d) return;
      selectRegion(d.dataset.mapRegion, true);
      if (history.replaceState) history.replaceState(null, "", "#map-" + d.dataset.mapRegion);
    });
    var openHash = function () {
      var id = decodeURIComponent(location.hash.slice(1)); if (!id) return;
      if (id.indexOf("map-") === 0 && selectRegion(id.slice(4), false)) {
        var sec = document.querySelector(".map-section"); if (sec) sec.scrollIntoView({ block: "start" });
        return;
      }
      var el = document.getElementById(id); if (!el) return;
      if (el.tagName === "DETAILS") el.open = true;
      el.classList.add("is-target"); setTimeout(function () { el.classList.remove("is-target"); }, 1600);
    };
    window.addEventListener("hashchange", openHash); openHash();
  }

  // ── PWA 서비스워커 ──────────────────────────────────────
  if ("serviceWorker" in navigator && (location.protocol === "https:" || /^(localhost|127\.0\.0\.1)$/.test(location.hostname))) {
    var root = document.documentElement.dataset.root || "";
    navigator.serviceWorker.register(root + "sw.js").catch(function () {});
  }

  // 모바일 레이어(mobile.js)가 같은 상태와 저장소를 쓰도록 공개
  window.SB = {
    load: load, save: save, isRead: isRead, setRead: setRead, toggleRead: toggleRead, toggleStar: toggleStar,
    isStarred: function (id) { return !!star[id]; }, stars: function () { return star; },
    unstar: function (id) { var v = star[id]; delete star[id]; save(KEY_STAR, star); render(); return v; },
    restar: function (id, v) { star[id] = v; save(KEY_STAR, star); render(); },
    streak: streak, render: render
  };

  render();
})();
