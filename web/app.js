/* PeatGuard mobile web app. No build step.
   Data: data/today.json, data/metrics.json, data/replay.json, data/air.json (scripts/export_web.py).
   Air quality is fetched live from Open-Meteo when possible, with data/air.json as fallback. */
(function () {
  'use strict';

  var CFG = window.PG_CONFIG || {};
  var S = {
    today: null, metrics: null, replay: null, impact: null, air: null, airState: 'idle',
    impactShare: 3, impactHa: 5, impactCost: 500, heroOpen: false, airSort: 'worst',
    filter: 'all', mapSel: null, replayDay: null, airSel: 'Kuala Lumpur',
    warn: { zone: null, who: 'community', lang: 'en', text: null },
    lastSent: null, smoulder: false, sensorZone: null
  };
  var app = document.getElementById('app');
  var sheetRoot = document.getElementById('sheet-root');
  var leafletMap = null, gmap = null, lastFocus = null;

  /* ---------------- storage (per-viewer conveniences only) ---------------- */
  function load(key, fallback) {
    try { var v = localStorage.getItem('pg_' + key); return v === null ? fallback : JSON.parse(v); }
    catch (e) { return fallback; }
  }
  function save(key, v) { try { localStorage.setItem('pg_' + key, JSON.stringify(v)); } catch (e) { /* ignore */ } }
  var assigned = load('assigned', {});

  /* ---------------- helpers ---------------- */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function cap(s) { s = String(s || ''); return s.charAt(0).toUpperCase() + s.slice(1); }
  function pct(p) { var v = Math.round(p * 100); return v < 1 ? '<1%' : v + '%'; }
  function pct0(x) { return Math.round(x * 100) + '%'; }
  function lift(a, b) { return b ? Math.round((a / b - 1) * 100) : 0; }
  function lvl(l) { return l === 'High' ? 'high' : l === 'Elevated' ? 'elevated' : 'low'; }
  function zoneById(id) {
    if (!S.today) return null;
    for (var i = 0; i < S.today.zones.length; i++) if (S.today.zones[i].id === id) return S.today.zones[i];
    return null;
  }
  function tz(o) { return Object.assign({ timeZone: 'Asia/Kuala_Lumpur' }, o); }
  function fmtDate(iso, o) {
    var d = new Date(iso + (iso.length === 10 ? 'T00:00:00+08:00' : ''));
    return d.toLocaleDateString('en-GB', tz(o || { day: 'numeric', month: 'short', year: 'numeric' }));
  }
  function fmtTime(iso) { return new Date(iso).toLocaleTimeString('en-GB', tz({ hour: 'numeric', minute: '2-digit', hour12: true })); }
  function updatedLine() {
    var g = S.today.generatedAt;
    return 'Updated ' + fmtTime(g) + ', ' + fmtDate(g, { weekday: 'short', day: 'numeric', month: 'short' });
  }
  function area(z) { return 'near ' + z.place + ', ' + regionName(z.region); }
  function regionName(r) { return r === 'South Sumatra-Jambi' ? 'South Sumatra' : r; }
  var STORY = {
    'Active fire: spread risk': 'Fire already burning here',
    'New fire risk: drought': 'Dry spell could start a new fire',
    'New fire risk: El Niño / IOD dry spell': 'El Niño dry spell',
    'New fire risk: repeat-burn area': 'This area burns often',
    'New fire risk: fire spreading from nearby': 'Fire spreading from nearby',
    'New fire risk: fire season': 'Peak fire season here',
    'New fire risk': 'Could start a new fire',
    'Low risk': 'No strong warning signs'
  };
  function story(z) { return STORY[z.category] || z.category; }
  function toast(msg) {
    var t = document.getElementById('toast');
    t.textContent = msg; t.classList.add('show');
    clearTimeout(toast._t); toast._t = setTimeout(function () { t.classList.remove('show'); }, 2200);
  }
  function copy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return false; });
    }
    return Promise.resolve(false);
  }

  /* ---------------- icons ---------------- */
  var I = {
    logo: '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z" fill="#1F0C05"/>',
    down: '<path d="M6 9l6 6 6-6"/>',
    flame: '<path d="M12 22c4.4 0 7-2.9 7-6.6 0-3.4-2.2-5.6-3.6-7.2-.4 1.7-1.3 2.9-2.6 3.5.3-3.3-1.2-6.4-4-8.7.2 3.3-1.6 5.1-3 6.8C4.6 11.3 5 13.4 5 15.4 5 19.1 7.6 22 12 22z"/>',
    back: '<path d="M15 18l-6-6 6-6"/>',
    chev: '<path d="M9 18l6-6-6-6"/>',
    map: '<path d="m9 4-6 2v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
    wind: '<path d="M3 8h11a3 3 0 1 0-3-3"/><path d="M3 12h15a3 3 0 1 1-3 3"/><path d="M3 16h7"/>',
    shield: '<path d="M12 3l7 3v6c0 4.5-3 8-7 9-4-1-7-4.5-7-9V6z"/><path d="m9 12 2 2 4-4"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    share: '<path d="M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7"/><path d="M16 6l-4-4-4 4M12 2v14"/>',
    chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    close: '<path d="M18 6 6 18M6 6l12 12"/>'
  };
  function ic(name, color, sw) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="' + (color || 'currentColor') + '" stroke-width="' + (sw || 1.8) +
      '" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + I[name] + '</svg>';
  }
  function backBtn(href) { return '<a class="icon-btn" href="' + href + '" aria-label="Back">' + ic('back', null, 2) + '</a>'; }
  function topbar(back, title, sub, right) {
    return '<div class="topbar">' + (back || '<span></span>') + '<div class="t"><h1>' + esc(title) + '</h1>' +
      (sub ? '<span>' + esc(sub) + '</span>' : '') + '</div>' + (right || '<span></span>') + '</div>';
  }
  function how(kind, arg, label, cls) {
    return '<button class="how' + (cls ? ' ' + cls : '') + '" data-act="sheet" data-v="' + kind + '"' + (arg ? ' data-arg="' + esc(arg) + '"' : '') + '>' +
      ic('info') + esc(label || 'How this was calculated') + '</button>';
  }
  function tabs(active) {
    var items = [['today', '#/today', 'flame', 'Today'], ['map', '#/map', 'map', 'Map'], ['air', '#/air', 'wind', 'Air'], ['evidence', '#/evidence', 'shield', 'Evidence']];
    return '<nav class="tabs" aria-label="Main">' + items.map(function (it) {
      return '<a href="' + it[1] + '"' + (active === it[0] ? ' aria-current="page"' : '') + '>' + ic(it[2]) + it[3] + '</a>';
    }).join('') + '</nav>';
  }

  /* ---------------- air quality ---------------- */
  var AQI = [
    [50, 'Good', '#5BBF7A', '#7FD39A', 'Air is clean. Normal outdoor work is fine.'],
    [100, 'Moderate', '#E8C547', '#EDD26A', 'Acceptable for most people. Anyone sensitive to smoke should limit long outdoor work.'],
    [150, 'Unhealthy for sensitive groups', '#F29A3A', '#F5AE5E', 'Children, older people, pregnant women and anyone with asthma or heart problems should limit time outdoors. Patrol teams should carry N95 masks.'],
    [200, 'Unhealthy', '#E5533D', '#F07A66', 'Everyone should limit time outdoors. Patrol teams should wear N95 masks and rotate crews.'],
    [300, 'Very unhealthy', '#A64CA6', '#C98AC9', 'Avoid outdoor activity. Send patrols only with N95 masks and short shifts.'],
    [1e9, 'Hazardous', '#7E2A3B', '#D9768A', 'Stay indoors. Postpone patrols that are not urgent.']
  ];
  function aqiCat(v) { for (var i = 0; i < AQI.length; i++) if (v <= AQI[i][0]) return { i: i, name: AQI[i][1], color: AQI[i][2], text: AQI[i][3], advice: AQI[i][4] }; }
  function scalePos(v) {
    var edges = [0, 50, 100, 150, 200, 300, 500];
    v = Math.max(0, Math.min(500, v));
    for (var i = 0; i < 6; i++) if (v <= edges[i + 1]) return ((i + (v - edges[i]) / (edges[i + 1] - edges[i])) / 6) * 100;
    return 100;
  }
  var AIR_CITIES = [
    ['Kuala Lumpur', 'Kuala Lumpur', 3.139, 101.687], ['Shah Alam', 'Selangor', 3.073, 101.518], ['Klang', 'Selangor', 3.044, 101.445],
    ['Kuala Selangor', 'Selangor', 3.34, 101.25], ['Seremban', 'Negeri Sembilan', 2.725, 101.938], ['Melaka', 'Melaka', 2.189, 102.25],
    ['Johor Bahru', 'Johor', 1.493, 103.741], ['Muar', 'Johor', 2.045, 102.568], ['Kuantan', 'Pahang', 3.808, 103.326],
    ['Ipoh', 'Perak', 4.597, 101.09], ['George Town', 'Penang', 5.414, 100.329], ['Kuching', 'Sarawak', 1.553, 110.359],
    ['Sibu', 'Sarawak', 2.3, 111.82], ['Pekanbaru', 'Riau, Indonesia', 0.507, 101.448],
    ['Palembang', 'South Sumatra, Indonesia', -2.99, 104.756], ['Palangka Raya', 'Central Kalimantan, Indonesia', -2.21, 113.92]
  ];
  function airLive() {
    var places = AIR_CITIES.map(function (c) { return { name: c[0], area: c[1], lat: c[2], lon: c[3], kind: 'city' }; })
      .concat(S.today.zones.map(function (z) { return { name: z.id, area: area(z), lat: z.lat, lon: z.lon, kind: 'zone' }; }));
    var batches = [];
    for (var b = 0; b < places.length; b += 50) batches.push(places.slice(b, b + 50));
    return Promise.all(batches.map(function (batch) {
      var u = 'https://air-quality-api.open-meteo.com/v1/air-quality?latitude=' + batch.map(function (p) { return p.lat; }).join(',') +
        '&longitude=' + batch.map(function (p) { return p.lon; }).join(',') +
        '&current=us_aqi,pm2_5&hourly=us_aqi&forecast_days=4&timezone=Asia%2FKuala_Lumpur';
      return fetch(u).then(function (r) { if (!r.ok) throw new Error('air ' + r.status); return r.json(); }).then(function (js) {
        js = Array.isArray(js) ? js : [js];
        return batch.map(function (p, k) {
          var j = js[k] || {}, h = j.hourly || { time: [], us_aqi: [] }, byDay = {}, order = [];
          for (var i = 0; i < h.time.length; i++) {
            var d = h.time[i].slice(0, 10), v = h.us_aqi[i];
            if (v == null) continue;
            if (!(d in byDay)) { byDay[d] = v; order.push(d); } else if (v > byDay[d]) byDay[d] = v;
          }
          var cur = j.current || {};
          return Object.assign({}, p, { aqi: cur.us_aqi == null ? null : Math.round(cur.us_aqi), pm25: cur.pm2_5, time: cur.time,
            days: order.slice(0, 4).map(function (d) { return [d, Math.round(byDay[d])]; }) });
        });
      });
    })).then(function (parts) {
      return { generatedAt: new Date().toISOString(), live: true, places: [].concat.apply([], parts) };
    });
  }
  function ensureAir() {
    if (S.airState !== 'idle') return;
    S.airState = 'loading';
    airLive().catch(function () {
      return getJSON('data/air.json').then(function (j) { j.live = false; return j; });
    }).then(function (a) { S.air = a; S.airState = 'ready'; refreshIf(/^#\/(today|air|zone)|^#?\/?$/); })
      .catch(function () { S.airState = 'failed'; refreshIf(/^#\/(today|air|zone)|^#?\/?$/); });
  }
  function airFor(name) {
    if (!S.air) return null;
    for (var i = 0; i < S.air.places.length; i++) if (S.air.places[i].name === name) return S.air.places[i];
    return null;
  }
  function refreshIf(re) { if (re.test(location.hash || '#/')) route(true); }

  function feedbackHref(z) {
    var u = CFG.feedbackUrl;
    if (!u) return null;
    if (z && CFG.feedbackZoneParam) u += (u.indexOf('?') >= 0 ? '&' : '?') + encodeURIComponent(CFG.feedbackZoneParam) + '=' + encodeURIComponent(z.id + ', near ' + z.place);
    return u;
  }
  function feedbackLink(z) {
    var h = feedbackHref(z);
    if (!h) return '';
    return '<section class="panel"><h3>Was this briefing useful?</h3><p class="small muted">Tell us if it matched what you see on the ground. It takes a minute and helps us check PeatGuard against reality.</p>' +
      '<a class="btn quiet" style="margin-top:12px" href="' + esc(h) + '" target="_blank" rel="noopener">Give feedback</a></section>';
  }
  function alertRule() {
    var M = S.metrics, f = M && M.futureYears;
    return 'An area is called high risk only when its chance of fire stays above the alert line two days in a row. A one-day jump is shown as rising instead.' +
      (f ? ' On years the model never saw, ' + pct0(f.precisionModel) + ' of high-risk calls were followed by a real fire within a week, against ' + pct0(f.precisionRule) + ' for the dry-days rule. The rest were false alarms, so treat high risk as "check this area", not "it is burning".' : '');
  }

  /* ---------------- views ---------------- */
  function item(z) {
    var c = lvl(z.level);
    return '<a class="item" href="#/zone/' + z.id + '"><span class="rk">' + z.rank + '</span>' +
      '<div style="min-width:0"><div class="nm">' + esc(z.id) + '<span class="tag ' + c + '">' + z.level + '</span>' +
      (z.rising ? '<span class="tag elevated">Rising</span>' : '') +
      (assigned[z.id] ? '<span class="tag done">Assigned</span>' : '') + '</div>' +
      '<div class="area">' + esc(area(z)) + '</div>' +
      '<div class="why">' + esc(cap(z.reasons[0] || story(z))) + '</div></div>' +
      '<div class="pc num c-' + c + '">' + pct(z.p) + '<small>chance</small></div>' +
      '<span class="chev">' + ic('chev', null, 2) + '</span></a>';
  }

  function heroLinks() {
    return '<div class="links"><button class="more" data-act="hero" aria-expanded="' + S.heroOpen + '" aria-controls="hero-facts">' +
      (S.heroOpen ? 'Fewer details' : 'More details') + ic('down', null, 2) + '</button>' + how('risk', null, 'How it was calculated', 'on-red') + '</div>';
  }
  function splitLine(burn, fresh) {
    var a = burn + (burn === 1 ? ' is' : ' are') + ' already burning and could spread.';
    var b = fresh ? ' ' + fresh + (fresh === 1 ? ' has' : ' have') + ' no fire yet, which is where early patrols matter most.' : ' None of the quiet areas are at high risk yet.';
    return a + b;
  }
  function vToday() {
    var t = S.today, s = t.summary, hero;
    var hiBurn = t.zones.filter(function (z) { return z.level === 'High' && z.fires7 > 0; }).length;
    var hiNew = t.zones.filter(function (z) { return z.level === 'High' && z.fires7 === 0; }).length;
    var quiet = t.zones.filter(function (z) { return z.fires7 === 0; }).slice(0, 3);
    var burning = t.zones.filter(function (z) { return z.fires7 > 0; }).slice(0, 3);
    if (s.high > 0) {
      hero = '<section class="hero-risk" aria-label="Fire risk today">' +
        '<div class="status"><span class="live"></span>Fire risk today</div>' +
        '<div class="headline"><span class="num">' + s.high + '</span><p>' + (s.high === 1 ? 'area' : 'areas') + ' at high risk of fire this week</p></div>' +
        '<p class="facts" id="hero-facts"' + (S.heroOpen ? '' : ' hidden') + '>' + splitLine(hiBurn, hiNew) + (s.smoke ? ' ' + s.smoke + ' risky areas would push smoke towards Malaysia.' : '') +
        (s.rising ? ' ' + s.rising + ' more crossed the alert line today.' : '') + '</p>' +
        '<div class="row"><a class="btn-light" href="#/patrol">Send teams</a>' + heroLinks() + '</div></section>';
    } else if (s.elevated > 0) {
      hero = '<section class="hero-risk watch" aria-label="Fire watch today">' +
        '<div class="status"><span class="live"></span>Fire watch today</div>' +
        '<div class="headline"><span class="num">' + s.elevated + '</span><p>' + (s.elevated === 1 ? 'area' : 'areas') + ' to watch. None at high risk today</p></div>' +
        '<p class="facts" id="hero-facts"' + (S.heroOpen ? '' : ' hidden') + '>' + s.burning + ' areas are burning now. ' + (s.rising ? s.rising + ' crossed the alert line today; if they stay above it tomorrow they become high risk. ' : '') + 'Patrol the areas below within three days.</p>' +
        '<div class="row"><a class="btn-light" href="#/patrol">See areas to watch</a>' + heroLinks() + '</div></section>';
    } else {
      hero = '<section class="hero-risk calm" aria-label="All clear today">' +
        '<div class="status"><span class="live"></span>All clear today</div>' +
        '<div class="headline"><span class="num">0</span><p>areas at high risk of fire this week</p></div>' +
        '<p class="facts" id="hero-facts"' + (S.heroOpen ? '' : ' hidden') + '>A good week to repair canal blocks and brief communities before the dry season.</p>' +
        '<div class="row"><a class="btn-light" href="#/patrol">See the ranking</a>' + heroLinks() + '</div></section>';
    }
    return '<main class="screen has-nav">' +
      '<header class="masthead"><div class="wordmark"><span class="mark" aria-hidden="true"><svg viewBox="2.6 1.6 18.8 21.4">' + I.logo + '</svg></span>' +
      '<div><b>PeatGuard</b><span>' + esc(updatedLine()) + '</span></div></div>' +
      '<button class="icon-btn" data-act="sheet" data-v="risk" aria-label="How PeatGuard works">' + ic('info') + '</button></header>' +
      hero +
      (quiet.length ? '<section class="stack"><div class="group-head"><h2>Catch it before it starts</h2><a href="#/patrol/new">See more</a></div>' +
        '<p class="small muted" style="margin-top:-4px">No fire here yet. Patrol now to stop one starting.</p>' +
        '<div class="group">' + quiet.map(item).join('') + '</div></section>' : '') +
      (burning.length ? '<section class="stack"><div class="group-head"><h2>Stop it spreading</h2><a href="#/patrol/burning">See more</a></div>' +
        '<p class="small muted" style="margin-top:-4px">Already burning and likely to continue.</p>' +
        '<div class="group">' + burning.map(item).join('') + '</div></section>' : '') +
      '<section class="stack"><div class="group-head"><h2>Air right now</h2><a href="#/air">All places</a></div>' + airStrip() + '</section>' +
      '</main>' + tabs('today');
  }

  function airStrip() {
    if (S.airState === 'failed') return '<div class="group empty">Air quality is unavailable right now.</div>';
    if (!S.air) return '<div class="group empty">Checking the air…</div>';
    return '<div class="air-strip">' + ['Kuala Lumpur', 'Johor Bahru', 'Kuching'].map(function (n) {
      var a = airFor(n);
      if (!a || a.aqi == null) return '<div class="air-chip"><span class="num dim">–</span><span class="p">' + esc(n) + '</span></div>';
      var c = aqiCat(a.aqi);
      return '<a class="air-chip" href="#/air/' + encodeURIComponent(n) + '"><span class="num" style="color:' + c.text + '">' + a.aqi + '</span>' +
        '<span class="c" style="color:' + c.text + '">' + esc(c.i === 2 ? 'Sensitive groups' : c.name) + '</span><span class="p">' + esc(n) + '</span></a>';
    }).join('') + '</div>';
  }

  function patrolZones() {
    var zs = S.today.zones.slice();
    if (S.filter === 'MY' || S.filter === 'ID') zs = zs.filter(function (z) { return z.country === S.filter; });
    if (S.filter === 'new') zs = zs.filter(function (z) { return z.fires7 === 0; });
    if (S.filter === 'burning') zs = zs.filter(function (z) { return z.fires7 > 0; });
    return zs.slice(0, 10);
  }

  function vPatrol() {
    var filters = [['all', 'All'], ['new', 'Not burning yet'], ['burning', 'Burning'], ['MY', 'Malaysia'], ['ID', 'Indonesia']];
    var rows = patrolZones();
    return '<main class="screen has-nav">' +
      topbar(backBtn('#/today'), 'Send teams here first', fmtDate(S.today.asOf, { weekday: 'long', day: 'numeric', month: 'long' }),
        '<button class="icon-btn" data-act="share" aria-label="Share this list">' + ic('share') + '</button>') +
      '<div class="seg" role="group" aria-label="Show">' + filters.map(function (f) {
        return '<button aria-pressed="' + (S.filter === f[0]) + '" data-act="filter" data-v="' + f[0] + '">' + f[1] + '</button>';
      }).join('') + '</div>' +
      (rows.length ? '<div class="group">' + rows.map(item).join('') + '</div>' : '<div class="group empty">No areas match this filter today.</div>') +
      '<p class="tiny dim">Ranked by chance of fire, the people living nearby, and whether smoke would blow towards Malaysia. ' +
      (S.filter === 'new' ? 'Not burning yet means no fire detected here this week.' : '') + '</p>' +
      how('risk') + '</main>' + tabs('today');
  }

  function wtChart(z) {
    var ser = z.series, n = ser.dates.length;
    if (!n) return '';
    var asOf = S.today.asOf, vals = ser.wt.map(function (v) { return v == null ? 0 : v; });
    var maxV = Math.max(60, Math.max.apply(null, vals) + 6);
    var W = 320, H = 96, top = 8, h = 80;
    function x(i) { return (n === 1 ? 0 : i / (n - 1) * W).toFixed(1); }
    function y(v) { return (top + v / maxV * h).toFixed(1); }
    var obs = [], fc = [], last = 0;
    for (var i = 0; i < n; i++) if (ser.dates[i] <= asOf) { obs.push(x(i) + ',' + y(vals[i])); last = i; }
    for (var j = last; j < n; j++) fc.push(x(j) + ',' + y(vals[j]));
    var dy = y(40), now = vals[last], over = now >= 40;
    return '<section class="panel"><h3>How dry the peat is</h3>' +
      '<p class="small muted">Estimated water table, now about <b style="color:var(--text)">' + Math.round(now) + ' cm</b> below the surface. ' +
      (over ? 'That is past the 40 cm line where peat starts to burn easily.' : 'Peat starts to burn easily below 40 cm.') + '</p>' +
      '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Water table over the past 60 days' + (fc.length > 1 ? ' and the next week' : '') + '">' +
      '<rect x="0" y="' + dy + '" width="' + W + '" height="' + (H - dy) + '" fill="#FF6A3D" opacity="0.12"/>' +
      '<line x1="0" y1="' + dy + '" x2="' + W + '" y2="' + dy + '" stroke="#FF6A3D" stroke-dasharray="4 4" stroke-width="1"/>' +
      '<text x="4" y="' + (H - 4) + '" fill="#FF9466" font-size="10" font-family="Schibsted Grotesk, sans-serif">danger zone, deeper than 40 cm</text>' +
      '<polyline points="' + obs.join(' ') + '" fill="none" stroke="#5FD6C8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>' +
      (fc.length > 1 ? '<polyline points="' + fc.join(' ') + '" fill="none" stroke="#A7EDE5" stroke-width="2.5" stroke-dasharray="5 4" stroke-linecap="round"/>' : '') +
      '<circle cx="' + x(last) + '" cy="' + y(now) + '" r="4.5" fill="' + (over ? '#FF9466' : '#5FD6C8') + '"/></svg>' +
      '<div class="tiny dim" style="display:flex;justify-content:space-between;margin-top:4px"><span>60 days ago</span><span>' + (fc.length > 1 ? 'today, then forecast (dashed)' : 'today') + '</span></div></section>';
  }

  function zoneAir(z) {
    if (S.airState === 'failed') return '';
    var a = airFor(z.id);
    if (!a || a.aqi == null) return '<section class="panel"><h3>Air before you go</h3><p class="small muted">Checking the air here…</p></section>';
    var c = aqiCat(a.aqi);
    var peak = a.days && a.days.length > 1 ? Math.max.apply(null, a.days.slice(0, 3).map(function (d) { return d[1]; })) : null;
    return '<section class="panel"><h3>Air before you go</h3><div class="air-mini" style="margin-top:8px"><span class="num" style="color:' + c.text + '">' + a.aqi + '</span>' +
      '<div><b style="color:' + c.text + '">' + esc(c.name) + '</b><span>US AQI now' + (peak != null ? ', up to ' + peak + ' in the next 3 days' : '') + '</span></div></div>' +
      '<p class="advice" style="margin-top:10px">' + esc(c.advice) + '</p>' +
      '<div style="margin-top:10px">' + how('air', null, 'How air quality is measured') + '</div></section>';
  }

  function heroSvg() {
    return '<svg viewBox="0 0 390 252" preserveAspectRatio="xMidYMax slice" aria-hidden="true">' +
      '<circle cx="250" cy="70" r="46" fill="#FF8A4C" opacity="0.22"/><circle cx="250" cy="70" r="24" fill="#FFB27A" opacity="0.38"/>' +
      '<path d="M0 158 Q60 140 120 156 T240 150 T390 146 V252 H0 Z" fill="#2A1710"/>' +
      '<g fill="#1C100B"><path d="M14 190 L26 134 L38 190 Z"/><path d="M44 194 L60 116 L76 194 Z"/><path d="M92 190 L103 142 L114 190 Z"/>' +
      '<path d="M300 194 L312 150 L324 194 Z"/><path d="M335 198 L352 132 L369 198 Z"/><path d="M362 196 L374 146 L386 196 Z"/></g>' +
      '<path d="M0 200 H390 V252 H0 Z" fill="#17120F"/></svg>';
  }

  function vZone(id) {
    var z = zoneById(id);
    if (!z) return vMissing();
    var c = lvl(z.level), on = !!assigned[z.id];
    var reasons = z.reasons.length ? z.reasons : ['No strong warning signs right now'];
    return '<main class="screen flush has-nav">' +
      '<div class="zhero ' + c + '">' + heroSvg() +
      '<div class="bar">' + backBtn('#/patrol') + '<a class="icon-btn" href="#/map/' + z.id + '" aria-label="Show on map">' + ic('map') + '</a></div>' +
      '<div class="info"><div><h1>' + esc(z.id) + '</h1><div class="area">' + esc(area(z)) + '</div>' +
      '<div class="lvl">' + z.level + ' risk' + (z.rising ? ', rising' : '') + ', number ' + z.rank + ' of 71</div></div>' +
      '<div><div class="num c-' + c + '">' + pct(z.p) + '</div><div class="pl">chance of fire<br>in the next 7 days</div></div></div></div>' +
      '<div class="zbody">' +
      '<section class="stack"><h2>' + esc(story(z)) + '</h2><ul class="reasons">' + reasons.map(function (r) { return '<li>' + esc(cap(r)) + '</li>'; }).join('') + '</ul>' +
      (z.smoke && z.level !== 'Low' ? '<p class="smoke-note">Today\'s wind would carry smoke from here towards Malaysia.</p>' : '') +
      (z.rising ? '<p class="small muted">This area crossed the alert line today for the first time. PeatGuard waits for a second day before calling it high risk, to avoid false alarms.</p>' : '') +
      '<div>' + how('zone', z.id) + '</div></section>' +
      '<section class="action' + (z.level === 'Low' ? ' calm' : '') + '"><h3>What to do</h3><p>' + esc(z.action) + '</p></section>' +
      '<div class="pair"><button class="btn ' + (on ? 'done' : 'quiet') + '" data-act="assign" data-v="' + z.id + '" aria-pressed="' + on + '">' + (on ? ic('check', null, 2) + 'Patrol assigned' : 'Assign a patrol') + '</button>' +
      '<a class="btn primary" href="#/warn/' + z.id + '">Warn this area</a></div>' +
      zoneAir(z) + wtChart(z) + feedbackLink(z) +
      '</div></main>' + tabs('today');
  }

  var AUD = [['community', 'Villages and schools'], ['plantation', 'Plantation estates'], ['fire', 'Fire and rescue'], ['gov', 'District office']];
  var ASKS = {
    en: {
      community: 'Do not burn anything outdoors. Report any smoke immediately. If haze arrives, keep windows closed and wear masks.',
      plantation: 'Check canal blocks and water levels, stop all open burning, and put your estate fire team on standby.',
      fire: 'Please send a patrol to this area today and position pumps near the drained peat.',
      gov: 'Please consider an open-burning ban for this area and prepare haze advice for schools and clinics.'
    },
    bm: {
      community: 'Jangan membakar di kawasan terbuka. Laporkan asap dengan segera. Jika jerebu tiba, tutup tingkap dan pakai pelitup muka.',
      plantation: 'Periksa empangan parit dan paras air, hentikan pembakaran terbuka, dan sediakan pasukan bomba ladang.',
      fire: 'Sila hantar rondaan ke kawasan ini hari ini dan letakkan pam berhampiran tanah gambut.',
      gov: 'Sila pertimbangkan larangan pembakaran terbuka dan sediakan nasihat jerebu untuk sekolah dan klinik.'
    }
  };
  var LVL_BM = { High: 'TINGGI', Elevated: 'SEDERHANA', Low: 'RENDAH' };
  function buildMessage(z, who, lang) {
    var reason = z.reasons[0] || '';
    if (lang === 'bm') {
      return 'Amaran kebakaran gambut (PeatGuard)\nKawasan ' + z.id + ', berhampiran ' + z.place + ', ' + regionName(z.region) + '.\n' +
        'Risiko ' + LVL_BM[z.level] + ' kebakaran dalam 7 hari (' + pct(z.p) + ').' + (z.smoke ? ' Asap mungkin bergerak ke arah Malaysia.' : '') + '\n\n' + ASKS.bm[who];
    }
    return 'Peat fire warning (PeatGuard)\nArea ' + z.id + ', near ' + z.place + ', ' + regionName(z.region) + '.\n' +
      cap(z.level.toLowerCase()) + ' risk of fire in the next 7 days (' + pct(z.p) + ' chance). ' + cap(reason) + '.' +
      (z.smoke ? ' Smoke may drift towards Malaysia.' : '') + '\n\n' + ASKS.en[who];
  }

  function vWarn(id) {
    var z = zoneById(id);
    if (!z) return vMissing();
    var W = S.warn;
    if (W.zone !== id) { W.zone = id; W.who = 'community'; W.lang = 'en'; W.text = null; }
    if (W.text === null) W.text = buildMessage(z, W.who, W.lang);
    return '<main class="screen">' +
      topbar(backBtn('#/zone/' + z.id), 'Warn this area', z.id + ', ' + area(z)) +
      '<div class="field"><span>Who are you warning?</span><div class="choice" role="radiogroup" aria-label="Who are you warning?">' +
      AUD.map(function (a) { return '<button role="radio" aria-checked="' + (a[0] === W.who) + '" data-act="who" data-v="' + a[0] + '">' + a[1] + '</button>'; }).join('') + '</div></div>' +
      '<div class="field"><span>Language</span><div class="choice">' +
      '<button aria-pressed="' + (W.lang === 'en') + '" data-act="lang" data-v="en">English</button>' +
      '<button aria-pressed="' + (W.lang === 'bm') + '" data-act="lang" data-v="bm">Bahasa Melayu</button></div></div>' +
      '<label class="field"><span>Message (you can edit it)</span><textarea class="msg" id="msg">' + esc(W.text) + '</textarea></label>' +
      '<button class="btn primary" data-act="send" data-v="whatsapp">' + ic('chat', null, 2) + 'Send on WhatsApp</button>' +
      '<div class="pair"><button class="btn quiet" data-act="send" data-v="sms">Send as SMS</button><button class="btn line" data-act="copymsg">Copy message</button></div>' +
      '<p class="fine">You choose who receives it. PeatGuard never sends anything on its own.</p></main>';
  }

  function vSent() {
    var L = S.lastSent;
    if (!L) { setTimeout(function () { location.hash = '#/today'; }, 0); return ''; }
    var z = zoneById(L.zone);
    var remaining = S.today.zones.filter(function (h) { return h.level === 'High' && !assigned[h.id] && h.id !== L.zone; });
    var next = remaining[0] || S.today.zones.filter(function (x) { return x.id !== L.zone && !assigned[x.id]; })[0];
    var audLabel = (AUD.filter(function (a) { return a[0] === L.who; })[0] || ['', ''])[1];
    return '<main class="screen" style="min-height:100dvh">' +
      '<div class="done-mark">' + ic('check', '#5FD6C8', 2.2) + '</div>' +
      '<div class="center"><h1>Warning ready to send</h1><p>' + (L.channel === 'Copied' ? 'The message is copied. Paste it wherever you need it.' : 'Your ' + L.channel + ' message is open. Press send there to deliver it.') + '</p></div>' +
      '<div class="facts-list"><div><span>Area</span><b>' + esc(z.id) + ', near ' + esc(z.place) + '</b></div>' +
      '<div><span>For</span><b>' + esc(audLabel) + '</b></div>' +
      '<div><span>Channel</span><b>' + esc(L.channel) + ', ' + (L.lang === 'bm' ? 'Bahasa Melayu' : 'English') + '</b></div>' +
      '<div><span>Time</span><b>' + esc(L.time) + '</b></div></div>' +
      (remaining.length ? '<p class="small muted center">' + remaining.length + ' more high-risk ' + (remaining.length === 1 ? 'area still needs' : 'areas still need') + ' a team today.</p>' : '') +
      '<div class="stack">' + (next ? '<a class="btn primary" href="#/zone/' + next.id + '">Go to the next area</a>' : '') +
      '<a class="btn quiet" href="#/today">Back to today</a></div></main>';
  }

  function vMap(sel) {
    var t = S.today, z = zoneById(sel || S.mapSel) || t.zones[0];
    S.mapSel = z.id;
    var c = lvl(z.level);
    return '<main class="screen has-nav">' +
      topbar(null, 'Risk map', '71 peatland areas in Malaysia and Indonesia') +
      '<label class="search">' + ic('search') + '<span class="sr">Find an area</span>' +
      '<input id="q" type="search" list="zlist" placeholder="Find an area, town or state" autocomplete="off"></label>' +
      '<datalist id="zlist">' + t.zones.map(function (x) { return '<option value="' + x.id + '">' + esc(area(x)) + '</option>'; }).join('') + '</datalist>' +
      '<div class="map-box" id="map" role="application" aria-label="Map of peatland areas coloured by fire risk"></div>' +
      '<div class="legend heat-legend"><span class="heat-scale"><em>Lower risk</em><b></b><em>Higher risk</em></span>' +
      '<span><i class="fire"></i>Burning this week</span></div>' +
      '<a class="selected" href="#/zone/' + z.id + '"><div class="row"><div><h3>' + esc(z.id) + '</h3><div class="small muted">' + esc(area(z)) + '</div></div>' +
      '<div><div class="num c-' + c + '">' + pct(z.p) + '</div><div class="tiny dim" style="text-align:right">chance of fire</div></div></div>' +
      '<p class="small" style="color:var(--text-2)">' + esc(cap(z.reasons[0] || story(z))) + '</p>' +
      '<span class="go">Open the briefing</span></a></main>' + tabs('map');
  }

  var MAP_COLORS = { High: ['#FF6A3D', 0.78], Elevated: ['#F2B046', 0.68], Low: ['#5A4E46', 0.45] };
  function initMap() {
    var el = document.getElementById('map');
    if (!el) return;
    var q = document.getElementById('q');
    if (q) {
      q.addEventListener('change', function () { jumpTo(q.value); });
      q.addEventListener('keydown', function (e) { if (e.key === 'Enter') jumpTo(q.value); });
    }
    if (CFG.googleMapsKey && !CFG.mapboxToken && !initMap.googleFailed) loadGoogle(function (ok) { if (ok) drawGoogle(el); else drawLeaflet(el); });
    else drawLeaflet(el);
  }
  function loadGoogle(cb) {
    if (window.google && window.google.maps) return cb(true);
    if (loadGoogle.waiting) { loadGoogle.waiting.push(cb); return; }
    loadGoogle.waiting = [cb];
    window.gm_authFailure = function () { initMap.googleFailed = true; toast('Google Maps key was refused, showing the free map'); refreshIf(/^#\/map/); };
    window.pgGoogleReady = function () { var w = loadGoogle.waiting; loadGoogle.waiting = null; w.forEach(function (f) { f(true); }); };
    var s = document.createElement('script');
    s.src = 'https://maps.googleapis.com/maps/api/js?key=' + encodeURIComponent(CFG.googleMapsKey) + '&callback=pgGoogleReady&v=weekly';
    s.async = true;
    s.onerror = function () { initMap.googleFailed = true; var w = loadGoogle.waiting; loadGoogle.waiting = null; w.forEach(function (f) { f(false); }); };
    document.head.appendChild(s);
  }
  var GSTYLE = [
    { elementType: 'geometry', stylers: [{ color: '#211A16' }] },
    { elementType: 'labels.text.fill', stylers: [{ color: '#B9ADA4' }] },
    { elementType: 'labels.text.stroke', stylers: [{ color: '#17120F' }] },
    { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#12191C' }] },
    { featureType: 'road', stylers: [{ visibility: 'simplified' }, { lightness: -55 }] },
    { featureType: 'poi', stylers: [{ visibility: 'off' }] },
    { featureType: 'transit', stylers: [{ visibility: 'off' }] },
    { featureType: 'administrative.country', elementType: 'geometry.stroke', stylers: [{ color: '#6B5D53' }] }
  ];
  function drawGoogle(el) {
    var g = window.google.maps;
    gmap = new g.Map(el, { center: { lat: 0.6, lng: 107.5 }, zoom: 5, styles: GSTYLE, disableDefaultUI: true, zoomControl: true, gestureHandling: 'greedy', backgroundColor: '#1B1512' });
    var bounds = new g.LatLngBounds();
    S.today.zones.forEach(function (z) {
      var col = MAP_COLORS[z.level], sel = z.id === S.mapSel;
      var b = { north: z.lat + 0.25, south: z.lat - 0.25, east: z.lon + 0.25, west: z.lon - 0.25 };
      bounds.extend({ lat: b.north, lng: b.east }); bounds.extend({ lat: b.south, lng: b.west });
      var r = new g.Rectangle({ map: gmap, bounds: b, fillColor: col[0], fillOpacity: col[1], strokeColor: sel ? '#FFFFFF' : '#17120F', strokeWeight: sel ? 2.5 : 1 });
      r.addListener('click', function () { location.hash = '#/map/' + z.id; });
      if (z.fires7 > 0) new g.Circle({ map: gmap, center: { lat: z.lat, lng: z.lon }, radius: 5000 + 900 * Math.sqrt(z.fires7), fillColor: '#FFD08A', fillOpacity: 0.95, strokeColor: '#FF8A4C', strokeWeight: 2, clickable: false });
    });
    gmap.fitBounds(bounds, 8);
  }
  function drawLeaflet(el) {
    if (typeof L === 'undefined') { el.innerHTML = '<div class="empty">The map could not load. Check your connection.</div>'; return; }
    if (leafletMap) { leafletMap.remove(); leafletMap = null; }
    leafletMap = L.map(el, { zoomControl: true, scrollWheelZoom: false });
    if (CFG.mapboxToken) {
      L.tileLayer('https://api.mapbox.com/styles/v1/mapbox/' + (CFG.mapboxStyle || 'dark-v11') + '/tiles/512/{z}/{x}/{y}@2x?access_token=' + encodeURIComponent(CFG.mapboxToken), {
        tileSize: 512, zoomOffset: -1, maxZoom: 12,
        attribution: '&copy; <a href="https://www.mapbox.com/about/maps/" target="_blank" rel="noopener">Mapbox</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>'
      }).addTo(leafletMap);
    } else {
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', { subdomains: 'abcd', maxZoom: 10, attribution: '&copy; OpenStreetMap &copy; CARTO' }).addTo(leafletMap);
    }
    var zones = S.today.zones, bounds = [];
    zones.forEach(function (z) { bounds.push([z.lat - 0.25, z.lon - 0.25], [z.lat + 0.25, z.lon + 0.25]); });
    leafletMap.fitBounds(bounds, { padding: [8, 8] });

    // Risk heat layer: one soft blob per zone, sized to the zone so neighbours blend.
    if (L.heatLayer) {
      var pts = zones.map(function (z) { return [z.lat, z.lon, heatValue(z, zones)]; });
      var heat = L.heatLayer(pts, { max: 1, maxZoom: 0, minOpacity: 0.05, gradient: HEAT_GRADIENT }).addTo(leafletMap);
      var fit = function () {
        var a = leafletMap.latLngToContainerPoint([0, 100]), b = leafletMap.latLngToContainerPoint([0, 100.5]);
        var cell = Math.abs(b.x - a.x);
        heat.setOptions({ radius: Math.max(9, cell * 1.05), blur: Math.max(10, cell * 1.1) });
      };
      fit(); leafletMap.on('zoomend', fit);
    }

    // Burning this week: small glowing embers on top of the heat.
    zones.forEach(function (z) {
      if (z.fires7 > 0) L.marker([z.lat, z.lon], {
        icon: L.divIcon({ className: 'ember' + (z.fires7 >= 10 ? ' big' : ''), html: '<i></i>', iconSize: [10, 10] }),
        interactive: false, keyboard: false
      }).addTo(leafletMap);
    });

    // Invisible tap areas (one per zone); the selected zone gets a white outline.
    zones.forEach(function (z) {
      var b = [[z.lat - 0.25, z.lon - 0.25], [z.lat + 0.25, z.lon + 0.25]], sel = z.id === S.mapSel;
      var r = L.rectangle(b, { stroke: sel, color: '#FFFFFF', weight: 2, dashArray: sel ? null : '3 4', fillColor: '#FFFFFF', fillOpacity: 0 }).addTo(leafletMap);
      r.bindTooltip(z.id + ', near ' + z.place + ': ' + pct(z.p), { direction: 'top' });
      r.on('click', function () { location.hash = '#/map/' + z.id; });
      if (!sel) {
        r.on('mouseover', function () { r.setStyle({ stroke: true, opacity: 0.5, weight: 1 }); });
        r.on('mouseout', function () { r.setStyle({ stroke: false }); });
      }
    });
  }
  // Warm "fire" ramp: transparent -> ember red -> orange -> hot yellow-white.
  var HEAT_GRADIENT = { 0.22: '#5A1E14', 0.38: '#7A2416', 0.52: '#C2401E', 0.68: '#FF6A3D', 0.84: '#FFA94D', 1: '#FFF0B3' };
  // Heat strength follows the risk level first (so a quiet High zone still glows), then the chance within that level.
  function heatValue(z, zones) {
    var band = { High: [0.72, 1], Elevated: [0.45, 0.64], Low: [0, 0.22] }[z.level] || [0, 0.22];
    var same = zones.filter(function (x) { return x.level === z.level; }).map(function (x) { return x.p; });
    var lo = Math.min.apply(null, same), hi = Math.max.apply(null, same);
    var f = hi > lo ? (z.p - lo) / (hi - lo) : 1;
    return band[0] + (band[1] - band[0]) * f;
  }
  function jumpTo(v) {
    v = (v || '').trim().toLowerCase();
    if (!v) return;
    var zs = S.today.zones;
    var hit = zs.filter(function (z) { return z.id.toLowerCase() === v; })[0] ||
      zs.filter(function (z) { return (z.id + ' ' + z.place + ' ' + z.region).toLowerCase().indexOf(v) >= 0; })[0];
    if (hit) location.hash = '#/map/' + hit.id; else toast('No area matches "' + v + '"');
  }

  function vAir(sel) {
    if (sel) S.airSel = sel;
    var head = topbar(null, 'Air quality', S.air ? (S.air.live ? 'Live, ' : 'As of ') + fmtTime(S.air.generatedAt) : 'Haze and smoke near you');
    if (S.airState === 'failed') return '<main class="screen has-nav">' + head + '<div class="group empty">Air quality is unavailable right now. Try again later.</div></main>' + tabs('air');
    if (!S.air) return '<main class="screen has-nav">' + head + '<div class="group empty">Checking the air…</div></main>' + tabs('air');
    var cities = S.air.places.filter(function (p) { return p.kind === 'city' && p.aqi != null; });
    var zonesA = S.air.places.filter(function (p) { return p.kind === 'zone' && p.aqi != null; });
    var a = airFor(S.airSel) || cities[0];
    var c = aqiCat(a.aqi);
    var dayNames = ['Today', 'Tomorrow'];
    var days = (a.days || []).slice(0, 3).map(function (d, k) {
      var dc = aqiCat(d[1]);
      return '<div><span>' + (dayNames[k] || fmtDate(d[0], { weekday: 'long' })) + '</span><b style="color:' + dc.text + '">' + d[1] + '</b><span>' + esc(dc.i === 2 ? 'Sensitive groups' : dc.name) + '</span></div>';
    }).join('');
    function opt(p) { return '<option value="' + esc(p.name) + '"' + (p.name === a.name ? ' selected' : '') + '>' + esc(p.name === p.area ? p.name : p.name + ', ' + p.area) + '</option>'; }
    var ranked = cities.slice().sort(function (x, y) { return S.airSort === 'best' ? x.aqi - y.aqi : y.aqi - x.aqi; });
    return '<main class="screen has-nav">' + head +
      '<div class="picker"><label for="airsel">Place</label><select id="airsel">' +
      '<optgroup label="Towns and cities">' + cities.map(opt).join('') + '</optgroup>' +
      '<optgroup label="Fire-risk areas">' + zonesA.map(opt).join('') + '</optgroup></select></div>' +
      '<section class="aqi-hero"><div class="top"><span class="num" style="color:' + c.text + '">' + a.aqi + '</span><span class="cat" style="color:' + c.text + '">' + esc(c.name) + '</span></div>' +
      '<p class="where">US AQI in ' + esc(a.name) + (a.pm25 != null ? '. Fine particles (PM2.5): ' + Math.round(a.pm25) + ' µg/m³' : '') + '</p>' +
      '<div class="scale" role="img" aria-label="Scale from good to hazardous; this reading is ' + esc(c.name) + '"><i style="left:' + scalePos(a.aqi).toFixed(1) + '%"></i></div>' +
      '<div class="scale-labels"><span>Good</span><span>Hazardous</span></div>' +
      '<p class="advice">' + esc(c.advice) + '</p>' +
      (days ? '<div class="days">' + days + '</div>' : '') +
      '<div>' + how('air', null, 'How this is measured') + '</div></section>' +
      '<section class="stack"><div class="group-head"><h2>Towns and cities</h2></div>' +
      '<div class="seg small" role="group" aria-label="Sort">' +
      '<button aria-pressed="' + (S.airSort === 'worst') + '" data-act="airsort" data-v="worst">Worst air first</button>' +
      '<button aria-pressed="' + (S.airSort === 'best') + '" data-act="airsort" data-v="best">Cleanest air first</button></div>' +
      '<div class="group">' +
      ranked.map(function (p) {
        var pc = aqiCat(p.aqi);
        return '<a class="item plain" href="#/air/' + encodeURIComponent(p.name) + '"><div><div class="nm"><span class="dot" style="background:' + pc.color + '"></span>' + esc(p.name) + '</div>' +
          '<div class="area" style="padding-left:18px">' + esc(p.area) + '</div></div>' +
          '<div class="pc num" style="color:' + pc.text + '">' + p.aqi + '<small>' + esc(pc.i === 2 ? 'Sensitive' : pc.name) + '</small></div><span class="chev">' + ic('chev', null, 2) + '</span></a>';
      }).join('') + '</div></section></main>' + tabs('air');
  }

  function vEvidence() {
    var M = S.metrics, f = M && M.futureYears;
    return '<main class="screen has-nav">' + topbar(null, 'Evidence', 'Why you can rely on the ranking') +
      (f ? '<a class="panel" href="#/proof" style="text-decoration:none;color:inherit;display:block"><div class="big-stat"><span class="num">+' + lift(f.model, f.rule) + '%</span><b>more fires caught</b></div>' +
        '<p class="stat-note">With the same ' + M.patrols + ' patrols a day, tested on ' + M.testStart.slice(0, 4) + ' to 2026, years the model never saw. See the full results.</p></a>' : '') +
      (S.impact ? '<a class="panel" href="#/impact" style="text-decoration:none;color:inherit;display:block"><div class="big-stat"><span class="num teal">' + S.impact.ruleNeeded + '</span><b>patrols a day</b></div>' +
        '<p class="stat-note">is what today\'s rule of thumb would need to match PeatGuard with ' + S.impact.patrols + '. That is about ' +
        S.impact.extraPatrolDaysPerYear.toLocaleString('en-GB') + ' extra patrol days, or ' + rm(S.impact.extraPatrolDaysPerYear * S.impactCost) + ' a year at RM ' + S.impactCost + ' per team-day.</p></a>' : '') +
      '<div class="group">' +
      ['Does it work?|#/proof|Results against today\'s rule of thumb and random patrols',
        'Replay a past day|#/replay|See what it would have flagged before real fires',
        'How PeatGuard works|#/method|The data, the model, how it was tested, and its limits',
        'What it could save|#/impact|Patrol days, forest and carbon, with the assumptions shown',
        'Ground sensors|#/sensors|What changes when sensors sit in the peat (demo)'].map(function (s) {
        var p = s.split('|');
        return '<a class="item plain" href="' + p[1] + '"><div><div class="nm">' + esc(p[0]) + '</div><div class="area">' + esc(p[2]) + '</div></div><span></span><span class="chev">' + ic('chev', null, 2) + '</span></a>';
      }).join('') + '</div>' +
      (feedbackHref() ? '<a class="btn quiet" href="' + esc(feedbackHref()) + '" target="_blank" rel="noopener">Tell us what you think</a>' : '') +
      '</main>' + tabs('evidence');
  }

  function vProof() {
    var M = S.metrics;
    if (!M) return vMissing();
    var f = M.futureYears, u = M.unseenCountry;
    return '<main class="screen has-nav">' + topbar(backBtn('#/evidence'), 'Does it work?') +
      '<p class="muted">We trained PeatGuard on ' + M.trainStart.slice(0, 4) + ' to ' + (Number(M.testStart.slice(0, 4)) - 1) + ', then tested it once on ' + M.testStart.slice(0, 4) +
      ' to 2026. Each day it picked ' + M.patrols + ' areas to patrol. We compared that with the rule officers use today (send teams where it has been dry longest) and with random picks.</p>' +
      '<section class="panel"><div class="big-stat"><span class="num">+' + lift(f.model, f.rule) + '%</span><b>more fires caught</b></div>' +
      '<p class="stat-note">PeatGuard\'s ' + M.patrols + ' areas caught ' + pct0(f.model) + ' of the fires that followed. The dry-days rule caught ' + pct0(f.rule) + ', random picks ' + pct0(f.random) + '.</p></section>' +
      '<section class="panel"><div class="big-stat"><span class="num">+' + lift(f.newModel, f.newRule) + '%</span><b>more new fires caught</b></div>' +
      '<p class="stat-note">In areas with no fire that week, the hardest case to predict: ' + pct0(f.newModel) + ' against ' + pct0(f.newRule) + '.</p></section>' +
      '<section class="panel"><div class="big-stat"><span class="num teal">' + pct0(u.newModel) + '</span><b>in a country it never saw</b></div>' +
      '<p class="stat-note">A copy trained only on Indonesia still caught ' + pct0(u.newModel) + ' of new fires in Malaysia. The rule caught ' + pct0(u.newRule) + '.</p></section>' +
      '<div class="kv"><div><span>Alerts that turned out real</span><b>' + pct0(f.precisionModel) + ' (rule ' + pct0(f.precisionRule) + ')</b></div>' +
      '<div><span>Ranking accuracy (AUC)</span><b>' + f.rocModel.toFixed(2) + ' (rule ' + f.rocRule.toFixed(2) + ')</b></div>' +
      '<div><span>Area-days tested</span><b>' + f.rows.toLocaleString('en-GB') + '</b></div></div>' +
      '<p class="small muted">It leans most on: ' + esc(M.drivers.join(', ').toLowerCase()) + '.</p>' +
      '<p class="small muted">' + esc(alertRule()) + '</p>' +
      '<div class="pair"><a class="btn quiet" href="#/impact">What it could save</a><a class="btn quiet" href="#/method">How it works</a></div></main>' + tabs('evidence');
  }

  function impactCurve(I) {
    var n = Math.min(30, I.curve.model.length), W = 320, H = 150, L = 38, B = 22, T = 8;
    function x(i) { return (L + (i - 1) / (n - 1) * (W - L - 6)).toFixed(1); }
    function y(v) { return (T + (1 - v) * (H - T - B)).toFixed(1); }
    function line(arr) { var o = []; for (var i = 1; i <= n; i++) o.push(x(i) + ',' + y(arr[i - 1])); return o.join(' '); }
    var p10 = I.curve.model[I.patrols - 1], rn = Math.min(I.ruleNeeded, n);
    return '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Share of fires caught as the number of daily patrols grows, for PeatGuard and the dry-days rule">' +
      [0, 0.5, 1].map(function (g) { return '<line x1="' + L + '" x2="' + W + '" y1="' + y(g) + '" y2="' + y(g) + '" stroke="#3A2F28"/><text x="' + (L - 6) + '" y="' + (Number(y(g)) + 4) + '" text-anchor="end" fill="#95897F" font-size="10">' + Math.round(g * 100) + '%</text>'; }).join('') +
      '<polyline points="' + line(I.curve.rule) + '" fill="none" stroke="#8A7F77" stroke-width="2.5"/>' +
      '<polyline points="' + line(I.curve.model) + '" fill="none" stroke="#FF6A3D" stroke-width="2.5"/>' +
      '<line x1="' + x(I.patrols) + '" x2="' + x(rn) + '" y1="' + y(p10) + '" y2="' + y(p10) + '" stroke="#F3EDE8" stroke-dasharray="3 3"/>' +
      '<circle cx="' + x(I.patrols) + '" cy="' + y(p10) + '" r="4" fill="#FF6A3D"/><circle cx="' + x(rn) + '" cy="' + y(p10) + '" r="4" fill="#8A7F77"/>' +
      '<text x="' + x(1) + '" y="' + (H - 6) + '" fill="#95897F" font-size="10">1 patrol</text><text x="' + x(n) + '" y="' + (H - 6) + '" text-anchor="end" fill="#95897F" font-size="10">' + n + ' patrols a day</text></svg>' +
      '<div class="legend" style="margin-top:6px"><span><i style="background:#FF6A3D"></i>PeatGuard</span><span><i style="background:#8A7F77"></i>Dry-days rule</span></div>';
  }
  function impactNumbers() {
    var I = S.impact, extra = I.usefulVisitsPerYear.extra;
    var stopped = extra * S.impactShare / 100, ha = stopped * S.impactHa;
    var lo = ha * I.co2PerHa[0], hi = ha * I.co2PerHa[1];
    function k(v) { return v >= 1e6 ? (v / 1e6).toFixed(1) + ' million' : v >= 1e4 ? Math.round(v / 1e3) + ',000' : Math.round(v).toLocaleString('en-GB'); }
    return { stopped: stopped, ha: ha, lo: lo, hi: hi, txt: {
      stopped: (Math.round(stopped * 10) / 10).toLocaleString('en-GB'), ha: k(ha), co2: k(lo) + ' to ' + k(hi), cars: k(lo / 4.6) + ' to ' + k(hi / 4.6) } };
  }
  function rm(v) {
    return v >= 1e6 ? 'RM ' + (v / 1e6).toFixed(1) + ' million' : 'RM ' + Math.round(v).toLocaleString('en-GB');
  }
  function vImpact() {
    var I = S.impact;
    var head = topbar(backBtn('#/evidence'), 'What it could save', 'Measured first, then estimated');
    if (!I) return '<main class="screen has-nav">' + head + '<div class="group empty">' + (ensureImpact.failed ? 'Impact data is not available yet. Run the export in the Codespace.' : 'Loading…') + '</div></main>' + tabs('evidence');
    var N = impactNumbers();
    return '<main class="screen has-nav">' + head +
      '<p class="muted">The first two numbers are measured on ' + fmtDate(I.testStart, { year: 'numeric', month: 'short' }) + ' to ' + fmtDate(I.testEnd, { year: 'numeric', month: 'short' }) +
      ', days the model never saw. The rest depends on assumptions you can change.</p>' +
      '<section class="panel"><div class="big-stat"><span class="num">' + I.ruleNeeded + '</span><b>patrols a day</b></div>' +
      '<p class="stat-note">is what the dry-days rule would need to catch as many fires as PeatGuard does with ' + I.patrols + '. That is about ' + I.extraPatrolDaysPerYear.toLocaleString('en-GB') + ' extra patrol days a year for the same result.</p>' +
      impactCurve(I) + '</section>' +
      '<section class="panel"><div class="big-stat"><span class="num">+' + I.usefulVisitsPerYear.extra.toLocaleString('en-GB') + '</span><b>useful visits a year</b></div>' +
      '<p class="stat-note">A useful visit is a patrol sent to an area that went on to burn that week. With ' + I.patrols + ' patrols a day: ' +
      I.usefulVisitsPerYear.model.toLocaleString('en-GB') + ' a year with PeatGuard, ' + I.usefulVisitsPerYear.rule.toLocaleString('en-GB') + ' with the rule.</p></section>' +
      '<section class="stack"><h2>What the saved patrol days are worth</h2>' +
      '<div class="panel stack">' +
      '<label class="field"><span>Cost of one team for one day: <b id="v-cost">RM ' + S.impactCost.toLocaleString('en-GB') + '</b></span><input id="r-cost" type="range" min="100" max="3000" step="50" value="' + S.impactCost + '"></label></div>' +
      '<div class="kv"><div><span>Extra patrol days the rule would need a year</span><b>' + I.extraPatrolDaysPerYear.toLocaleString('en-GB') + '</b></div>' +
      '<div><span>Their cost a year</span><b id="o-cost">' + rm(I.extraPatrolDaysPerYear * S.impactCost) + '</b></div></div>' +
      '<p class="small muted">The patrol days are measured. The daily cost of a team (people, fuel, pumps) is an assumption: set it to your agency\'s real figure.</p></section>' +
      '<section class="stack"><h2>If some of those visits stop a fire early</h2>' +
      '<div class="panel stack">' +
      '<label class="field"><span>Extra visits that stop a fire while it is small: <b id="v-share">' + S.impactShare + '%</b></span><input id="r-share" type="range" min="1" max="30" step="1" value="' + S.impactShare + '"></label>' +
      '<label class="field"><span>Forest saved each time: <b id="v-ha">' + S.impactHa + ' ha</b></span><input id="r-ha" type="range" min="1" max="100" step="1" value="' + S.impactHa + '"></label></div>' +
      '<div class="kv"><div><span>Fires stopped early a year</span><b id="o-stopped">' + N.txt.stopped + '</b></div>' +
      '<div><span>Peat forest saved a year</span><b id="o-ha">' + N.txt.ha + ' ha</b></div>' +
      '<div><span>CO₂ kept out of the air</span><b id="o-co2">' + N.txt.co2 + ' t</b></div>' +
      '<div><span>Same as taking cars off the road</span><b id="o-cars">' + N.txt.cars + '</b></div></div></section>' +
      '<div class="info-note small muted">For scale, the 2015 haze cost Indonesia an estimated US$16 billion (Wan Nawang et al., 2026, Fire Ecology). Where the numbers come from: ' + esc(I.co2Source) + ' A typical car emits about 4.6 tonnes of CO₂ a year (US EPA). The two sliders are our assumptions, not measurements: start low, and only claim what a field pilot confirms.</div>' +
      '</main>' + tabs('evidence');
  }
  function bindImpact() {
    var rs = document.getElementById('r-share'), rh = document.getElementById('r-ha'), rc = document.getElementById('r-cost');
    if (!rs || !rh) return;
    if (rc) rc.addEventListener('input', function () {
      S.impactCost = Number(rc.value);
      document.getElementById('v-cost').textContent = 'RM ' + S.impactCost.toLocaleString('en-GB');
      document.getElementById('o-cost').textContent = rm(S.impactCache * S.impactCost);
    });
    S.impactCache = S.impact.extraPatrolDaysPerYear;
    function upd() {
      S.impactShare = Number(rs.value); S.impactHa = Number(rh.value);
      var N = impactNumbers();
      document.getElementById('v-share').textContent = S.impactShare + '%';
      document.getElementById('v-ha').textContent = S.impactHa + ' ha';
      document.getElementById('o-stopped').textContent = N.txt.stopped;
      document.getElementById('o-ha').textContent = N.txt.ha + ' ha';
      document.getElementById('o-co2').textContent = N.txt.co2 + ' t';
      document.getElementById('o-cars').textContent = N.txt.cars;
    }
    rs.addEventListener('input', upd); rh.addEventListener('input', upd);
  }
  function ensureImpact() {
    if (S.impact || ensureImpact.busy || ensureImpact.failed) return;
    ensureImpact.busy = true;
    getJSON('data/impact.json').then(function (j) { S.impact = j; })
      .catch(function () { ensureImpact.failed = true; })
      .then(function () { ensureImpact.busy = false; refreshIf(/^#\/(impact|evidence)/); });
  }

  function vReplay() {
    var R = S.replay, M = S.metrics;
    var head = topbar(backBtn('#/evidence'), 'Replay a past day', 'Days the model never saw in training');
    if (!R) return '<main class="screen has-nav">' + head + '<div class="group empty">' + (ensureReplay.failed ? 'Replay data is not available.' : 'Loading the replay…') + '</div></main>' + tabs('evidence');
    var byDate = {};
    R.days.forEach(function (d) { byDate[d.d] = d; });
    if (!S.replayDay || !byDate[S.replayDay]) S.replayDay = R.featured[0] || R.days[0].d;
    var cur = byDate[S.replayDay], rnd = cur.b * R.patrols / cur.n;
    function bar(name, v, color) {
      var w = cur.b ? Math.round(v / cur.b * 100) : 0;
      return '<div class="bar-row"><span>' + name + '</span><div class="track"><div class="fill" style="width:' + w + '%;background:' + color + '"></div></div><b>' + (Math.round(v * 10) / 10) + '</b></div>';
    }
    return '<main class="screen has-nav">' + head +
      '<div class="chips-row" role="group" aria-label="Days where PeatGuard did best">' + R.featured.map(function (d) {
        return '<button aria-pressed="' + (d === S.replayDay) + '" data-act="day" data-v="' + d + '">' + esc(fmtDate(d)) + '</button>';
      }).join('') + '</div>' +
      (cur.b > 0 ?
        '<section class="result"><p class="muted small">On ' + esc(fmtDate(cur.d, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })) + ', PeatGuard\'s top ' + R.patrols + ' areas included</p>' +
        '<div><span class="num">' + cur.m + '</span><span class="of"> of ' + cur.b + '</span></div><p>areas that burned in the following week</p></section>' +
        '<section class="panel"><h3>Same ' + R.patrols + ' patrols, three ways</h3><div class="bars" style="margin-top:12px">' +
        bar('PeatGuard', cur.m, '#FF6A3D') + bar('Dry-days rule', cur.r, '#8A7F77') + bar('Random', rnd, '#4A403A') + '</div></section>'
        : '<section class="result"><p class="muted small">' + esc(fmtDate(cur.d, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })) + '</p><p>No areas burned in the week after this day.</p></section>') +
      '<label class="date-pick"><span>Pick any day</span><input type="date" id="rday" min="' + R.days[0].d + '" max="' + R.days[R.days.length - 1].d + '" value="' + cur.d + '"></label>' +
      '<p class="tiny dim">The three days above are where PeatGuard beat both other methods by the widest margin in each test year.</p>' +
      how('replay', null, 'How the replay works') +
      (M ? '<a class="btn quiet" href="#/proof">See results across all test years</a>' : '') + '</main>' + tabs('evidence');
  }

  function vMethod() {
    var t = S.today, M = S.metrics, f = M && M.futureYears;
    return '<main class="screen has-nav">' + topbar(backBtn('#/evidence'), 'How PeatGuard works') +
      '<div class="prose">' +
      '<p>PeatGuard estimates, for each of 71 peatland areas of about 55 by 55 km, the chance that a real fire starts or keeps burning in the next 7 days. It then ranks the areas so a team with limited people knows where to go first.</p>' +
      '<h2>The data it uses</h2></div>' +
      '<div class="src">' +
      '<div><b>Satellite fire detections</b><span>NASA FIRMS, VIIRS satellite, 375 m pixels, since 2015. Live feed checked daily. <a href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" rel="noopener">firms.modaps.eosdis.nasa.gov</a></span></div>' +
      '<div><b>Daily weather history</b><span>NASA POWER: rain, temperature, humidity, wind, 2015 to now. <a href="https://power.larc.nasa.gov/" target="_blank" rel="noopener">power.larc.nasa.gov</a></span></div>' +
      '<div><b>Weather forecast</b><span>Open-Meteo, next 7 days, refreshed with every update. <a href="https://open-meteo.com/" target="_blank" rel="noopener">open-meteo.com</a></span></div>' +
      '<div><b>El Niño and Indian Ocean Dipole</b><span>NOAA monthly climate indices. Both bring dry seasons to Sumatra and Borneo. <a href="https://www.cpc.ncep.noaa.gov/" target="_blank" rel="noopener">cpc.ncep.noaa.gov</a></span></div>' +
      '<div><b>Air quality</b><span>Copernicus CAMS model via Open-Meteo, shown on the US AQI scale. <a href="https://atmosphere.copernicus.eu/" target="_blank" rel="noopener">atmosphere.copernicus.eu</a></span></div></div>' +
      '<div class="prose"><h2>How the data is cleaned</h2><ul>' +
      '<li>Low-confidence satellite detections are removed.</li>' +
      '<li>' + (M && M.staticSources ? M.staticSources + ' fixed heat sources' : 'Fixed heat sources') + ' such as factories and gas flares are removed, because they show up as hot every year.</li>' +
      '<li>An area only counts as burning with 3 or more detections in a week, so a single small burn does not trigger it.</li></ul>' +
      '<h2>The model</h2>' +
      '<p>Two models (gradient-boosted trees, LightGBM) look at ' + (M ? M.featureCount : 'about 30') + ' signals per area per day: rain over the past week to three months, how dry the peat is compared with normal, heat, humidity, wind, the time of year, El Niño, and the area\'s own fire history.</p>' +
      '<ul><li>One model handles areas already burning: will the fire continue or spread?</li>' +
      '<li>The other handles quiet areas: will a new fire start? It cannot rely on "there is already a fire here", so it has to learn the warning signs.</li></ul>' +
      '<p>Every area\'s briefing lists the signals that pushed its score up the most.</p>' +
      '<h2>When it raises an alarm</h2><p>' + esc(alertRule()) + '</p>' +
      '<h2>How the list is ranked</h2><p>Areas are ordered by chance of fire, times a rough weight for how many people live nearby (1 to 3, which we set per region; it is not census data), times 1.5 when today\'s wind would carry the smoke to Malaysia.</p>' +
      '<h2>How we tested it</h2>' +
      '<p>We trained on 2015 to ' + (M ? Number(M.testStart.slice(0, 4)) - 1 : 2022) + ' and tested once on ' + (M ? M.testStart.slice(0, 4) : 2023) + ' to 2026, without changing anything after seeing the results. ' +
      (f ? 'With ' + M.patrols + ' patrols a day it caught ' + pct0(f.model) + ' of fires, against ' + pct0(f.rule) + ' for the dry-days rule and ' + pct0(f.random) + ' for random picks. ' : '') +
      'A second copy trained only on Indonesia was tested on Malaysia, to check it learned general fire behaviour rather than memorising places.</p>' +
      '<h2>What it cannot do</h2><ul>' +
      '<li>Areas are about 55 km wide. It tells you which area to patrol, not which field is burning.</li>' +
      '<li>The water table is estimated from rain and evaporation, not measured. Ground sensors would fix this.</li>' +
      '<li>Satellites miss fires under thick cloud or smoke, and fires smouldering underground.</li>' +
      '<li>It is a decision aid, not an official warning. Follow your local authority.</li></ul>' +
      '<h2>This update</h2></div>' +
      '<div class="kv"><div><span>Calculated</span><b>' + esc(fmtDate(t.generatedAt, { day: 'numeric', month: 'short' })) + ', ' + esc(fmtTime(t.generatedAt)) + '</b></div>' +
      '<div><span>Weather</span><b>' + (t.sources.weather === 'live' ? 'Live forecast' : 'Stored, to ' + esc(t.sources.weatherThrough || '')) + '</b></div>' +
      '<div><span>Satellite fires</span><b>' + (t.sources.fires === 'live' ? 'Live, last 5 days' : 'Stored, to ' + esc(t.sources.firesThrough || '')) + '</b></div></div>' +
      '</main>' + tabs('evidence');
  }

  function vSensors() {
    var t = S.today, z = zoneById(S.sensorZone) || t.zones[0];
    S.sensorZone = z.id;
    var on = S.smoulder, wt = Math.round(Math.max(0, z.wt || 0) + (on ? 3 : 0)), wtAlert = wt > 40;
    function card(name, val, unit, sub, color, alert) {
      return '<div class="sensor' + (alert ? ' alert' : '') + '"><div><div><span class="num" style="color:' + (alert ? '#FF8A70' : color) + '">' + val + '</span><span class="u">' + unit + '</span></div>' +
        '<div class="nm">' + name + '</div><div class="sub">' + sub + '</div></div><span class="state ' + (alert ? 'bad' : 'ok') + '">' + (alert ? 'Alert' : 'Normal') + '</span></div>';
    }
    return '<main class="screen has-nav' + (on ? ' alarm' : '') + '">' +
      topbar(backBtn('#/evidence'), 'Ground sensors', 'Demo with simulated readings') +
      '<div class="picker"><label for="szone">Sensor in</label><select id="szone">' +
      t.zones.map(function (x) { return '<option value="' + x.id + '"' + (x.id === z.id ? ' selected' : '') + '>' + esc(x.id + ', near ' + x.place) + '</option>'; }).join('') + '</select></div>' +
      card('Water table depth', wt, 'cm', 'Alert when deeper than 40 cm', '#5FD6C8', wtAlert) +
      card('Soil temperature, 20 cm down', on ? 56 : 27, '°C', 'Alert above 40 °C', '#F2B046', on) +
      card('Carbon monoxide at ground', on ? 36 : 0.4, 'ppm', 'Alert above 10 ppm', '#DCD2CA', on) +
      (on ? '<div class="callout bad"><b>Fire underground</b>Smouldering found before any satellite could see it. ' + esc(z.id) +
        (z.rank === 1 ? ' is already first on the list and is now marked urgent.' : ' moves from number ' + z.rank + ' to number 1 on the list.') + ' Send a team with deep-water injection equipment now.</div>'
        : '<div class="callout ok"><b>All readings normal</b>' + (wt <= 40 ? 'The water table is ' + (40 - wt) + ' cm short of the 40 cm danger line.' : 'The peat is already past the 40 cm line, so keep a close watch.') + '</div>') +
      '<div class="pair"><button class="btn primary" data-act="smoulder">Simulate a smoulder</button><button class="btn line" data-act="reset">Reset</button></div>' +
      '<p class="fine">The water table starts from PeatGuard\'s estimate for this area. The other readings and alert lines are illustrative until a field pilot.</p>' +
      '</main>' + tabs('evidence');
  }

  function vMissing() {
    return '<main class="screen has-nav">' + topbar(backBtn('#/today'), 'Not found') + '<div class="group empty">This page does not exist. <a href="#/today">Go to today</a></div></main>' + tabs('today');
  }

  /* ---------------- sheets: "how this was calculated" ---------------- */
  function sheetHtml(kind, arg) {
    var t = S.today, M = S.metrics, f = M && M.futureYears;
    var fresh = '<div class="kv"><div><span>Calculated</span><b>' + esc(fmtDate(t.generatedAt, { day: 'numeric', month: 'short' })) + ', ' + esc(fmtTime(t.generatedAt)) + '</b></div>' +
      '<div><span>Weather</span><b>' + (t.sources.weather === 'live' ? 'Live forecast' : 'Stored data') + '</b></div>' +
      '<div><span>Satellite fires</span><b>' + (t.sources.fires === 'live' ? 'Live' : 'Up to ' + esc(t.sources.firesThrough || '')) + '</b></div></div>';
    if (kind === 'zone') {
      var z = zoneById(arg);
      if (!z) return null;
      var model = z.model === 'spread'
        ? 'This area already had fire this week, so the <b>spread model</b> scored it: will the fire keep going or grow?'
        : 'This area had no fire this week, so the <b>new-fire model</b> scored it: will a fire start here?';
      return ['How ' + z.id + ' was scored',
        '<div class="prose"><p>' + model + '</p><p>It compared today\'s conditions here with ' + (M ? M.trainStart.slice(0, 4) + ' to ' + (Number(M.testStart.slice(0, 4)) - 1) : 'past years') +
        ', when we know which areas burned. The result is a ' + pct(z.p) + ' chance of 3 or more fire detections here in the next 7 days, number ' + z.rank + ' of 71.</p>' +
        '<h2>What pushed the score up</h2></div>' +
        (z.drivers && z.drivers.length ? '<div class="kv">' + z.drivers.map(function (d) { return '<div><span>' + esc(d[0]) + '</span><b>' + esc(d[1] || 'yes') + '</b></div>'; }).join('') + '</div>' : '<p class="muted">No single signal stood out.</p>') +
        '<div class="prose"><h2>How often it is wrong</h2><p>' + esc(alertRule()) + '</p><h2>Data used</h2></div>' + fresh +
        (f ? '<p class="small muted" style="margin-top:12px">On years it never saw, PeatGuard\'s top ' + M.patrols + ' areas caught ' + pct0(f.model) + ' of fires, against ' + pct0(f.rule) + ' for the dry-days rule.</p>' : '') +
        '<a class="btn quiet" href="#/method" style="margin-top:14px">Read the full method</a>'];
    }
    if (kind === 'air') {
      return ['How air quality is measured',
        '<div class="prose"><p>Readings come from the Copernicus CAMS atmospheric model, through Open-Meteo, updated every hour for each place. They are shown on the US AQI scale, based mainly on fine particles (PM2.5), the main danger in haze.</p>' +
        '<p>This is a model estimate for the area, not a reading from a ground station, and it is not Malaysia\'s official Air Pollutant Index (API). For official readings, check the Department of Environment\'s <a href="https://eqms.doe.gov.my/APIMS/main" target="_blank" rel="noopener">APIMS</a>.</p>' +
        '<h2>The scale</h2></div><div class="kv">' + AQI.map(function (c, i) {
          var lo = [0, 51, 101, 151, 201, 301][i], hi = [50, 100, 150, 200, 300, 500][i];
          return '<div><span><span class="dot" style="background:' + c[2] + '"></span>' + esc(c[1]) + '</span><b>' + lo + '–' + hi + '</b></div>';
        }).join('') + '</div>' +
        '<p class="small muted" style="margin-top:12px">' + (S.air ? (S.air.live ? 'Fetched live at ' : 'Last saved at ') + esc(fmtTime(S.air.generatedAt)) + '.' : '') + '</p>'];
    }
    if (kind === 'replay') {
      return ['How the replay works',
        '<div class="prose"><p>PeatGuard was trained only on data up to ' + (M ? Number(M.testStart.slice(0, 4)) - 1 : 2022) + '. For every day since, we asked it which ' + (M ? M.patrols : 10) + ' areas to patrol, using only what was known that morning, then checked which areas actually had a fire in the following week.</p>' +
        '<p>The dry-days rule picks the ' + (M ? M.patrols : 10) + ' areas that have gone longest without rain. Random is what ' + (M ? M.patrols : 10) + ' random picks would catch on average.</p>' +
        '<p>The suggested days are the ones where PeatGuard beat both by the widest margin in each year. Use the date picker to check any other day, including bad ones.</p></div>'];
    }
    return ['How today\'s risk was calculated',
      '<div class="prose"><p>Every morning PeatGuard checks 71 peatland areas in Malaysia and Indonesia. For each one it estimates the chance of a real fire (3 or more satellite detections) in the next 7 days, from:</p>' +
      '<ul><li>fires seen by NASA satellites, in the area and nearby</li><li>rain, heat, humidity and wind, past and forecast</li><li>how dry the peat is compared with normal for the season</li><li>El Niño and the Indian Ocean Dipole</li><li>how often the area has burned before</li></ul>' +
      '<h2>How often it is wrong</h2><p>' + esc(alertRule()) + '</p>' +
      '<h2>How the list is ranked</h2><p>By the chance of fire, times a rough weight for how many people live nearby (1 to 3, set by us per region, not census data), times 1.5 if today\'s wind would carry smoke to Malaysia.</p></div>' +
      fresh + '<a class="btn quiet" href="#/method" style="margin-top:14px">Read the full method</a>'];
  }
  function openSheet(kind, arg) {
    var c = sheetHtml(kind, arg);
    if (!c) return;
    lastFocus = document.activeElement;
    sheetRoot.innerHTML = '<div class="scrim"><div class="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title" tabindex="-1">' +
      '<div class="grab"></div><div class="sh"><h2 id="sheet-title">' + esc(c[0]) + '</h2>' +
      '<button class="icon-btn" data-act="close-sheet" aria-label="Close">' + ic('close', null, 2) + '</button></div>' + c[1] + '</div></div>';
    var sh = sheetRoot.querySelector('.sheet');
    sh.focus();
    sh.querySelectorAll('a[href^="#"]').forEach(function (a) { a.addEventListener('click', closeSheet); });
  }
  function closeSheet() { sheetRoot.innerHTML = ''; if (lastFocus && lastFocus.focus) lastFocus.focus(); }
  sheetRoot.addEventListener('click', function (e) {
    if (e.target.classList.contains('scrim') || e.target.closest('.sheet [data-act="close-sheet"]')) closeSheet();
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && sheetRoot.innerHTML) closeSheet(); });

  /* ---------------- router ---------------- */
  function route(keepScroll) {
    if (!S.today) return;
    var parts = (location.hash || '').replace(/^#\/?/, '').split('/');
    var page = parts[0] || 'today', arg = parts[1] ? decodeURIComponent(parts[1]) : null;
    if (page !== 'map') { if (leafletMap) { leafletMap.remove(); leafletMap = null; } gmap = null; }
    var html;
    switch (page) {
      case 'today': case 'home': html = vToday(); ensureAir(); break;
      case 'patrol': if (arg) S.filter = arg; html = vPatrol(); break;
      case 'zone': html = vZone(arg); ensureAir(); break;
      case 'warn': html = vWarn(arg); break;
      case 'sent': html = vSent(); break;
      case 'map': html = vMap(arg); break;
      case 'air': html = vAir(arg); ensureAir(); break;
      case 'evidence': html = vEvidence(); ensureImpact(); break;
      case 'impact': html = vImpact(); ensureImpact(); break;
      case 'proof': html = vProof(); break;
      case 'replay': html = vReplay(); ensureReplay(); break;
      case 'method': html = vMethod(); break;
      case 'sensors': html = vSensors(); break;
      default: html = vMissing();
    }
    var y = window.scrollY;
    app.innerHTML = html;
    if (keepScroll) window.scrollTo(0, y);
    if (page === 'map') initMap();
    if (page === 'impact') bindImpact();
    var el;
    if ((el = document.getElementById('rday'))) el.addEventListener('change', function () { if (el.value) { S.replayDay = el.value; route(true); } });
    if ((el = document.getElementById('szone'))) { var sz = el; sz.addEventListener('change', function () { S.sensorZone = sz.value; S.smoulder = false; route(true); }); }
    if ((el = document.getElementById('airsel'))) { var as = el; as.addEventListener('change', function () { location.hash = '#/air/' + encodeURIComponent(as.value); }); }
    if ((el = document.getElementById('msg'))) { var ta = el; ta.addEventListener('input', function () { S.warn.text = ta.value; }); }
  }
  window.addEventListener('hashchange', function () { closeSheet(); route(); window.scrollTo(0, 0); });

  function ensureReplay() {
    if (S.replay || ensureReplay.busy || ensureReplay.failed) return;
    ensureReplay.busy = true;
    getJSON('data/replay.json').then(function (j) { S.replay = j; })
      .catch(function () { ensureReplay.failed = true; })
      .then(function () { ensureReplay.busy = false; refreshIf(/^#\/replay/); });
  }

  /* ---------------- actions ---------------- */
  app.addEventListener('click', function (e) {
    var el = e.target.closest('[data-act]');
    if (!el) return;
    var act = el.getAttribute('data-act'), v = el.getAttribute('data-v');
    if (act === 'sheet') { openSheet(v, el.getAttribute('data-arg')); return; }
    if (act === 'filter') { S.filter = v; route(true); return; }
    if (act === 'hero') { S.heroOpen = !S.heroOpen; route(true); return; }
    if (act === 'airsort') { S.airSort = v; route(true); return; }
    if (act === 'assign') {
      if (assigned[v]) delete assigned[v]; else assigned[v] = true;
      save('assigned', assigned); route(true); toast(assigned[v] ? 'Patrol assigned' : 'Patrol unassigned'); return;
    }
    if (act === 'who') { S.warn.who = v; S.warn.text = null; route(true); return; }
    if (act === 'lang') { S.warn.lang = v; S.warn.text = null; route(true); return; }
    if (act === 'smoulder') { S.smoulder = true; route(true); return; }
    if (act === 'reset') { S.smoulder = false; route(true); return; }
    if (act === 'day') { S.replayDay = v; route(true); return; }
    if (act === 'retry') { boot(); return; }
    if (act === 'share') {
      var lines = patrolZones().map(function (z) { return z.rank + '. ' + z.id + ', near ' + z.place + ' (' + pct(z.p) + '): ' + (z.reasons[0] || story(z)); });
      var text = 'PeatGuard: send teams here first, ' + fmtDate(S.today.asOf) + '\n' + lines.join('\n');
      if (navigator.share) navigator.share({ title: 'PeatGuard patrol list', text: text }).catch(function () {});
      else copy(text).then(function (ok) { toast(ok ? 'List copied' : 'Could not copy the list'); });
      return;
    }
    if (act === 'copymsg') {
      copy(S.warn.text).then(function (ok) {
        if (!ok) { toast('Could not copy the message'); return; }
        markSent('Copied'); location.hash = '#/sent';
      });
      return;
    }
    if (act === 'send') {
      var msg = encodeURIComponent(S.warn.text || '');
      var url = v === 'whatsapp' ? 'https://wa.me/?text=' + msg : 'sms:?&body=' + msg;
      markSent(v === 'whatsapp' ? 'WhatsApp' : 'SMS');
      window.open(url, v === 'whatsapp' ? '_blank' : '_self');
      location.hash = '#/sent';
    }
  });
  function markSent(channel) {
    var now = new Date().toLocaleTimeString('en-GB', tz({ hour: 'numeric', minute: '2-digit', hour12: true }));
    S.lastSent = { zone: S.warn.zone, who: S.warn.who, lang: S.warn.lang, channel: channel, time: now };
  }

  /* ---------------- boot ---------------- */
  function getJSON(u) {
    return fetch(u, { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error(u + ' (' + r.status + ')'); return r.json(); });
  }
  function boot() {
    app.innerHTML = '<div class="loading"><p>Loading today\'s fire risk…</p></div>';
    Promise.all([getJSON('data/today.json'), getJSON('data/metrics.json').catch(function () { return null; })])
      .then(function (res) {
        S.today = res[0]; S.metrics = res[1];
        if (!S.today.zones || !S.today.zones.length) throw new Error('no areas in the data');
        S.today.zones.forEach(function (z) { if (!z.place) z.place = z.region; if (!z.drivers) z.drivers = []; });
        S.today.zones.sort(function (a, b) { return a.rank - b.rank; });
        route();
      })
      .catch(function (err) {
        app.innerHTML = '<div class="loading"><div><p>Today\'s fire risk could not load.</p><p class="small dim" style="margin:6px 0 16px">' + esc(err.message || String(err)) + '</p>' +
          '<button class="btn primary" data-act="retry">Try again</button></div></div>';
      });
  }
  boot();
})();
