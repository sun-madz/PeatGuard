/* PeatGuard mobile web app.
   Reads data/today.json, data/metrics.json and data/replay.json, written by
   scripts/export_web.py from the trained model. No build step. */
(function () {
  'use strict';

  var S = {
    today: null, metrics: null, replay: null,
    filter: 'all', mapSel: null, replayDay: null,
    alert: { zone: null, who: null, lang: 'en', text: null },
    lastSent: null, smoulder: false, sensorZone: null
  };
  var map = null;
  var app = document.getElementById('app');

  /* ---------------- storage (per-viewer conveniences only) ---------------- */
  function load(key, fallback) {
    try { var v = localStorage.getItem('pg_' + key); return v === null ? fallback : JSON.parse(v); }
    catch (e) { return fallback; }
  }
  function save(key, v) { try { localStorage.setItem('pg_' + key, JSON.stringify(v)); } catch (e) { /* ignore */ } }

  var role = load('role', null);
  var assigned = load('assigned', {});

  /* ---------------- helpers ---------------- */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function pct(p) { var v = Math.round(p * 100); return v < 1 ? '<1%' : v + '%'; }
  function pct0(x) { return Math.round(x * 100) + '%'; }
  function lift(a, b) { return b ? Math.round((a / b - 1) * 100) : 0; }
  function lvlClass(l) { return l === 'High' ? 'high' : l === 'Elevated' ? 'elevated' : 'low'; }
  function zoneById(id) {
    if (!S.today) return null;
    for (var i = 0; i < S.today.zones.length; i++) if (S.today.zones[i].id === id) return S.today.zones[i];
    return null;
  }
  function fmtDate(iso, opts) {
    var d = new Date(iso + (iso.length === 10 ? 'T00:00:00+08:00' : ''));
    return d.toLocaleDateString('en-GB', Object.assign({ timeZone: 'Asia/Kuala_Lumpur' }, opts || { day: 'numeric', month: 'short', year: 'numeric' }));
  }
  function fmtUpdated() {
    var t = S.today;
    var d = new Date(t.generatedAt);
    var time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kuala_Lumpur' });
    var day = d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'Asia/Kuala_Lumpur' });
    return 'Updated ' + time + ' MYT · ' + day;
  }
  function regionShort(r) {
    return r.replace('South Sumatra-Jambi', 'S. Sumatra').replace('Central Kalimantan', 'C. Kalimantan');
  }
  function countryName(c) { return c === 'MY' ? 'Malaysia' : 'Indonesia'; }
  function island(z) {
    var r = z.region;
    if (r === 'Riau' || r === 'South Sumatra-Jambi') return r + ', Sumatra';
    if (r === 'Central Kalimantan') return r + ', Borneo';
    return r + ', ' + countryName(z.country);
  }
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
  function highZones() { return S.today.zones.filter(function (z) { return z.level === 'High'; }); }

  /* ---------------- icons ---------------- */
  var I = {
    flame: '<path d="M12 22c4.4 0 7-2.9 7-6.6 0-3.4-2.2-5.6-3.6-7.2-.4 1.7-1.3 2.9-2.6 3.5.3-3.3-1.2-6.4-4-8.7.2 3.3-1.6 5.1-3 6.8C4.6 11.3 5 13.4 5 15.4 5 19.1 7.6 22 12 22z"/>',
    bell: '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    back: '<path d="M19 12H5M12 19l-7-7 7-7"/>',
    arrow: '<path d="M5 12h14M12 5l7 7-7 7"/>',
    home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/>',
    map: '<path d="m9 4-6 2v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
    list: '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>',
    sensor: '<circle cx="12" cy="12" r="2"/><path d="M16.2 7.8a6 6 0 0 1 0 8.4M7.8 16.2a6 6 0 0 1 0-8.4M19 5a10 10 0 0 1 0 14M5 19A10 10 0 0 1 5 5"/>',
    replay: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
    share: '<path d="M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7"/><path d="M16 6l-4-4-4 4M12 2v14"/>',
    send: '<path d="M3 11l18-8-8 18-2-8z"/>',
    chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    check: '<path d="M20 6 9 17l-5-5"/>'
  };
  function ic(name, color, sw) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="' + (color || 'currentColor') + '" stroke-width="' + (sw || 1.8) +
      '" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + I[name] + '</svg>';
  }
  function logo(big) { return '<div class="logo' + (big ? ' big' : '') + '">' + ic('flame', '#1A0D07', 2) + '</div>'; }
  function backBtn(href, label) { return '<a class="icon-btn" href="' + href + '" aria-label="' + (label || 'Back') + '">' + ic('back') + '</a>'; }
  function topbar(back, title, sub, right) {
    return '<div class="topbar">' + back + '<div class="title"><h1>' + esc(title) + '</h1>' +
      (sub ? '<div class="sub">' + esc(sub) + '</div>' : '') + '</div>' + (right || '<div class="spacer"></div>') + '</div>';
  }
  function nav(active) {
    var items = [['home', '#/home', 'Home'], ['map', '#/map', 'Map'], ['list', '#/patrol', 'Patrol list'], ['sensor', '#/sensors', 'Sensors']];
    return '<nav class="nav" aria-label="Main">' + items.map(function (it) {
      return '<a href="' + it[1] + '" aria-label="' + it[2] + '"' + (active === it[0] ? ' class="on" aria-current="page"' : '') + '>' + ic(it[0]) + '</a>';
    }).join('') + '</nav>';
  }

  /* ---------------- views ---------------- */
  var ROLES = [
    ['fire', 'Fire & rescue officer', 'Daily patrol list and zone briefings'],
    ['plant', 'Plantation fire team', 'Watch the zones around your estates'],
    ['gov', 'Government or agency', 'Warn communities and issue burning bans'],
    ['comm', 'Community member', 'Get haze and fire warnings for your area']
  ];

  function vOnboard() {
    var cur = role || 'fire';
    return '<main class="screen onboard">' +
      '<div style="display:flex;flex-direction:column;gap:14px">' + logo(true) +
      '<h1>Stop peat fires<br>before the haze.</h1>' +
      '<p class="lead" style="font-size:14px">Every morning PeatGuard tells you which peatland areas are most likely to burn this week, why, and what to do.</p></div>' +
      '<div class="muted" style="font-size:13px;font-weight:600">I am a…</div>' +
      '<div role="radiogroup" aria-label="Your role" style="display:flex;flex-direction:column;gap:10px">' +
      ROLES.map(function (r) {
        var on = r[0] === cur;
        return '<button class="role' + (on ? ' on' : '') + '" role="radio" aria-checked="' + on + '" data-act="role" data-v="' + r[0] + '">' +
          '<span class="dot"></span><span><b>' + r[1] + '</b><small>' + r[2] + '</small></span></button>';
      }).join('') + '</div>' +
      '<div class="push"><button class="btn primary tall" data-act="start">Continue</button>' +
      '<div class="note">Uses NASA satellite fire data, weather and El Niño signals</div></div></main>';
  }

  function vHome() {
    var t = S.today, s = t.summary, top = t.zones[0];
    var block;
    if (s.high > 0) {
      block = '<section class="alert-block" aria-label="Fire alert">' +
        '<div class="alert-kicker"><span class="pulse"></span>FIRE ALERT · TODAY</div>' +
        '<div class="alert-count"><span class="n">' + s.high + '</span><span class="t">zone' + (s.high === 1 ? '' : 's') + ' at <b>high risk</b><br>of fire this week</span></div>' +
        '<div class="alert-chips"><span>' + s.smoke + ' would send smoke to Malaysia</span><span>' + s.burning + ' burning now</span></div>' +
        '<a class="btn-white" href="#/patrol">Send teams ' + ic('arrow', null, 2) + '</a></section>';
    } else if (s.elevated > 0) {
      block = '<section class="alert-block quiet" aria-label="Fire watch">' +
        '<div class="alert-kicker"><span class="pulse"></span>FIRE WATCH · TODAY</div>' +
        '<div class="alert-count"><span class="n">' + s.elevated + '</span><span class="t">zone' + (s.elevated === 1 ? '' : 's') + ' to <b>watch</b><br>no high-risk zones today</span></div>' +
        '<div class="alert-chips"><span>' + s.smoke + ' would send smoke to Malaysia</span><span>' + s.burning + ' burning now</span></div>' +
        '<a class="btn-white" href="#/patrol">See zones to watch ' + ic('arrow', null, 2) + '</a></section>';
    } else {
      block = '<section class="alert-block calm" aria-label="All clear">' +
        '<div class="alert-kicker"><span class="pulse"></span>ALL CLEAR · TODAY</div>' +
        '<div class="alert-count"><span class="n">0</span><span class="t">zones at high risk<br>this week</span></div>' +
        '<div class="alert-chips"><span>' + s.burning + ' burning now</span><span>Good time to repair canal blocks</span></div>' +
        '<a class="btn-white" href="#/patrol">See the ranking ' + ic('arrow', null, 2) + '</a></section>';
    }
    return '<main class="screen has-nav">' +
      '<div class="topbar"><a class="brand" href="#/onboard" aria-label="PeatGuard, change your role">' + logo() +
      '<div><div class="name">PeatGuard</div><div class="sub">' + esc(fmtUpdated()) + '</div></div></a>' +
      '<a class="icon-btn square" href="#/patrol" aria-label="Today\'s alerts">' + ic('bell') + '</a></div>' +
      block +
      '<div class="section-head"><h2>Top priority</h2><a href="#/patrol">All 10</a></div>' +
      '<a class="card top-card" href="#/zone/' + top.id + '">' +
      '<div><div class="k">#1 · ' + esc(island(top)) + '</div><div class="z">' + esc(top.id) + '</div></div>' +
      '<div><div class="pct c-' + lvlClass(top.level) + '">' + pct(top.p) + '</div><div class="pl">chance of fire</div></div>' +
      '<div class="why">' + esc(top.reasons[0] || top.category) + '</div></a>' +
      '<div class="tiles">' +
      '<a class="card tile" href="#/map">' + ic('map', '#5FD6C8') + '<div><b>Risk map</b><small>71 zones, MY + ID</small></div></a>' +
      '<a class="card tile" href="#/replay">' + ic('replay', '#F5B342') + '<div><b>Replay</b><small>Did it catch past fires?</small></div></a>' +
      '</div></main>' + nav('home');
  }

  function patrolZones() {
    var zs = S.today.zones.slice();
    if (S.filter === 'MY' || S.filter === 'ID') zs = zs.filter(function (z) { return z.country === S.filter; });
    if (S.filter === 'new') zs = zs.filter(function (z) { return z.fires7 === 0; });
    return zs.slice(0, 10);
  }

  function vPatrol() {
    var t = S.today, s = t.summary;
    var filters = [['all', 'All'], ['MY', 'Malaysia'], ['ID', 'Indonesia'], ['new', 'New fires']];
    var rows = patrolZones();
    return '<main class="screen has-nav">' +
      topbar(backBtn('#/home'), 'Send teams here first', null,
        '<button class="icon-btn" data-act="share" aria-label="Share list">' + ic('share') + '</button>') +
      '<div class="card summary-card"><div><div class="muted" style="font-size:12px">' + esc(fmtDate(t.asOf, { weekday: 'short', day: 'numeric', month: 'short' })) + ' · top 10 of 71 zones</div>' +
      '<div style="display:flex;align-items:baseline;gap:8px;margin-top:6px"><span class="big">' + s.high + '</span><span style="font-size:14px;color:#C8D1D9">high-risk zone' + (s.high === 1 ? '' : 's') + '</span></div></div>' +
      '<div class="side"><span class="tag ember">' + s.smoke + ' smoke → Malaysia</span><span class="tag amber">' + s.elevated + ' elevated</span></div></div>' +
      '<div class="pills" role="group" aria-label="Filter">' + filters.map(function (f) {
        return '<button class="pill round' + (S.filter === f[0] ? ' on' : '') + '" aria-pressed="' + (S.filter === f[0]) + '" data-act="filter" data-v="' + f[0] + '">' + f[1] + '</button>';
      }).join('') + '</div>' +
      '<div class="list">' + (rows.length ? rows.map(function (z) {
        var c = lvlClass(z.level);
        return '<a class="zrow" href="#/zone/' + z.id + '"><div class="rk">#' + z.rank + '</div>' +
          '<div style="min-width:0"><div class="nm"><b>' + esc(z.id) + '</b><span class="lvl c-' + c + '">' + z.level + '</span>' +
          (assigned[z.id] ? '<span class="ok">✓ patrol assigned</span>' : '') + '</div>' +
          '<div class="wy">' + esc(z.reasons[0] || z.category) + '</div></div>' +
          '<div class="pc c-' + c + '">' + pct(z.p) + '</div></a>';
      }).join('') : '<div class="card empty">No zones match this filter today.</div>') + '</div>' +
      '<div class="note">Ranked by chance of fire × people nearby × smoke toward Malaysia</div>' +
      '</main>' + nav('list');
  }

  function wtChart(z) {
    var ser = z.series, n = ser.dates.length;
    if (!n) return '';
    var asOf = S.today.asOf, vals = ser.wt.map(function (v) { return v == null ? 0 : v; });
    var maxV = Math.max(60, Math.max.apply(null, vals) + 6);
    var W = 320, H = 92, top = 6, h = 80;
    function x(i) { return (n === 1 ? 0 : i / (n - 1) * W).toFixed(1); }
    function y(v) { return (top + v / maxV * h).toFixed(1); }
    var obs = [], fc = [], last = 0;
    for (var i = 0; i < n; i++) {
      if (ser.dates[i] <= asOf) { obs.push(x(i) + ',' + y(vals[i])); last = i; }
    }
    for (var j = last; j < n; j++) fc.push(x(j) + ',' + y(vals[j]));
    var dy = y(40), now = vals[last], below = now >= 40;
    return '<div class="card chart-card"><div class="h"><b>Peat water table (estimated)</b><span>past 60 days' + (fc.length > 1 ? ' · dashed = forecast' : '') + '</span></div>' +
      '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Estimated water table ' + Math.round(now) + ' centimetres below the surface; danger line 40 centimetres">' +
      '<rect x="0" y="' + dy + '" width="' + W + '" height="' + (H - dy) + '" fill="#FF6A3D" opacity="0.10"/>' +
      '<line x1="0" y1="' + dy + '" x2="' + W + '" y2="' + dy + '" stroke="#FF6A3D" stroke-dasharray="4 4" stroke-width="1"/>' +
      '<text x="4" y="' + (dy - 4) + '" fill="#FF9F78" font-size="9" font-family="Sora, sans-serif">40 cm danger line</text>' +
      '<polyline points="' + obs.join(' ') + '" fill="none" stroke="#5FD6C8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>' +
      (fc.length > 1 ? '<polyline points="' + fc.join(' ') + '" fill="none" stroke="#A7EDE5" stroke-width="2.5" stroke-dasharray="5 4" stroke-linecap="round"/>' : '') +
      '<circle cx="' + x(last) + '" cy="' + y(now) + '" r="4" fill="' + (below ? '#FF7A4A' : '#5FD6C8') + '"/></svg>' +
      '<div class="muted" style="font-size:11px;padding:2px 0 4px">Now about <b style="color:#EEF2F5">' + Math.round(now) + ' cm</b> below the surface' + (below ? ', past the danger line' : '') + '</div></div>';
  }

  function heroSvg() {
    return '<svg viewBox="0 0 390 236" preserveAspectRatio="xMidYMax slice" aria-hidden="true">' +
      '<circle cx="190" cy="78" r="40" fill="#FF7A3D" opacity="0.28"/><circle cx="190" cy="78" r="22" fill="#FFB27A" opacity="0.40"/>' +
      '<path d="M0 150 Q60 132 120 148 T240 142 T390 138 V236 H0 Z" fill="#1A120E"/>' +
      '<g fill="#0F0B09"><path d="M20 180 L32 124 L44 180 Z"/><path d="M50 184 L66 106 L82 184 Z"/><path d="M95 180 L106 132 L117 180 Z"/>' +
      '<path d="M140 188 L158 112 L176 188 Z"/><path d="M200 184 L212 136 L224 184 Z"/><path d="M245 188 L263 116 L281 188 Z"/>' +
      '<path d="M300 184 L312 140 L324 184 Z"/><path d="M335 188 L352 122 L369 188 Z"/></g>' +
      '<path d="M0 192 H390 V236 H0 Z" fill="#0A0D10"/></svg>';
  }

  function vZone(id) {
    var z = zoneById(id);
    if (!z) return vMissing();
    var c = lvlClass(z.level), on = !!assigned[z.id];
    var reasons = z.reasons.length ? z.reasons : ['No strong warning signs right now.'];
    return '<main class="screen flush">' +
      '<div class="hero ' + c + '">' + heroSvg() +
      '<div class="bar">' + backBtn('#/patrol') + '<a class="icon-btn" href="#/map/' + z.id + '" aria-label="Show on map">' + ic('map') + '</a></div>' +
      '<div class="info"><div class="k">' + esc(island(z)) + ' · priority #' + z.rank + '</div>' +
      '<div class="line"><h1>' + esc(z.id) + '</h1><div><div class="pct c-' + c + '">' + pct(z.p) + '</div><div class="pl">chance of fire · 7 days</div></div></div>' +
      '<div class="chips"><span class="chip ' + c + '">' + z.level.toUpperCase() + ' RISK</span><span class="chip">' + esc(z.category.replace('New fire risk: ', 'New fire: ').replace('Active fire: spread risk', 'Active fire: spreading')) + '</span>' +
      (z.smoke ? '<span class="chip smoke">Smoke → Malaysia</span>' : '') + '</div></div></div>' +
      '<div class="zone-body">' +
      '<div class="why"><h2>Why</h2><ol>' + reasons.map(function (r) { return '<li>' + esc(r.charAt(0).toUpperCase() + r.slice(1)) + '</li>'; }).join('') + '</ol></div>' +
      wtChart(z) +
      '<div class="todo' + (z.level === 'Low' ? ' calm' : '') + '"><div class="k">WHAT TO DO</div><p>' + esc(z.action) + '</p></div>' +
      '<div class="row-2"><button class="btn ' + (on ? 'done' : 'ghost') + '" data-act="assign" data-v="' + z.id + '" aria-pressed="' + on + '">' + (on ? 'Patrol assigned ✓' : 'Assign patrol') + '</button>' +
      '<a class="btn primary" href="#/alert/' + z.id + '">' + ic('send', null, 2) + 'Warn area</a></div>' +
      '</div></main>';
  }

  var AUD = [['community', 'Villages & schools'], ['plantation', 'Plantation estates'], ['fire', 'Fire & rescue'], ['gov', 'District office']];
  var ROLE_AUD = { fire: 'fire', plant: 'plantation', gov: 'gov', comm: 'community' };
  var ASKS = {
    en: {
      community: 'Do not burn anything outdoors. Report any smoke immediately. If haze arrives, keep windows closed and use masks.',
      plantation: 'Check canal blocks and water levels, stop all open burning, and put your estate fire team on standby.',
      fire: 'Send a patrol to this zone today and position pumps near the drained peat.',
      gov: 'Consider an open-burning ban for this area and prepare haze advisories for schools and clinics.'
    },
    bm: {
      community: 'Jangan membakar di kawasan terbuka. Laporkan asap dengan segera. Jika jerebu tiba, tutup tingkap dan pakai pelitup muka.',
      plantation: 'Periksa empangan parit dan paras air, hentikan pembakaran terbuka, dan sediakan pasukan bomba ladang.',
      fire: 'Hantar rondaan ke zon ini hari ini dan letakkan pam berhampiran tanah gambut.',
      gov: 'Pertimbangkan larangan pembakaran terbuka dan sediakan nasihat jerebu untuk sekolah dan klinik.'
    }
  };
  var LVL_BM = { High: 'TINGGI', Elevated: 'SEDERHANA', Low: 'RENDAH' };

  function buildMessage(z, who, lang) {
    var reason = z.reasons[0] || '';
    if (lang === 'bm') {
      return 'AMARAN KEBAKARAN PEATGUARD\nZon ' + z.id + ' (' + z.region + '): risiko ' + LVL_BM[z.level] + ' kebakaran gambut dalam 7 hari (' + pct(z.p) + ').\n' +
        'Data: ' + reason + '.' + (z.smoke ? ' Asap mungkin bergerak ke arah Malaysia.' : '') + '\n\n' + ASKS.bm[who];
    }
    return 'PEATGUARD FIRE WARNING\nZone ' + z.id + ' (' + z.region + '): ' + z.level.toUpperCase() + ' risk of peat fire in the next 7 days (' + pct(z.p) + ' chance).\n' +
      'Why: ' + reason + '.' + (z.smoke ? ' Smoke may drift toward Malaysia.' : '') + '\n\n' + ASKS.en[who];
  }

  function vAlert(id) {
    var z = zoneById(id);
    if (!z) return vMissing();
    var A = S.alert;
    if (A.zone !== id) { A.zone = id; A.who = ROLE_AUD[role] || 'community'; A.lang = 'en'; A.text = null; }
    if (A.text === null) A.text = buildMessage(z, A.who, A.lang);
    return '<main class="screen">' +
      topbar(backBtn('#/zone/' + z.id), 'Warn the area', z.id + ' · ' + regionShort(z.region) + ' · ' + z.level + ' risk') +
      '<div><span class="field-label">Who are you warning?</span><div class="aud-grid" role="radiogroup" aria-label="Audience">' +
      AUD.map(function (a) {
        var on = a[0] === A.who;
        return '<button class="pill' + (on ? ' on' : '') + '" role="radio" aria-checked="' + on + '" data-act="who" data-v="' + a[0] + '">' + a[1] + '</button>';
      }).join('') + '</div></div>' +
      '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><span class="field-label" style="margin:0 4px 0 0">Language</span>' +
      '<button class="pill' + (A.lang === 'en' ? ' on' : '') + '" aria-pressed="' + (A.lang === 'en') + '" data-act="lang" data-v="en">English</button>' +
      '<button class="pill' + (A.lang === 'bm' ? ' on' : '') + '" aria-pressed="' + (A.lang === 'bm') + '" data-act="lang" data-v="bm">Bahasa Melayu</button></div>' +
      '<label><span class="field-label">Message · edit before sending</span><textarea class="msg" id="msg">' + esc(A.text) + '</textarea></label>' +
      '<button class="btn primary tall" data-act="send" data-v="whatsapp">' + ic('chat', null, 2) + 'Send via WhatsApp</button>' +
      '<div class="row-2"><button class="btn ghost short" data-act="send" data-v="sms">SMS</button><button class="btn outline short" data-act="copymsg">Copy text</button></div>' +
      '<div class="note">You choose who receives it. Nothing is sent automatically.</div></main>';
  }

  function vSent() {
    var L = S.lastSent;
    if (!L) { location.hash = '#/home'; return ''; }
    var z = zoneById(L.zone);
    var remaining = highZones().filter(function (h) { return !assigned[h.id] && h.id !== L.zone; });
    var next = remaining[0] || S.today.zones.filter(function (x) { return x.id !== L.zone && !assigned[x.id]; })[0];
    var audLabel = (AUD.filter(function (a) { return a[0] === L.who; })[0] || ['', ''])[1];
    return '<main class="screen" style="min-height:100dvh">' +
      '<div class="done-mark">' + ic('check', '#5FD6C8', 2) + '</div>' +
      '<div class="center"><h1>Warning ready</h1><p>Your ' + (L.channel === 'Copied' ? 'message is copied' : L.channel + ' message opened') + ' for ' + esc(audLabel.toLowerCase()) + ' near ' + esc(z.id) + '.</p></div>' +
      '<div class="card kv"><div><span>Zone</span><b>' + esc(z.id) + ' · ' + esc(regionShort(z.region)) + '</b></div>' +
      '<div><span>Sent to</span><b>' + esc(audLabel) + '</b></div>' +
      '<div><span>Channel</span><b>' + esc(L.channel) + ' · ' + (L.lang === 'bm' ? 'Bahasa Melayu' : 'English') + '</b></div>' +
      '<div><span>Time</span><b>' + esc(L.time) + ' MYT</b></div></div>' +
      (remaining.length ? '<div class="next-note"><b>Next:</b> ' + remaining.length + ' more high-risk zone' + (remaining.length === 1 ? '' : 's') + ' still need a team today.</div>' : '') +
      '<div class="push">' + (next ? '<a class="btn primary tall" href="#/zone/' + next.id + '">Next zone on the list</a>' : '') +
      '<a class="btn ghost" href="#/home">Back to home</a></div></main>';
  }

  function vMap(sel) {
    var t = S.today;
    var z = zoneById(sel || S.mapSel) || t.zones[0];
    S.mapSel = z.id;
    var c = lvlClass(z.level);
    return '<main class="screen has-nav">' +
      topbar(backBtn('#/home'), 'Risk map') +
      '<label class="search">' + ic('search') + '<span class="sr">Search zones</span>' +
      '<input id="q" type="search" list="zlist" placeholder="Search a zone or region" autocomplete="off"></label>' +
      '<datalist id="zlist">' + t.zones.map(function (x) { return '<option value="' + x.id + '">' + esc(x.region) + '</option>'; }).join('') + '</datalist>' +
      '<div class="map-box" id="map" role="application" aria-label="Map of 71 peatland zones coloured by fire risk"></div>' +
      '<div class="legend"><span><i style="background:#FF6A3D"></i>High</span><span><i style="background:#F5B342"></i>Elevated</span>' +
      '<span><i style="background:#3A4752"></i>Low</span><span><i class="dot"></i>Fire this week</span></div>' +
      '<a class="sel-card" href="#/zone/' + z.id + '"><div class="row"><div><div class="muted" style="font-size:12px">Selected · ' + esc(z.region) + '</div>' +
      '<div class="z">' + esc(z.id) + '</div></div><div><div class="pct c-' + c + '">' + pct(z.p) + '</div><div class="muted" style="font-size:11px;text-align:right">fire chance</div></div></div>' +
      '<div style="font-size:13px;color:#D3DAE0">' + esc(z.reasons[0] || z.category) + (z.smoke ? ' · smoke would drift to Malaysia' : '') + '</div>' +
      '<div class="foot"><span>Open zone briefing</span>' + ic('arrow', null, 2) + '</div></a>' +
      '</main>' + nav('map');
  }

  function initMap() {
    var el = document.getElementById('map');
    if (!el || typeof L === 'undefined') return;
    if (map) { map.remove(); map = null; }
    map = L.map(el, { zoomControl: true, attributionControl: true, scrollWheelZoom: false });
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      subdomains: 'abcd', maxZoom: 10,
      attribution: '&copy; OpenStreetMap &copy; CARTO'
    }).addTo(map);
    var colors = { High: ['#FF6A3D', 0.75], Elevated: ['#F5B342', 0.65], Low: ['#3A4752', 0.55] };
    var bounds = [];
    S.today.zones.forEach(function (z) {
      var b = [[z.lat - 0.25, z.lon - 0.25], [z.lat + 0.25, z.lon + 0.25]];
      bounds.push(b[0], b[1]);
      var col = colors[z.level], sel = z.id === S.mapSel;
      var r = L.rectangle(b, { color: sel ? '#FFFFFF' : '#0A0D10', weight: sel ? 2.5 : 1, fillColor: col[0], fillOpacity: col[1] }).addTo(map);
      r.bindTooltip(z.id + ' · ' + pct(z.p), { direction: 'top' });
      r.on('click', function () { S.mapSel = z.id; location.hash = '#/map/' + z.id; });
      if (z.fires7 > 0) {
        L.circleMarker([z.lat, z.lon], { radius: Math.min(7, 3 + Math.sqrt(z.fires7) / 2), color: '#FF8A4C', weight: 2, fillColor: '#FFD08A', fillOpacity: 0.95, interactive: false }).addTo(map);
      }
    });
    map.fitBounds(bounds, { padding: [8, 8] });
    var q = document.getElementById('q');
    if (q) q.addEventListener('change', function () { jumpTo(q.value); });
    if (q) q.addEventListener('keydown', function (e) { if (e.key === 'Enter') jumpTo(q.value); });
  }
  function jumpTo(v) {
    v = (v || '').trim().toLowerCase();
    if (!v) return;
    var hit = S.today.zones.filter(function (z) { return z.id.toLowerCase() === v; })[0] ||
      S.today.zones.filter(function (z) { return z.id.toLowerCase().indexOf(v) >= 0 || z.region.toLowerCase().indexOf(v) >= 0; })[0];
    if (hit) location.hash = '#/map/' + hit.id; else toast('No zone matches "' + v + '"');
  }

  function vReplay() {
    var R = S.replay, M = S.metrics;
    if (!R) return '<main class="screen">' + topbar(backBtn('#/home'), 'Replay a past day') + '<div class="card empty">Loading replay…</div></main>';
    var byDate = {};
    R.days.forEach(function (d) { byDate[d.d] = d; });
    if (!S.replayDay || !byDate[S.replayDay]) S.replayDay = R.featured[0] || R.days[0].d;
    var cur = byDate[S.replayDay];
    var rnd = cur.b * R.patrols / cur.n;
    var chips = R.featured.slice(0, 3);
    function bar(name, v, color) {
      var w = cur.b ? Math.round(v / cur.b * 100) : 0;
      return '<div class="bar-row"><span>' + name + '</span><div class="track"><div class="fill" style="width:' + w + '%;background:' + color + '"></div></div><b>' + (Math.round(v * 10) / 10) + '</b></div>';
    }
    return '<main class="screen">' +
      topbar(backBtn('#/home'), 'Replay a past day', R.days[0].d.slice(0, 4) + '–' + R.days[R.days.length - 1].d.slice(0, 4) + ' · never used in training') +
      '<div class="date-row" role="group" aria-label="Pick a day">' + chips.map(function (d) {
        var on = d === S.replayDay;
        return '<button class="pill' + (on ? ' on' : '') + '" aria-pressed="' + on + '" data-act="day" data-v="' + d + '">' + esc(fmtDate(d)) + '</button>';
      }).join('') + '</div>' +
      (cur.b > 0 ?
        '<div class="card big-result"><div class="muted" style="font-size:13px">On ' + esc(fmtDate(cur.d, { day: 'numeric', month: 'long', year: 'numeric' })) + ', PeatGuard\'s top ' + R.patrols + ' caught</div>' +
        '<div class="n"><b>' + cur.m + '</b><span>of ' + cur.b + '</span></div><div style="font-size:14px;color:#D3DAE0">zones that burned in the next 7 days</div></div>' +
        '<div class="card bars"><h3>Same ' + R.patrols + ' patrols, three ways</h3>' +
        bar('PeatGuard', cur.m, '#FF6A3D') + bar('Dry-days rule', cur.r, '#6B7C8C') + bar('Random', rnd, '#3A4752') + '</div>'
        : '<div class="card big-result"><div class="muted" style="font-size:13px">' + esc(fmtDate(cur.d, { day: 'numeric', month: 'long', year: 'numeric' })) + '</div>' +
        '<div style="font-size:15px;margin-top:6px">No zones burned in the 7 days after this day.</div></div>') +
      '<label class="card date-input"><span>Or pick any day</span><input type="date" id="rday" min="' + R.days[0].d + '" max="' + R.days[R.days.length - 1].d + '" value="' + cur.d + '"></label>' +
      (M ? '<a class="link-card" href="#/proof"><span><b>Across all test years:</b> +' + lift(M.futureYears.model, M.futureYears.rule) + '% more fires caught</span>' + ic('arrow', null, 2) + '</a>' : '') +
      '</main>';
  }

  function vProof() {
    var M = S.metrics;
    if (!M) return vMissing();
    var f = M.futureYears, u = M.unseenCountry;
    return '<main class="screen">' +
      topbar(backBtn('#/replay'), 'Does it work?') +
      '<p class="lead">Tested on ' + M.testStart.slice(0, 4) + '–2026, years it never saw. Same ' + M.patrols + ' patrols a day: PeatGuard\'s list against today\'s rule of thumb.</p>' +
      '<div class="card proof-card"><div class="n"><b>+' + lift(f.model, f.rule) + '%</b><span>more fires caught</span></div>' +
      '<small>' + pct0(f.model) + ' of fires vs ' + pct0(f.rule) + ' with the rule · ' + pct0(f.random) + ' at random</small></div>' +
      '<div class="card proof-card"><div class="n"><b>+' + lift(f.newModel, f.newRule) + '%</b><span>more <i>new</i> fires caught</span></div>' +
      '<small>Fires in quiet zones, before they spread · ' + pct0(f.newModel) + ' vs ' + pct0(f.newRule) + '</small></div>' +
      '<div class="card proof-card"><div class="n"><b class="teal">' + pct0(u.newModel) + '</b><span>in a country it never saw</span></div>' +
      '<small>Trained only on Indonesia, tested on Malaysia · rule: ' + pct0(u.newRule) + '</small></div>' +
      '<div class="info-card"><b>What it looks at most:</b> ' + esc(M.drivers.join(', ').toLowerCase()) + '.</div>' +
      '</main>';
  }

  function vSensors() {
    var t = S.today;
    var z = zoneById(S.sensorZone) || t.zones[0];
    S.sensorZone = z.id;
    var on = S.smoulder;
    var wt = Math.max(0, z.wt || 0);
    var wtNow = Math.round(wt + (on ? 3 : 0));
    var wtAlert = wtNow > 40;
    var others = t.zones.filter(function (x) { return x.id !== z.id; });
    function card(name, val, unit, sub, color, alert) {
      return '<div class="sensor' + (alert ? ' alert' : '') + '"><div><div class="v"><b style="color:' + (alert ? '#FF7A5A' : color) + '">' + val + '</b><span>' + unit + '</span></div>' +
        '<div class="nm">' + name + '</div><div class="sub">' + sub + '</div></div>' +
        '<span class="status' + (alert ? ' on' : '') + '" style="' + (alert ? '' : 'color:' + color) + '">' + (alert ? 'ALERT' : 'OK') + '</span></div>';
    }
    return '<main class="screen has-nav' + (on ? ' alarm' : '') + '" style="min-height:100dvh">' +
      topbar(backBtn('#/home'), 'Ground sensors', 'Node ' + z.id + '-A · every 15 min', '<div class="icon-btn" style="background:transparent;border:none"><span class="live-dot" aria-label="Online"></span></div>') +
      '<label class="card date-input"><span>Sensor zone</span><select id="szone" style="background:#1E242B;color:#EEF2F5;border:1px solid #2E353E;border-radius:10px;padding:8px 10px;font-family:inherit;font-size:13px">' +
      [z].concat(others).map(function (x) { return '<option value="' + x.id + '"' + (x.id === z.id ? ' selected' : '') + '>#' + x.rank + ' · ' + x.id + '</option>'; }).join('') + '</select></label>' +
      card('Water table depth', wtNow, 'cm', 'Alert deeper than 40 cm', '#5FD6C8', wtAlert) +
      card('Soil temperature, 20 cm deep', on ? 56 : 27, '°C', 'Alert above 40 °C', '#F5B342', on) +
      card('Carbon monoxide at ground', on ? 36 : 0.4, 'ppm', 'Alert above 10 ppm', '#C8D1D9', on) +
      (on ? '<div class="sensor-msg bad"><div class="k">Underground fire detected</div><p>Smouldering found before any satellite hotspot. ' + esc(z.id) + (z.rank === 1 ? ' is now confirmed <b>#1</b> and marked urgent.' : ' jumps from #' + z.rank + ' to <b>#1</b> on the patrol list.') + ' Send a team now with deep-water injection equipment.</p></div>'
        : '<div class="sensor-msg ok"><b>All readings normal.</b> ' + (wtNow <= 40 ? 'The water table is ' + Math.max(0, 40 - wtNow) + ' cm short of the 40 cm danger line.' : 'The peat is already past the 40 cm danger line, so watch this zone closely.') + '</div>') +
      '<div class="row-21"><button class="btn primary" data-act="smoulder">Simulate underground smoulder</button><button class="btn outline" data-act="reset">Reset</button></div>' +
      '<div class="note">Simulated readings for the demo. Water table starts from PeatGuard\'s estimate for this zone; alert lines are illustrative.</div>' +
      '</main>' + nav('sensor');
  }

  function vMissing() {
    return '<main class="screen">' + topbar(backBtn('#/home'), 'Not found') + '<div class="card empty">That page does not exist. <a href="#/home">Go home</a></div></main>';
  }
  function vError(msg) {
    return '<div class="loading">' + logo(true) + '<p>Could not load today\'s fire risk.<br><span class="dim">' + esc(msg) + '</span></p>' +
      '<button class="btn primary" data-act="retry" style="width:200px">Try again</button></div>';
  }

  /* ---------------- router ---------------- */
  function route() {
    var parts = (location.hash || '').replace(/^#\/?/, '').split('/');
    var page = parts[0] || '', arg = parts[1] ? decodeURIComponent(parts[1]) : null;
    if (!S.today) return;
    if (!role && page !== 'onboard') { page = 'onboard'; }
    if (page !== 'map' && map) { map.remove(); map = null; }
    var html;
    switch (page) {
      case 'onboard': html = vOnboard(); break;
      case '': case 'home': html = vHome(); break;
      case 'patrol': html = vPatrol(); break;
      case 'zone': html = vZone(arg); break;
      case 'alert': html = vAlert(arg); break;
      case 'sent': html = vSent(); break;
      case 'map': html = vMap(arg); break;
      case 'replay': html = vReplay(); ensureReplay(); break;
      case 'proof': html = vProof(); break;
      case 'sensors': html = vSensors(); break;
      default: html = vMissing();
    }
    app.innerHTML = html;
    if (page === 'map') initMap();
    if (page === 'replay') {
      var rd = document.getElementById('rday');
      if (rd) rd.addEventListener('change', function () { if (rd.value) { S.replayDay = rd.value; route(); } });
    }
    if (page === 'sensors') {
      var sz = document.getElementById('szone');
      if (sz) sz.addEventListener('change', function () { S.sensorZone = sz.value; S.smoulder = false; route(); });
    }
    if (page === 'alert') {
      var ta = document.getElementById('msg');
      if (ta) ta.addEventListener('input', function () { S.alert.text = ta.value; });
    }
  }
  function go() { route(); window.scrollTo(0, 0); }

  function ensureReplay() {
    if (S.replay || ensureReplay.busy) return;
    ensureReplay.busy = true;
    fetch('data/replay.json', { cache: 'no-cache' }).then(function (r) { return r.json(); }).then(function (j) {
      S.replay = j; if (/^#\/replay/.test(location.hash)) route();
    }).catch(function () { app.querySelector('.empty') && (app.querySelector('.empty').textContent = 'Replay data is not available.'); })
      .then(function () { ensureReplay.busy = false; });
  }

  /* ---------------- actions ---------------- */
  app.addEventListener('click', function (e) {
    var el = e.target.closest('[data-act]');
    if (!el) return;
    var act = el.getAttribute('data-act'), v = el.getAttribute('data-v');
    if (act === 'role') { role = v; route(); save('role', v); role = v; return; }
    if (act === 'start') { if (!role) role = 'fire'; save('role', role); location.hash = '#/home'; return; }
    if (act === 'filter') { S.filter = v; route(); return; }
    if (act === 'assign') { if (assigned[v]) delete assigned[v]; else assigned[v] = true; save('assigned', assigned); route(); toast(assigned[v] ? 'Patrol assigned' : 'Assignment removed'); return; }
    if (act === 'who') { S.alert.who = v; S.alert.text = null; route(); return; }
    if (act === 'lang') { S.alert.lang = v; S.alert.text = null; route(); return; }
    if (act === 'smoulder') { S.smoulder = true; route(); return; }
    if (act === 'reset') { S.smoulder = false; route(); return; }
    if (act === 'day') { S.replayDay = v; route(); return; }
    if (act === 'retry') { boot(); return; }
    if (act === 'share') {
      var lines = patrolZones().map(function (z) { return '#' + z.rank + ' ' + z.id + ' (' + z.region + ') ' + pct(z.p) + ' · ' + (z.reasons[0] || z.category); });
      var text = 'PeatGuard patrol list, ' + fmtDate(S.today.asOf) + '\n' + lines.join('\n');
      if (navigator.share) { navigator.share({ title: 'PeatGuard patrol list', text: text }).catch(function () {}); }
      else copy(text).then(function (ok) { toast(ok ? 'Patrol list copied' : 'Could not copy'); });
      return;
    }
    if (act === 'copymsg') {
      copy(S.alert.text).then(function (ok) {
        if (!ok) { toast('Could not copy'); return; }
        markSent('Copied'); location.hash = '#/sent';
      });
      return;
    }
    if (act === 'send') {
      var msg = encodeURIComponent(S.alert.text || '');
      var url = v === 'whatsapp' ? 'https://wa.me/?text=' + msg : 'sms:?&body=' + msg;
      markSent(v === 'whatsapp' ? 'WhatsApp' : 'SMS');
      window.open(url, v === 'whatsapp' ? '_blank' : '_self');
      location.hash = '#/sent';
      return;
    }
  });
  function markSent(channel) {
    var now = new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kuala_Lumpur' });
    S.lastSent = { zone: S.alert.zone, who: S.alert.who, lang: S.alert.lang, channel: channel, time: now };
  }

  window.addEventListener('hashchange', go);

  /* ---------------- boot ---------------- */
  function getJSON(u) {
    return fetch(u, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error(u + ' (' + r.status + ')');
      return r.json();
    });
  }
  function boot() {
    app.innerHTML = '<div class="loading">' + logo(true) + '<p>Loading today\'s fire risk…</p></div>';
    Promise.all([getJSON('data/today.json'), getJSON('data/metrics.json').catch(function () { return null; })])
      .then(function (res) {
        S.today = res[0]; S.metrics = res[1];
        if (!S.today.zones || !S.today.zones.length) throw new Error('no zones in data');
        S.today.zones.sort(function (a, b) { return a.rank - b.rank; });
        if (!location.hash) location.hash = role ? '#/home' : '#/onboard';
        route();
      })
      .catch(function (err) { app.innerHTML = vError(err.message || String(err)); });
  }
  boot();
})();
