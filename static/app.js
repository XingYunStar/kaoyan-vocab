/* ==========================================================================
   考研单词背诵系统 —— 前端逻辑
   ========================================================================== */
(function () {
'use strict';

/* ------------------------------------------------------------- 工具 */
var $  = function (s, r) { return (r || document).querySelector(s); };
var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

function esc(s) {
  s = (s === null || s === undefined) ? '' : String(s);
  return s.split('&').join('&amp;').split('<').join('&lt;')
          .split('>').join('&gt;').split('"').join('&quot;');
}
/* h(tag, attrs, ...children)
   1) 第 3 个及以后的参数依次拼接成内容，漏写加号也不会丢节点；
   2) 非空元素一律输出闭合标签 —— 这一点很关键：像 <i style="width:0%"> 这种
      没闭合的行内标签，会触发 HTML 的「活动格式化元素重建」规则，
      浏览器会把它重新打开到后面每一个块级元素里，把整块内容包进这个
      零宽 <i> 中（音标行就是这么被压成 0 宽的）。 */
var VOID_TAGS = { br: 1, img: 1, input: 1, hr: 1, meta: 1, link: 1, source: 1,
  area: 1, col: 1, embed: 1, track: 1, wbr: 1, path: 1, circle: 1, line: 1,
  polyline: 1, rect: 1, use: 1, stop: 1, ellipse: 1, polygon: 1 };
function h(tag, attrs) {
  var a = '';
  if (attrs) for (var k in attrs) {
    var v = attrs[k];
    if (v === null || v === undefined || v === false) continue;
    if (v === true) { a += ' ' + k; continue; }
    a += ' ' + k + '="' + esc(v) + '"';
  }
  if (VOID_TAGS[tag]) return '<' + tag + a + '>';
  var inner = '';
  for (var i = 2; i < arguments.length; i++) {
    var c = arguments[i];
    if (c === null || c === undefined || c === false) continue;
    inner += c;
  }
  return '<' + tag + a + '>' + inner + '</' + tag + '>';
}
function num(n) { return (n === null || n === undefined) ? '0' : Number(n).toLocaleString('en-US'); }
function pad(n) { return (n < 10 ? '0' : '') + n; }
function todayISO() { var d = new Date(); return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
function addDays(iso, k) {
  var p = iso.split('-'); var d = new Date(+p[0], +p[1] - 1, +p[2]);
  d.setDate(d.getDate() + k); return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
}
function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

function api(path, opts) {
  opts = opts || {};
  var cfg = { headers: { 'Content-Type': 'application/json' } };
  if (opts.body) cfg.body = JSON.stringify(opts.body);
  if (opts.method) cfg.method = opts.method;
  return fetch(path, cfg).then(function (r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  });
}

function toast(msg, ms) {
  var root = $('#toastRoot');
  root.innerHTML = h('div', { class: 'toast' }, esc(msg));
  clearTimeout(toast._t);
  toast._t = setTimeout(function () { root.innerHTML = ''; }, ms || 2200);
}

/* ------------------------------------------------------------- 主题 */
var THEME_KEY = 'kv_theme';
function systemTheme() {
  return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
}
function applyTheme(t) {
  var eff = (t === 'auto') ? systemTheme() : t;
  document.documentElement.setAttribute('data-theme', eff);
  var btn = $('#themeBtn');
  if (btn) {
    // 图标显示的是「当前处于什么模式」，title 显示「点一下会变成什么」
    btn.innerHTML = eff === 'dark'
      ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4.2"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.4 1.4M17.6 17.6L19 19M19 5l-1.4 1.4M6.4 17.6L5 19"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"/></svg>';
    btn.setAttribute('title', eff === 'dark' ? '切换到白昼模式' : '切换到夜间模式');
    btn.setAttribute('aria-label', eff === 'dark' ? '切换到白昼模式' : '切换到夜间模式');
  }
}
function currentTheme() { return localStorage.getItem(THEME_KEY) || 'auto'; }
function toggleTheme() {
  // 只有「白 / 夜」两态。之前是三态循环（白→夜→跟随系统），
  // 当系统恰好是白昼时，「跟随系统 → 白昼」这一步看不出任何变化，
  // 用户以为按钮没反应，于是反复点。现在每次都真的翻转。
  var cur = currentTheme();
  if (cur === 'auto') cur = systemTheme();
  var next = (cur === 'dark') ? 'light' : 'dark';
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
  toast(next === 'dark' ? '夜间模式' : '白昼模式', 1200);
}

/* ------------------------------------------------------------- 发音 */
var voiceCache = [];
function loadVoices() { try { voiceCache = window.speechSynthesis.getVoices() || []; } catch (e) { voiceCache = []; } }
if (window.speechSynthesis) {
  loadVoices();
  window.speechSynthesis.onvoiceschanged = loadVoices;
}
function pickVoice(lang) {
  if (!voiceCache.length) loadVoices();
  var two = lang.slice(0, 2);
  var v = voiceCache.filter(function (x) { return x.lang === lang; })[0]
       || voiceCache.filter(function (x) { return x.lang && x.lang.indexOf(two) === 0; })[0];
  return v || null;
}
function tts(text, lang, rate) {
  if (!window.speechSynthesis) { toast('当前浏览器不支持语音合成'); return; }
  try {
    window.speechSynthesis.cancel();
    var u = new SpeechSynthesisUtterance(text);
    u.lang = lang || 'en-US';
    u.rate = rate || 0.85;
    u.pitch = 1;
    var v = pickVoice(u.lang);
    if (v) u.voice = v;
    window.speechSynthesis.speak(u);
  } catch (e) { /* ignore */ }
}
function playCard(card, which) {
  which = which || 'us';
  var url = which === 'uk' ? card.audio_uk : card.audio_us;
  var lang = which === 'uk' ? 'en-GB' : 'en-US';
  var rate = (S.boot && S.boot.settings.speech_rate) || 0.85;
  if (url && S.preferReal && !S.speechOnly) {
    try {
      var a = new Audio(url);
      a.play().catch(function () { tts(card.word, lang, rate); });
      return;
    } catch (e) { /* fall through */ }
  }
  tts(card.word, lang, rate);
}

/* ------------------------------------------------------------- 状态 */
var S = {
  boot: null, route: 'today', queue: [], idx: 0, revealed: false,
  total: 0, stats: { again: 0, hard: 0, good: 0, easy: 0 },
  startedAt: 0, mode: 'mix', preferReal: true, speechOnly: false,
  browse: { page: 1, q: '', tier: '', status: '' }, enrichQueue: [], enriching: false
};

/* ------------------------------------------------------------- 导航 */
var ROUTES = [
  { id: 'today',    name: '今日',    icon: 'M3 11l9-8 9 8v9a2 2 0 01-2 2h-4v-6H9v6H5a2 2 0 01-2-2z' },
  { id: 'study',    name: '背新词',  icon: 'M4 5a2 2 0 012-2h13v18H6a2 2 0 01-2-2zm3 3h8M7 12h8' },
  { id: 'review',   name: '复习',    icon: 'M20 12a8 8 0 11-2.3-5.6M20 4v5h-5' },
  { id: 'browse',   name: '词库',    icon: 'M4 6h16M4 12h16M4 18h10' },
  { id: 'dash',     name: '仪表板',  icon: 'M4 20V10M10 20V4M16 20v-7M22 20H2' },
  { id: 'settings', name: '设置',    icon: 'M12 15.5A3.5 3.5 0 1112 8.5a3.5 3.5 0 010 7zM19.4 15a1.6 1.6 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.6 1.6 0 00-2.7 1.1V21a2 2 0 11-4 0v-.1A1.6 1.6 0 008.4 19.4l-.1.1a2 2 0 11-2.8-2.8l.1-.1A1.6 1.6 0 004.5 14H4a2 2 0 110-4h.1A1.6 1.6 0 005.6 8.4l-.1-.1a2 2 0 112.8-2.8l.1.1A1.6 1.6 0 0011 4.5V4a2 2 0 114 0v.1a1.6 1.6 0 002.7 1.1l.1-.1a2 2 0 112.8 2.8l-.1.1A1.6 1.6 0 0019.5 11H20a2 2 0 110 4h-.1a1.6 1.6 0 00-1.5 1z' }
];
function renderNav() {
  var due = (S.boot && S.boot.counts.due) || 0;
  $('#nav').innerHTML = ROUTES.map(function (r) {
    var badge = (r.id === 'review' && due > 0) ? h('span', { class: 'badge' }, due > 99 ? '99+' : due) : '';
    return h('button', { class: S.route === r.id ? 'on' : '', 'data-go': r.id },
      h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.8', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, h('path', { d: r.icon })) +
      h('span', null, r.name) + badge);
  }).join('');
}
function go(route) {
  if (route !== S.route && location.hash.slice(1) !== route) {
    try { history.replaceState(null, '', '#' + route); } catch (e) { location.hash = route; }
  }
  S.route = route;
  S.queue = []; S.settled = 0; S.attempts = 0; S.total = 0;
  $('#sidebar').classList.remove('open');
  renderNav();
  if (route === 'today') renderToday();
  else if (route === 'study') startSession('new');
  else if (route === 'review') startSession('review');
  else if (route === 'browse') renderBrowse();
  else if (route === 'dash') renderDash();
  else if (route === 'settings') renderSettings();
}
function setTitle(t, sub) { $('#pageTitle').textContent = t; $('#pageSub').textContent = sub || ''; }

/* ------------------------------------------------------------- 侧栏倒计时 */
function renderSide() {
  if (!S.boot) return;
  var p = S.boot.plan, c = S.boot.counts, s = S.boot.settings;
  var pct = c.selected ? Math.round(c.graduated / c.selected * 100) : 0;
  $('#sideCount').innerHTML =
    h('div', { class: 'big' }, num(p.days_left)) +
    h('div', { class: 'lbl' }, '距 ' + esc(S.boot.exam_name || '考试') + ' 还有 · 天') +
    h('div', { class: 'mini-row' }, h('span', null, '今日需学新词') + h('b', null, num(p.new_per_day))) +
    h('div', { class: 'mini-row' }, h('span', null, '今日待复习') + h('b', null, num(p.due_today))) +
    h('div', { class: 'mini-row' }, h('span', null, '已毕业') + h('b', null, num(c.graduated) + ' / ' + num(c.selected))) +
    h('div', { class: 'mini-bar' }, h('i', { style: 'width:' + pct + '%' }));
}

/* ------------------------------------------------------------- 顶部 */
function renderTop() {
  if (!S.boot) return;
  var t = S.boot.today;
  var done = (t.new_count || 0) + (t.review_count || 0);
  var need = S.boot.plan.daily_load || 0;
  $('#topStats').innerHTML =
    h('span', { class: 'pill ' + (done ? 'done' : '') }, '今日 ' + num(done) + ' / ' + num(need));
}

/* ------------------------------------------------------------- 今日 */
function renderToday() {
  setTitle('今日', S.boot.exam_name + ' · 冲刺计划');
  var p = S.boot.plan, c = S.boot.counts, t = S.boot.today;
  var pct = c.selected ? clamp(Math.round(c.graduated / c.selected * 100), 0, 100) : 0;
  var circ = 2 * Math.PI * 46;
  var done = (t.new_count || 0) + (t.review_count || 0);
  var acc = (t.correct + t.wrong) ? Math.round(t.correct / (t.correct + t.wrong) * 100) : 0;

  var hero = h('div', { class: 'hero' },
    h('div', null,
      h('div', { class: 'days' }, num(p.days_left), h('small', null, '天')) ) +
    h('div', { class: 'plan' },
      planCell('今日新词', p.new_per_day, '词') +
      planCell('今日复习', p.due_today, '张') +
      planCell('今日总量', p.daily_load, '张') +
      planCell('未学单词', p.remaining_new, '词') +
      planCell('待完成轮次', p.rounds_pending, '次') +
      planCell('预计日均轮次', p.rounds_per_day, '次') ) +
    h('div', { class: 'ring' },
      '<svg width="108" height="108" viewBox="0 0 108 108">' +
      '<circle cx="54" cy="54" r="46" fill="none" stroke="var(--bg-soft)" stroke-width="9"/>' +
      '<circle cx="54" cy="54" r="46" fill="none" stroke="var(--accent)" stroke-width="9" stroke-linecap="round" stroke-dasharray="' + circ + '" stroke-dashoffset="' + (circ * (1 - pct / 100)) + '"/>' +
      '</svg>' +
      h('div', { class: 'pct' }, pct + '%') ));

  var stats = h('div', { class: 'grid g4 mt20' },
    statCard('词库总量', num(c.total), '考纲 + 补录词条', '') +
    statCard('已开始学', num(c.learned), '占所选 ' + num(c.selected) + ' 词的 ' + (c.selected ? Math.round(c.learned / c.selected * 100) : 0) + '%', '') +
    statCard('已毕业', num(c.graduated), S.boot.rounds + ' 轮全部完成', 'accent') +
    statCard('今日正确率', acc + '%', '答对 ' + num(t.correct) + ' / 答错 ' + num(t.wrong), acc >= 80 ? 'ok' : 'warn'));

  var actions = h('div', { class: 'grid g3 mt20' },
    card(h('h3', null, '开始背新词') +
      h('p', { class: 'muted', style: 'font-size:13px;margin:0 0 14px' },
        '按词频从高到低推送，每批 ' + (S.boot.settings.batch_size || 20) + ' 词。第 1 轮先认词义。') +
      h('button', { class: 'btn primary', 'data-go': 'study' }, '开始')),
    card(h('h3', null, '到期复习') +
      h('p', { class: 'muted', style: 'font-size:13px;margin:0 0 14px' },
        '按遗忘曲线到期推送，当前有 ' + num(p.due_today) + ' 张待复习。还没到期的会自动留到之后。') +
      h('button', { class: 'btn', 'data-go': 'review' }, '去复习')),
    card(h('h3', null, '浏览词库') +
      h('p', { class: 'muted', style: 'font-size:13px;margin:0 0 14px' },
        '按梯队、状态筛选，或搜索单词与释义，查看音标与助记。') +
      h('button', { class: 'btn', 'data-go': 'browse' }, '打开词库')));

  $('#view').innerHTML = h('div', { class: 'view' }, hero + stats + actions);
}
function planCell(k, v, u) {
  return h('div', null, h('div', { class: 'k' }, k),
    h('div', { class: 'v' }, num(v) + h('em', null, u)));
}
function statCard(k, v, d, cls) {
  return h('div', { class: 'card stat' },
    h('div', { class: 'k' }, k),
    h('div', { class: 'v ' + (cls || '') }, v),
    h('div', { class: 'd' }, d));
}
function card(inner) { return h('div', { class: 'card pad' }, inner); }

/* ------------------------------------------------------------- 学习会话 */
function startSession(mode) {
  S.mode = mode;
  S.queue = []; S.revealed = false;
  S.settled = 0; S.attempts = 0; S.total = 0;
  S.stats = { again: 0, hard: 0, good: 0, easy: 0 };
  setTitle(mode === 'review' ? '复习' : '背新词', '正在取词…');
  $('#view').innerHTML = h('div', { class: 'view' }, h('div', { class: 'empty' }, '加载中…'));
  api('/api/session?mode=' + mode + '&limit=' + ((S.boot && S.boot.settings.batch_size) || 20))
    .then(function (r) {
      S.queue = r.cards || [];
      S.total = S.queue.length;
      S.startedAt = Date.now();
      if (!S.queue.length) { renderEmptySession(mode); return; }
      renderCard();
    })
    .catch(function (e) { $('#view').innerHTML = h('div', { class: 'view' }, h('div', { class: 'empty' }, '加载失败：' + esc(e.message))); });
}

function renderEmptySession(mode) {
  setTitle(mode === 'review' ? '复习' : '背新词', '');
  var msg = mode === 'review'
    ? '当前没有到期的复习卡片，休息一下，或者去背新词。'
    : '你选中的词池已经全部开始学习了，去复习巩固吧。';
  $('#view').innerHTML = h('div', { class: 'view narrow' },
    h('div', { class: 'card pad' }, h('div', { class: 'empty' },
      h('div', { class: 'big' }, '完成'),
      h('p', null, msg),
      h('div', { class: 'row', style: 'justify-content:center;margin-top:16px' },
        h('button', { class: 'btn', 'data-go': 'today' }, '返回今日') +
        h('button', { class: 'btn primary', 'data-go': mode === 'review' ? 'study' : 'review' },
          mode === 'review' ? '去背新词' : '去复习')))));
}

/* 词性释义块：把 ECDICT 的「按词性分组释义」渲染成 词性标签 + 释义 */
function posBlock(card, maxSenses) {
  var list = card && card.pos;
  if (!list || !list.length) return '';
  maxSenses = maxSenses || 4;
  var rows = list.map(function (g) {
    var senses = g.senses || [];
    if (!senses.length) return '';
    var short = senses.slice(0, maxSenses).join('、');
    var full = senses.join('、');
    var toggle = senses.length > maxSenses
      ? h('button', { class: 'more', type: 'button', title: '点击展开完整释义' },
          h('span', { class: 't-more' }, '展开全部 ' + senses.length + ' 义') +
          h('span', { class: 't-less' }, '收起'))
      : '';
    var isDom = g.kind === 'domain';
    var label = isDom ? ('专业·' + (g.domain_zh || g.domain || '')) : (g.pos_zh || '释义');
    return h('div', { class: 'row-pos' + (isDom ? ' dom' : '') },
      h('span', { class: 'badge' }, esc(label)) +
      h('span', { class: 'senses' },
        h('span', { class: 'short' }, esc(short)) +
        h('span', { class: 'full' }, esc(full)) +
        toggle));
  }).join('');
  return h('div', { class: 'poslist' }, rows);
}

/* 把句子里命中的词（或其变形）包起来高亮。
   命中的词形由后端给出，所以是精确标注，不是拿词根去乱匹配。 */
function highlight(en, form) {
  if (!form) return esc(en);
  var low = en.toLowerCase(), f = form.toLowerCase();
  if (low.indexOf(f) < 0) return esc(en);
  var out = '', i = 0;
  while (true) {
    var k = low.indexOf(f, i);
    if (k < 0) { out += esc(en.slice(i)); break; }
    out += esc(en.slice(i, k)) + '<mark>' + esc(en.slice(k, k + f.length)) + '</mark>';
    i = k + f.length;
  }
  return out;
}

/* 例句块：优先英汉对照句；没有则退回词典给的英文例句。 */
function exampleBlock(card, limit) {
  var list = (card && card.examples) || [];
  limit = limit || 2;
  var rows = list.slice(0, limit).map(function (e) {
    return h('div', { class: 'ex' },
      h('div', { class: 'ex-en' }, highlight(e.en || '', e.form || '')) +
      (e.zh ? h('div', { class: 'ex-zh' }, esc(e.zh)) : ''));
  }).join('');
  if (!rows && card && card.example_en) {
    rows = h('div', { class: 'ex' },
      h('div', { class: 'ex-en' }, highlight(card.example_en, card.word || '')) +
      h('div', { class: 'ex-zh muted' }, '（词典例句，暂无中文翻译）'));
  }
  if (!rows) return '';
  return h('div', { class: 'examples' },
    h('h5', null, '例句') + rows +
    (list.length > limit ? h('div', { class: 'ex-more muted' }, '共 ' + list.length + ' 条') : ''));
}

function roundLabel(r) {
  return r === 1 ? '第 1 轮 · 识记' : r === 2 ? '第 2 轮 · 拼写' : r === 3 ? '第 3 轮 · 运用' : '第 ' + r + ' 轮';
}
function blankWord(text, word) {
  var lw = word.toLowerCase();
  var parts = text.split(' ');
  for (var i = 0; i < parts.length; i++) {
    var clean = parts[i].replace(/[^A-Za-z]/g, '').toLowerCase();
    if (clean && (clean === lw || lw.indexOf(clean) === 0 && clean.length >= 4 || clean.indexOf(lw) === 0 && lw.length >= 4)) {
      var out = parts.slice();
      out[i] = parts[i].replace(/[A-Za-z][A-Za-z'\-]*/, '______');
      return { text: out.join(' '), ok: true };
    }
  }
  return { text: text, ok: false };
}

function buildPrompt(card) {
  if (card.round >= 3 && card.collocation) {
    var b = blankWord(card.collocation, card.word);
    if (b.ok) return { kind: 'cloze', text: b.text, hint: '根据释义与真题搭配，填出缺失的单词' };
  }
  if (card.round >= 2) return { kind: 'spell', text: '', hint: '根据中文释义，拼写出这个单词' };
  return { kind: 'recognize', text: '', hint: '看词说义 — 按空格显示答案' };
}

/* 队列里还有多少张「重做」卡（评过忘了/模糊，尚未掌握） */
function redoCount() {
  var n = 0;
  for (var i = 0; i < S.queue.length; i++) {
    if (S.queue[i] && S.queue[i].retries) n++;
  }
  return n;
}

function renderCard() {
  var card = S.queue[0];
  if (!card) { renderSummary(); return; }
  // 进度只统计「已掌握」的卡片：重复做同一张不会推进进度，分子分母都不会超过总词数
  var pctDone = S.total ? Math.round(S.settled / S.total * 100) : 0;
  var pr = buildPrompt(card);
  setTitle(S.mode === 'review' ? '复习' : '背新词',
    roundLabel(card.round) + ' · 已掌握 ' + S.settled + ' / ' + S.total);

  var head = h('div', { class: 'head' },
    h('span', { class: 'tag r' + clamp(card.round, 1, 3) }, roundLabel(card.round)) +
    h('span', { class: 'tag tier' }, esc(card.tier || '')) +
    (card.freq ? h('span', { class: 'tag tier' }, '词频 ' + num(card.freq)) : '') +
    (card.state === 'new' ? h('span', { class: 'tag tier' }, '首次') : '') +
    (card.retries ? h('span', { class: 'tag retry' }, '重做 ×' + card.retries) : '') +
    h('span', { class: 'spacer' }) +
    h('button', { class: 'icon-btn', id: 'starBtn', title: '收藏 (S)' },
      '<svg viewBox="0 0 24 24" fill="' + (card.starred ? 'currentColor' : 'none') + '" stroke="currentColor" stroke-width="1.8"><path d="M12 3l2.7 5.7 6.3.9-4.6 4.4 1.1 6.2L12 17.3 6.5 20.2l1.1-6.2L3 9.6l6.3-.9z"/></svg>'));

  var body = '';
  if (pr.kind === 'recognize') {
    body = h('div', { class: 'word-line' }, h('div', { class: 'w' }, esc(card.word))) + phonRow(card);
  } else {
    body = h('div', { class: 'word-line' },
        h('div', { class: 'w', style: 'font-size:26px;font-family:var(--font-ui);font-weight:600;line-height:1.5' }, esc(card.meaning))) +
      (pr.kind === 'cloze'
        ? h('div', { class: 'prompt-hint', style: 'margin-top:20px;text-align:left;font-family:var(--font-mono);font-size:16px;color:var(--text)' }, esc(pr.text))
        : '');
  }

  var reveal = '';
  if (S.revealed) {
    var mem = card.mnemonic;
    if (pr.kind !== 'recognize') {
      reveal += h('div', { class: 'phon', style: 'margin-top:22px' },
        h('button', { class: 'play', 'data-audio': 'us', title: '播放发音' }, speakerIcon()),
        h('div', { class: 'ipa' }, h('b', null, 'US'), '/' + esc(card.phonetic_us || '—') + '/') +
        (card.phonetic_uk ? h('div', { class: 'ipa' }, h('b', null, 'UK'), '/' + esc(card.phonetic_uk) + '/') : '') +
        h('span', { class: 'tag', style: 'font-family:var(--font-en);font-size:20px;background:transparent;color:var(--text);font-weight:600;letter-spacing:.5px' }, esc(card.word)));
    }
    reveal += h('div', { class: 'answer' },
      (pr.kind === 'recognize' ? h('div', { class: 'meaning' }, esc(card.meaning)) : h('div', { class: 'meaning', style: 'font-size:16px' }, esc(card.meaning))) +
      ((S.boot.settings.show_pos !== false) ? posBlock(card, 4) : '') +
      exampleBlock(card, 2) +
      h('div', { class: 'meta' },
        (card.category ? h('span', { class: 'chip acc' }, esc(card.category)) : '') +
        (card.subcategory ? h('span', { class: 'chip' }, esc(card.subcategory)) : '') +
        (card.collocation ? h('span', { class: 'chip' }, '搭配：' + esc(card.collocation)) : '') +
        (card.alt ? h('span', { class: 'chip' }, '异体：' + esc(card.alt)) : '') +
        (card.remark ? h('span', { class: 'chip' }, esc(card.remark)) : '')) +
      (mem && (mem.breakdown || (mem.tips && mem.tips.length)) ? h('div', { class: 'mn' },
        h('h5', null, '助记'),
        h('div', { class: 'breakdown' }, esc(mem.breakdown)),
        h('ul', null, (mem.tips || []).map(function (t) { return h('li', null, esc(t)); }).join(''))) : '') +
      h('div', { class: 'mn' },
        h('h5', null, '我的笔记'),
        h('textarea', { id: 'noteBox', rows: '2', style: 'width:100%;background:var(--surface);border:1px solid var(--border-2);border-radius:9px;padding:8px 11px;resize:vertical',
          placeholder: '写点自己的联想…（失焦自动保存）' }, esc(card.note_text || ''))));
  }

  var footer = '';
  if (!S.revealed) {
    if (pr.kind === 'recognize') {
      footer = h('button', { class: 'btn primary', id: 'revealBtn', style: 'margin-top:auto;padding:14px' }, '显示答案　␣');
    } else {
      footer = h('div', { class: 'spell-box' },
        h('input', { type: 'text', id: 'spellInput', autocomplete: 'off', autocapitalize: 'off',
          spellcheck: 'false', placeholder: '在此输入英文单词，回车提交' }),
        h('div', { class: 'fb', id: 'spellFb' }, esc(pr.hint)));
    }
  } else {
    var g = [['again', '忘了', '1 · 重来'], ['hard', '模糊', '2 · 重来'],
             ['good', '记得', '3 · 掌握'], ['easy', '简单', '4 · 掌握']];
    footer = h('div', { class: 'grades' }, g.map(function (x) {
      return h('button', { class: 'grade', 'data-r': x[0] },
        h('span', { class: 'g' }, x[1]) + h('span', { class: 'n' }, x[2]));
    }).join('')) +
    h('div', { class: 'muted center', style: 'font-size:12px;margin-top:12px' },
      '当前间隔 ' + (card.interval ? card.interval.toFixed(1) + ' 天' : '新卡') +
      ' · 难度系数 ' + (card.ease || 2.5).toFixed(2) +
      ' · 已连对 ' + (card.reps || 0) + ' 次') +
    h('div', { class: 'muted center', style: 'font-size:11.5px;margin-top:6px' },
      '「忘了 / 模糊」会排到队尾再来一次，直到选「记得 / 简单」才算掌握；它们同时已进入间隔复习');
  }

  $('#view').innerHTML = h('div', { class: 'view' },
    h('div', { class: 'study-wrap' },
      h('div', { class: 'session-bar' },
        h('span', { class: 'cnt' }, '已掌握 ' + S.settled + '/' + S.total),
        h('div', { class: 'track' }, h('i', { style: 'width:' + pctDone + '%' })),
        h('span', { class: 'cnt' }, redoCount() ? ('待重做 ' + redoCount()) : ('答了 ' + S.attempts + ' 次'))) +
      h('div', { class: 'flash' }, head + body + reveal + footer)));

  if (card.round === 1 && !card.enriched) enrich(card.id);
  if (pr.kind === 'spell' || pr.kind === 'cloze') setTimeout(function () { var i = $('#spellInput'); if (i) i.focus(); }, 30);
  if (S.boot.settings.auto_play !== false && pr.kind === 'recognize') setTimeout(function () { playCard(card, 'us'); }, 120);
}

function phonRow(card) {
  return h('div', { class: 'phon' },
    h('button', { class: 'play', 'data-audio': 'us', title: '美音 (A)' }, speakerIcon()) +
    h('div', { class: 'ipa' }, h('b', null, 'US'), '/' + esc(card.phonetic_us || '—') + '/') +
    (card.phonetic_uk ? h('button', { class: 'play', 'data-audio': 'uk', title: '英音 (Shift+A)' }, speakerIcon()) : '') +
    (card.phonetic_uk ? h('div', { class: 'ipa' }, h('b', null, 'UK'), '/' + esc(card.phonetic_uk) + '/') : '') +
    h('span', { class: 'muted', style: 'font-size:12px' }, '点击喇叭或按 A 发音'));
}
function speakerIcon() {
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5L6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 010 7M18.5 5.5a9 9 0 010 13"/></svg>';
}

function checkSpelling() {
  var card = S.queue[0];
  var input = $('#spellInput');
  if (!card || !input) return;
  var val = (input.value || '').trim().toLowerCase();
  var target = card.word.toLowerCase();
  var fb = $('#spellFb');
  if (val === target) {
    fb.className = 'fb ok'; fb.textContent = '正确：' + card.word;
    S.revealed = true;
    renderCard();
    setTimeout(function () { S.suggest = 'good'; var b = $('.grade[data-r=good]'); if (b) b.focus(); }, 40);
  } else {
    fb.className = 'fb no';
    fb.textContent = val ? ('拼写不对（你输入：' + val + '）— 再试一次') : '请先输入单词';
    input.select();
  }
}

function grade(rating) {
  var card = S.queue[0];
  if (!card) return;
  var ms = S.startedAt ? (Date.now() - S.startedAt) : 0;
  S.stats[rating] = (S.stats[rating] || 0) + 1;
  S.attempts++;
  api('/api/answer', { method: 'POST', body: { word_id: card.id, round: card.round, rating: rating, ms: ms } })
    .then(function (r) {
      if (r.unlocked_round) toast('第 ' + (r.unlocked_round - 1) + ' 轮毕业，已解锁第 ' + r.unlocked_round + ' 轮');
      S.queue.shift();                       // 当前这张先出队
      if (rating === 'good' || rating === 'easy') {
        S.settled++;                         // 只有「记得 / 简单」才算掌握
      } else {
        // 「忘了 / 模糊」：原样排到队尾，本次会话内一定会再出现，次数不限，
        // 直到选「记得 / 简单」为止。同一次作答已经通过 /api/answer 进了间隔复习队列，
        // 所以即使这次会话中断，以后复习也会遇到它。
        var redo = Object.assign({}, card);
        redo.retries = (card.retries || 0) + 1;
        S.queue.push(redo);
      }
      S.startedAt = Date.now();
      S.revealed = false;
      if (!S.queue.length) { renderSummary(); return; }
      renderCard();
      refreshBoot(true);
    })
    .catch(function (e) { toast('提交失败：' + e.message); });
}

function renderSummary() {
  $('#view').innerHTML = h('div', { class: 'view narrow' },
    h('div', { class: 'card pad' },
      h('div', { class: 'empty' },
        h('div', { class: 'big' }, '本轮完成'),
        h('p', null, S.total + ' 张卡片全部掌握 · 共作答 ' + S.attempts + ' 次'),
        h('div', { class: 'grid g4 mt20', style: 'text-align:left' },
          statCard('忘了', num(S.stats.again), '', '') +
          statCard('模糊', num(S.stats.hard), '', '') +
          statCard('记得', num(S.stats.good), '', '') +
          statCard('简单', num(S.stats.easy), '', '')),
        h('div', { class: 'row', style: 'justify-content:center;margin-top:20px' },
          h('button', { class: 'btn', 'data-go': 'today' }, '返回今日') +
          h('button', { class: 'btn primary', 'id': 'moreBtn' }, '再来一批')))));
  var b = $('#moreBtn');
  if (b) b.addEventListener('click', function () { startSession(S.mode); });
}

/* ------------------------------------------------------------- 按需补音标 */
function enrich(id) {
  if (S.enrichQueue.indexOf(id) >= 0 || S.enrichedIds && S.enrichedIds[id]) return;
  S.enrichQueue.push(id);
  if (S.enriching) return;
  S.enriching = true;
  var step = function () {
    if (!S.enrichQueue.length) { S.enriching = false; return; }
    var wid = S.enrichQueue.shift();
    api('/api/enrich/' + wid, { method: 'POST' }).then(function (r) {
      if (r && r.word) {
        S.enrichedIds = S.enrichedIds || {}; S.enrichedIds[wid] = true;
        S.queue.forEach(function (c) {
          if (c.id === wid) { c.phonetic_uk = r.word.phonetic_uk || c.phonetic_uk; c.audio_us = r.word.audio_us; c.audio_uk = r.word.audio_uk; c.enriched = 1; }
        });
      }
    }).catch(function () {}).then(step);
  };
  setTimeout(step, 400);
}

/* ------------------------------------------------------------- 词库 */
function renderBrowse() {
  setTitle('词库', '搜索、筛选、查看助记');
  var b = S.browse;
  $('#view').innerHTML = h('div', { class: 'view' },
    h('div', { class: 'card pad' },
      h('div', { class: 'row wrap' },
        h('input', { type: 'text', id: 'bq', placeholder: '搜索单词 / 释义 / 搭配…', value: esc(b.q), style: 'flex:1;min-width:200px' }) +
        h('select', { id: 'btier' },
          h('option', { value: '' }, '全部梯队') +
          (S.boot.tiers || []).map(function (t) {
            return h('option', { value: esc(t.tier), selected: b.tier === t.tier ? true : null }, t.tier + ' (' + t.c + ')');
          }).join('')) +
        h('select', { id: 'bstatus' },
          sel('', '全部状态') + sel('new', '未学') + sel('learning', '学习中') + sel('done', '已毕业') + sel('starred', '已收藏')) +
        h('button', { class: 'btn', id: 'bgo' }, '查询'))) +
    h('div', { id: 'bresult', class: 'mt20' }, h('div', { class: 'empty' }, '加载中…')));
  $('#bq').value = b.q;
  $('#btier').value = b.tier;
  $('#bstatus').value = b.status;
  function sel(v, label) { return h('option', { value: v, selected: b.status === v ? true : null }, label); }
  $('#bgo').addEventListener('click', function () {
    S.browse.q = $('#bq').value; S.browse.tier = $('#btier').value;
    S.browse.status = $('#bstatus').value; S.browse.page = 1; loadBrowse();
  });
  $('#bq').addEventListener('keydown', function (e) { if (e.key === 'Enter') $('#bgo').click(); });
  loadBrowse();
}
function loadBrowse() {
  var b = S.browse;
  var qs = '?q=' + encodeURIComponent(b.q) + '&tier=' + encodeURIComponent(b.tier) +
           '&status=' + encodeURIComponent(b.status) + '&page=' + b.page + '&size=40';
  api('/api/browse' + qs).then(function (r) {
    var rows = r.rows.map(function (w) {
      var st = w.rn === 'graduated' ? h('span', { class: 'pill done' }, '已毕业')
             : w.r1 ? h('span', { class: 'pill learn' }, '学习中')
             : h('span', { class: 'pill new' }, '未学');
      return h('tr', { 'data-wid': w.id, style: 'cursor:pointer' },
        h('td', { class: 'en' }, esc(w.word) + (w.starred ? ' ★' : '')) +
        h('td', { class: 'mono muted' }, w.phonetic_us ? '/' + esc(w.phonetic_us) + '/' : '—') +
        h('td', null, esc(w.meaning) +
          (w.pos_primary ? h('div', { class: 'muted', style: 'font-size:11.5px' }, esc(w.pos_primary)) : '')) +
        h('td', { class: 'freq' }, num(w.freq)) +
        h('td', null, h('span', { class: 'pill' }, esc(w.tier || ''))) +
        h('td', null, st));
    }).join('');
    $('#bresult').innerHTML =
      h('div', { class: 'muted', style: 'font-size:13px;margin-bottom:10px' }, '共 ' + num(r.total) + ' 条，第 ' + r.page + '/' + r.pages + ' 页') +
      h('div', { class: 'table-wrap' },
        '<table class="tbl"><thead><tr><th>单词</th><th>音标</th><th>释义</th><th>词频</th><th>梯队</th><th>状态</th></tr></thead><tbody>' + rows + '</tbody></table>') +
      h('div', { class: 'row mt14', style: 'justify-content:center' },
        h('button', { class: 'btn sm', id: 'bprev', disabled: r.page <= 1 ? true : null }, '上一页') +
        h('span', { class: 'muted mono' }, r.page + ' / ' + r.pages) +
        h('button', { class: 'btn sm', id: 'bnext', disabled: r.page >= r.pages ? true : null }, '下一页'));
    $('#bprev') && $('#bprev').addEventListener('click', function () { S.browse.page--; loadBrowse(); });
    $('#bnext') && $('#bnext').addEventListener('click', function () { S.browse.page++; loadBrowse(); });
    $$('#bresult tbody tr').forEach(function (tr) {
      tr.addEventListener('click', function () { showWord(+tr.getAttribute('data-wid')); });
    });
  });
}

function showWord(id) {
  api('/api/word/' + id).then(function (r) {
    var w = r.word, mem = r.mnemonic;
    var root = h('div', { class: 'modal' },
      h('h3', null, esc(w.word)) +
      h('div', { class: 'phon', style: 'margin-top:6px' },
        h('button', { class: 'play', 'data-audio2': 'us' }, speakerIcon()) +
        h('div', { class: 'ipa' }, h('b', null, 'US'), '/' + esc(w.phonetic_us || '—') + '/') +
        (w.phonetic_uk ? h('div', { class: 'ipa' }, h('b', null, 'UK'), '/' + esc(w.phonetic_uk) + '/') : '') +
        (w.audio_us || w.audio_uk ? h('span', { class: 'chip acc' }, '含真人发音') : '')) +
      h('div', { class: 'meaning mt14', style: 'font-size:18px' }, esc(w.meaning)) +
      (w.pos && w.pos.length ? h('div', { class: 'mn mt14' }, h('h5', null, '按词性释义'), posBlock(w, 8)) : '') +
      (w.examples && w.examples.length ? h('div', { class: 'mn mt14' }, exampleBlock(w, 3)) : '') +
      h('div', { class: 'meta mt8' },
        (w.tier ? h('span', { class: 'chip acc' }, esc(w.tier)) : '') +
        (w.freq ? h('span', { class: 'chip' }, '词频 ' + num(w.freq)) : '') +
        (w.category ? h('span', { class: 'chip' }, esc(w.category)) : '') +
        (w.collocation ? h('span', { class: 'chip' }, '搭配：' + esc(w.collocation)) : '')) +
      (mem.breakdown ? h('div', { class: 'mn mt14' }, h('h5', null, '助记'), h('div', { class: 'breakdown' }, esc(mem.breakdown)) +
        h('ul', null, mem.tips.map(function (t) { return h('li', null, esc(t)); }).join(''))) : '') +
      (r.family && r.family.length ? h('div', { class: 'mn' }, h('h5', null, '同根词族'), h('div', null, r.family.map(function (f) { return h('span', { class: 'chip', style: 'margin:2px' }, esc(f)); }).join(''))) : '') +
      (r.similar && r.similar.length ? h('div', { class: 'mn' }, h('h5', null, '形近词'), h('div', null, r.similar.map(function (f) { return h('span', { class: 'chip', style: 'margin:2px' }, esc(f)); }).join(''))) : '') +
      h('div', { class: 'mn' }, h('h5', null, '我的笔记'),
        h('textarea', { id: 'modalNote', rows: '3', style: 'width:100%;background:var(--surface);border:1px solid var(--border-2);border-radius:9px;padding:9px 11px;resize:vertical' }, esc(r.note || ''))) +
      h('div', { class: 'row mt20', style: 'justify-content:flex-end' },
        h('button', { class: 'btn', id: 'closeModal' }, '关闭')));

    $('#modalRoot').innerHTML = h('div', { class: 'modal-bg' }, root);
    $('#closeModal').addEventListener('click', function () { $('#modalRoot').innerHTML = ''; });
    $('.modal-bg').addEventListener('click', function (e) { if (e.target.classList.contains('modal-bg')) $('#modalRoot').innerHTML = ''; });
    $('[data-audio2]').addEventListener('click', function () { playCard({ word: w.word, audio_us: w.audio_us, audio_uk: w.audio_uk }, 'us'); });
    $('#modalNote').addEventListener('blur', function () {
      api('/api/note', { method: 'POST', body: { word_id: w.id, text: this.value } }).then(function () { toast('笔记已保存'); });
    });
  });
}

/* ------------------------------------------------------------- 仪表板 */
function renderDash() {
  setTitle('仪表板', '进度、遗忘曲线与预测');
  api('/api/dashboard').then(function (d) {
    var t = d.totals;
    var head = h('div', { class: 'grid g4' },
      statCard('词库总量', num(t.total), '含考纲全部词条', '') +
      statCard('已开始', num(t.learned), '占比 ' + (t.total ? Math.round(t.learned / t.total * 100) : 0) + '%', '') +
      statCard('已毕业', num(t.graduated), d.rounds + ' 轮全部完成', 'accent') +
      statCard('连续打卡', num(d.streak), '天', 'ok'));

    // 热力图
    var have = {};
    d.days.forEach(function (x) { have[x.date] = (x.new_count || 0) + (x.review_count || 0); });
    var cells = [];
    var start = addDays(todayISO(), -181);
    for (var i = 0; i < 182; i++) {
      var dt = addDays(start, i), n = have[dt] || 0;
      var lv = n === 0 ? 0 : n < 10 ? 1 : n < 25 ? 2 : n < 60 ? 3 : 4;
      cells.push(h('i', { 'data-l': lv, title: dt + ' · ' + n + ' 张' }));
    }
    var heat = h('div', { class: 'card pad' },
      h('h3', null, '近 26 周学习热力') +
      h('div', { class: 'heat' }, cells.join('')) +
      h('div', { class: 'legend' }, h('span', null, h('i', { style: 'background:var(--bg-soft)' }), '0') +
        h('span', null, h('i', { style: 'background:color-mix(in srgb, var(--accent) 26%, var(--bg-soft))' }), '10+') +
        h('span', null, h('i', { style: 'background:color-mix(in srgb, var(--accent) 48%, var(--bg-soft))' }), '25+') +
        h('span', null, h('i', { style: 'background:color-mix(in srgb, var(--accent) 72%, var(--bg-soft))' }), '60+') +
        h('span', null, h('i', { style: 'background:var(--accent)' }), '更多')));

    // 遗忘曲线
    var colors = ['var(--accent)', 'var(--warn)', 'var(--ok)', 'var(--text-2)'];
    var W = 560, H = 200, PL = 38, PB = 26;
    var lines = d.curve.map(function (c, i) {
      var pts = c.points.map(function (p) {
        var x = PL + (p.t / 21) * (W - PL - 10);
        var y = 12 + (1 - p.r) * (H - 12 - PB);
        return x.toFixed(1) + ',' + y.toFixed(1);
      }).join(' ');
      return '<polyline class="ln" stroke="' + colors[i % colors.length] + '" points="' + pts + '"/>';
    }).join('');
    var curve = h('div', { class: 'card pad' },
      h('h3', null, '遗忘曲线（各轮平均保持时间）') +
      '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '">' +
      [0, .25, .5, .75, 1].map(function (v) {
        var y = 12 + (1 - v) * (H - 12 - PB);
        return '<line class="gl" x1="' + PL + '" y1="' + y + '" x2="' + (W - 10) + '" y2="' + y + '"/>' +
               '<text x="4" y="' + (y + 3) + '">' + Math.round(v * 100) + '%</text>';
      }).join('') +
      [0, 3, 7, 14, 21].map(function (dd) {
        var x = PL + (dd / 21) * (W - PL - 10);
        return '<line class="ax" x1="' + x + '" y1="12" x2="' + x + '" y2="' + (H - PB) + '"/>' +
               '<text x="' + (x - 6) + '" y="' + (H - 8) + '">' + dd + 'd</text>';
      }).join('') +
      lines + '</svg>' +
      h('div', { class: 'legend' }, d.curve.map(function (c, i) {
        return h('span', null, h('i', { style: 'background:' + colors[i % colors.length] }), '第 ' + c.round + ' 轮（稳定期 ' + c.stability + ' 天）');
      }).join('')) +
      h('p', { class: 'muted', style: 'font-size:12px' }, '曲线按 R = e^(−t/S) 计算，S 为该轮已学卡片的平均间隔天数。轮次越高（回忆/运用比识记难），曲线下降越快，复习越密集。'));

    // 预测
    var maxF = Math.max.apply(null, d.forecast.map(function (x) { return x.due; }).concat([1]));
    var fb = h('div', { class: 'card pad' },
      h('h3', null, '未来 30 天复习量预测') +
      h('div', { class: 'bars' }, d.forecast.map(function (x, i) {
        var hh = Math.max(2, Math.round(x.due / maxF * 100));
        return h('div', { class: 'b' + (i === 0 ? ' today' : ''), style: 'height:' + hh + '%',
          'data-tip': x.date + ' · ' + x.due + ' 张' });
      }).join('')) +
      h('div', { class: 'muted', style: 'font-size:12px;margin-top:8px' }, '峰值 ' + maxF + ' 张/天 · 红色为今天'));

    // 梯队进度
    var tierRows = d.tiers.map(function (x) {
      var p = x.total ? Math.round(x.done / x.total * 100) : 0;
      return h('tr', null,
        h('td', null, h('span', { class: 'pill' }, esc(x.tier || ''))) +
        h('td', { class: 'mono' }, num(x.total)) +
        h('td', { class: 'mono' }, num(x.started)) +
        h('td', { class: 'mono' }, num(x.done)) +
        h('td', { style: 'width:160px' },
          h('div', { class: 'mini-bar' }, h('i', { style: 'width:' + p + '%' })) +
          h('span', { class: 'muted mono', style: 'font-size:11.5px' }, p + '%')));
    }).join('');
    var tiers = h('div', { class: 'card pad' }, h('h3', null, '各梯队进度'),
      h('div', { class: 'table-wrap' }, '<table class="tbl"><thead><tr><th>梯队</th><th>总数</th><th>已开始</th><th>已毕业</th><th>完成度</th></tr></thead><tbody>' + tierRows + '</tbody></table>'));

    // 难词
    var hardRows = d.hard.length ? d.hard.map(function (x) {
      return h('tr', null,
        h('td', { class: 'en' }, esc(x.word)) +
        h('td', null, esc(x.meaning)) +
        h('td', { class: 'mono' }, num(x.lapses)) +
        h('td', { class: 'mono' }, num(x.wrong)));
    }).join('') : h('tr', null, h('td', { colspan: '4', class: 'muted center' }, '还没有遗忘记录，继续保持'));
    var hard = h('div', { class: 'card pad' }, h('h3', null, '最难记的 15 个词'),
      h('div', { class: 'table-wrap' }, '<table class="tbl"><thead><tr><th>单词</th><th>释义</th><th>遗忘次数</th><th>答错次数</th></tr></thead><tbody>' + hardRows + '</tbody></table>'));

    // 近 14 天
    var accRows = d.accuracy.map(function (x) {
      var tot = (x.correct || 0) + (x.wrong || 0);
      var a = tot ? Math.round(x.correct / tot * 100) : 0;
      return h('tr', null, h('td', { class: 'mono' }, x.date), h('td', { class: 'mono' }, num(x.new_count)),
        h('td', { class: 'mono' }, num(x.review_count)), h('td', { class: 'mono' }, num(tot)),
        h('td', { class: 'mono' }, a + '%'), h('td', { class: 'mono' }, Math.round((x.ms || 0) / 60000) + ' 分'));
    }).join('');
    var acc = h('div', { class: 'card pad' }, h('h3', null, '近 14 天记录'),
      h('div', { class: 'table-wrap' }, '<table class="tbl"><thead><tr><th>日期</th><th>新词</th><th>复习</th><th>总答题</th><th>正确率</th><th>用时</th></tr></thead><tbody>' + accRows + '</tbody></table>'));

    $('#view').innerHTML = h('div', { class: 'view' }, head +
      // 用类而不是内联 grid-template-columns：内联样式会盖过媒体的响应式规则
      h('div', { class: 'grid mt20 dash-split' }, heat + fb) +
      h('div', { class: 'mt20' }, curve) +
      h('div', { class: 'grid g2 mt20' }, tiers + hard) +
      h('div', { class: 'mt20' }, acc));
  });
}

/* ------------------------------------------------------------- 设置 */
function renderSettings() {
  setTitle('设置', '计划、轮次与偏好');
  var s = S.boot.settings;
  api('/api/settings').then(function (st) {
    var tiers = S.boot.tiers || [];
    var sel = st.tiers || [];
    var body = h('div', { class: 'card pad' },
      row('考试名称', '显示在倒计时上', h('input', { type: 'text', id: 'stName', value: esc(st.exam_name || '') })) +
      row('考试日期', '倒计时与每日计划的基准', h('input', { type: 'date', id: 'stDate', value: esc(st.exam_date || '') })) +
      row('每个单词的轮次', '默认 3 轮：识记 → 拼写 → 运用。上一轮毕业才会解锁下一轮。',
        h('input', { type: 'number', id: 'stRounds', min: '1', max: '6', value: st.rounds || 3 })) +
      row('每轮毕业所需间隔（天）', '间隔达到该天数就算该轮毕业，并解锁下一轮。',
        h('input', { type: 'text', id: 'stGrad', value: esc((st.graduation || [3, 7, 21]).join(', ')), placeholder: '3, 7, 21' })) +
      row('每批卡片数', '一次学习会话的卡片数量', h('input', { type: 'number', id: 'stBatch', min: '5', max: '200', value: st.batch_size || 20 })) +
      row('语音音量/语速', '浏览器合成音朗读速度，0.5 慢 ~ 1.5 快',
        h('input', { type: 'number', id: 'stRate', min: '0.4', max: '1.6', step: '0.05', value: st.speech_rate || 0.85 })) +
      row('显示词性释义', '揭开答案时按词性分行列出名词、动词、形容词等各义项',
        h('input', { type: 'checkbox', id: 'stPos', checked: st.show_pos ? true : null })) +
      row('显示答案后自动发音', '第 1 轮认词时自动朗读',
        h('input', { type: 'checkbox', id: 'stAuto', checked: st.auto_play ? true : null })) +
      row('优先使用在线真人发音', '有真人录音时优先播放，没有则回退到浏览器合成音',
        h('input', { type: 'checkbox', id: 'stReal', checked: S.preferReal ? true : null })));

    var tierBox = h('div', { class: 'card pad mt20' },
      h('h3', null, '参与学习的梯队'),
      h('p', { class: 'muted', style: 'font-size:12.5px;margin:0 0 12px' },
        '取消勾选可把低频词排除在推送队列之外。当前所选共约 ' + num(S.boot.counts.selected) + ' 词。') +
      h('div', { class: 'row wrap' }, tiers.map(function (t) {
        return h('label', { class: 'chip', style: 'cursor:pointer;display:flex;align-items:center;gap:6px;padding:6px 12px' },
          h('input', { type: 'checkbox', 'data-tier': esc(t.tier), checked: sel.indexOf(t.tier) >= 0 ? true : null }) +
          h('span', null, esc(t.tier) + '（' + t.c + '）'));
      }).join('')));

    var dataBox = h('div', { class: 'card pad mt20' },
      h('h3', null, '数据') +
      h('div', { class: 'row wrap' },
        h('button', { class: 'btn', id: 'btnExport' }, '导出学习记录 JSON') +
        h('button', { class: 'btn', id: 'btnResetP' }, '清空学习进度（保留笔记）') +
        h('button', { class: 'btn', id: 'btnResetA' }, '清空全部数据')) +
      h('p', { class: 'muted', style: 'font-size:12px;margin-top:10px' },
        '数据保存在本地 SQLite：kaoyan-vocab/data/vocab.db。备份该文件即可迁移。'));

    $('#view').innerHTML = h('div', { class: 'view narrow' }, body + tierBox + dataBox +
      h('div', { class: 'row mt20', style: 'justify-content:flex-end' },
        h('button', { class: 'btn primary', id: 'stSave' }, '保存设置')));

    function row(t, d, ctrl) {
      return h('div', { class: 'set-row' }, h('div', { class: 't' }, h('b', null, t) + h('small', null, d)),
        h('div', null, ctrl));
    }
    $('#stSave').addEventListener('click', function () {
      var picked = $$('input[data-tier]:checked').map(function (x) { return x.getAttribute('data-tier'); });
      var grad = $('#stGrad').value.split(',').map(function (x) { return parseFloat(x.trim()); })
        .filter(function (x) { return !isNaN(x) && x > 0; });
      var patch = {
        exam_name: $('#stName').value, exam_date: $('#stDate').value,
        rounds: parseInt($('#stRounds').value, 10) || 3,
        graduation: grad.length ? grad : [3, 7, 21],
        batch_size: parseInt($('#stBatch').value, 10) || 20,
        speech_rate: parseFloat($('#stRate').value) || 0.85,
        auto_play: $('#stAuto').checked ? '1' : '0',
        show_pos: $('#stPos').checked ? '1' : '0',
        tiers: picked
      };
      S.preferReal = $('#stReal').checked;
      api('/api/settings', { method: 'POST', body: patch }).then(function () {
        toast('设置已保存');
        return refreshBoot().then(function () { go('today'); });
      });
    });
    $('#stReal').addEventListener('change', function () { S.preferReal = this.checked; });
    $('#btnExport').addEventListener('click', function () {
      api('/api/export').then(function (d) {
        var blob = new Blob([JSON.stringify(d, null, 2)], { type: 'application/json' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'vocab-backup-' + todayISO() + '.json';
        a.click();
        toast('已导出');
      });
    });
    $('#btnResetP').addEventListener('click', function () { confirmReset('progress'); });
    $('#btnResetA').addEventListener('click', function () { confirmReset('all'); });
  });
}
function confirmReset(what) {
  $('#modalRoot').innerHTML = h('div', { class: 'modal-bg' }, h('div', { class: 'modal' },
    h('h3', null, what === 'all' ? '清空全部数据？' : '清空学习进度？'),
    h('p', { class: 'muted' }, what === 'all'
      ? '将删除进度、复习记录、统计与笔记，词库本身保留。此操作不可撤销。'
      : '将删除所有进度、复习记录与统计，笔记和收藏保留。此操作不可撤销。'),
    h('div', { class: 'row', style: 'justify-content:flex-end;margin-top:16px' },
      h('button', { class: 'btn', id: 'cNo' }, '取消') +
      h('button', { class: 'btn primary', id: 'cYes' }, '确认清空'))));
  $('#cNo').addEventListener('click', function () { $('#modalRoot').innerHTML = ''; });
  $('#cYes').addEventListener('click', function () {
    api('/api/reset', { method: 'POST', body: { what: what } }).then(function () {
      $('#modalRoot').innerHTML = ''; toast('已清空');
      refreshBoot().then(function () { go('today'); });
    });
  });
}

/* ------------------------------------------------------------- 事件委托 */
document.addEventListener('click', function (e) {
  // 「展开全部 N 义」：原地展开，不换页、不弹窗
  var mb = e.target.closest ? e.target.closest('.more') : null;
  if (mb) {
    var mrow = mb.closest('.row-pos');
    if (mrow) mrow.setAttribute('data-open', mrow.getAttribute('data-open') === '1' ? '0' : '1');
    return;
  }
  var t = e.target.closest ? e.target.closest('[data-go]') : null;
  if (t) { go(t.getAttribute('data-go')); return; }
  var a = e.target.closest ? e.target.closest('[data-audio]') : null;
  if (a) { var c = S.queue[0]; if (c) playCard(c, a.getAttribute('data-audio')); return; }
  var g = e.target.closest ? e.target.closest('.grade') : null;
  if (g) { grade(g.getAttribute('data-r')); return; }
  // 注意：这些按钮内部都有 <svg>/<span>，点图标时 e.target 是子元素而不是按钮本身，
  // 用 e.target.id 判断会「点几次才有反应」，必须走 closest。
  var hit = function (sel) { return e.target.closest ? e.target.closest(sel) : null; };
  if (hit('#revealBtn')) { S.revealed = true; renderCard(); return; }
  if (hit('#starBtn')) { toggleStar(); return; }
  if (hit('#themeBtn')) { toggleTheme(); return; }
  if (hit('#menuBtn')) {
    var sb = $('#sidebar'), sc = $('#navScrim');
    sb.classList.toggle('open');
    if (sc) sc.classList.toggle('on', sb.classList.contains('open'));
    return;
  }
  if (hit('#navScrim')) {
    $('#sidebar').classList.remove('open');
    var s2 = $('#navScrim'); if (s2) s2.classList.remove('on');
    return;
  }
  if (hit('#closeModal')) { $('#modalRoot').innerHTML = ''; return; }
});
document.addEventListener('input', function (e) {
  if (e.target.id === 'spellInput') { /* 实时不校验，回车提交 */ }
});
document.addEventListener('keydown', function (e) {
  var tag = (e.target.tagName || '').toLowerCase();
  var typing = tag === 'input' || tag === 'textarea' || tag === 'select';
  if (e.target.id === 'spellInput' && e.key === 'Enter') { e.preventDefault(); checkSpelling(); return; }
  if (e.key === 'Escape') { $('#modalRoot').innerHTML = ''; return; }
  if (typing) return;
  if (S.route !== 'study' && S.route !== 'review') return;
  if (!S.queue.length) return;
  if (e.key === ' ' || e.key === 'Enter') {
    e.preventDefault();
    if (!S.revealed) { S.revealed = true; renderCard(); }
    return;
  }
  if (!S.revealed) return;
  var map = { '1': 'again', '2': 'hard', '3': 'good', '4': 'easy' };
  if (map[e.key]) { e.preventDefault(); grade(map[e.key]); return; }
  if (e.key === 'a' || e.key === 'A') { e.preventDefault(); playCard(S.queue[0], e.shiftKey ? 'uk' : 'us'); return; }
  if (e.key === 's' || e.key === 'S') { e.preventDefault(); toggleStar(); return; }
});
function toggleStar() {
  var c = S.queue[0];
  if (!c) return;
  c.starred = c.starred ? 0 : 1;
  api('/api/note', { method: 'POST', body: { word_id: c.id, starred: c.starred } })
    .then(function () { toast(c.starred ? '已收藏' : '已取消收藏'); renderCard(); });
}

/* ------------------------------------------------------------- 启动 */
function refreshBoot(silent) {
  return api('/api/bootstrap').then(function (b) {
    S.boot = b;
    S.preferReal = true;
    renderNav(); renderSide(); renderTop();
    if (!silent && S.route === 'today') renderToday();
    return b;
  });
}
function init() {
  applyTheme(currentTheme());
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
      if (currentTheme() === 'auto') applyTheme('auto');
    });
  }
  if (window.innerWidth <= 720) $('#menuBtn').style.display = 'grid';
  window.addEventListener('resize', function () {
    $('#menuBtn').style.display = window.innerWidth <= 720 ? 'grid' : 'none';
  });
  window.addEventListener('hashchange', function () {
    var r = location.hash.slice(1);
    if (r && r !== S.route && ROUTES.some(function (x) { return x.id === r; })) go(r);
  });
  refreshBoot().then(function () {
    var r = location.hash.slice(1);
    go(ROUTES.some(function (x) { return x.id === r; }) ? r : 'today');
  });
}
window.App = { go: go, toggleTheme: toggleTheme, showWord: showWord };
init();
})();
