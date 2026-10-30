(() => {
  'use strict';
  const D = JSON.parse(document.getElementById('bp-data').textContent);
  const model = D.model;
  const M = new Map(model.modules.map((m) => [m.id, m]));
  const E = new Map(model.edges.map((e) => [e.id, e]));
  const LAYER = new Map(model.layers.map((l) => [l.id, l]));
  const KIND = new Map(model.edgeKinds.map((k) => [k.id, k]));
  const INV = new Map(model.invariants.map((x) => [x.id, x]));
  const AT = new Map(model.acceptance.map((x) => [x.id, x]));
  const SL = new Map(model.slices.map((x) => [x.id, x]));
  const STEP = new Map(model.flow.map((s) => [s.n, s]));
  const FLOW = D.flowName || '流程';
  const CIRCLED = ['', '①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩'];
  const NS = 'http://www.w3.org/2000/svg';
  // 本版改动：architecture.json 里的 revision 列出改了哪些模块、箭头、不变量、验收、切片
  const REV = model.revision || null;
  const revIds = new Set(REV ? REV.items.flatMap((it) => it.refs) : []);
  const revNew = new Set(REV ? REV.added || [] : []);
  const revKind = (id) => (revNew.has(id) ? '新' : revIds.has(id) ? '改' : '');
  const revItems = (id) => (REV ? REV.items.filter((it) => it.refs.includes(id)) : []);
  const state = { sel: null, step: 0, slice: '', actual: false, rev: !!REV };

  // 每个模块在哪个切片新建（第一次被该切片的验收覆盖），每一步流程在哪个切片亮起
  const sliceIndex = new Map(model.slices.map((x, i) => [x.id, i]));
  const builtAt = new Map();
  const litAt = new Map();
  for (const sl of model.slices) {
    for (const a of sl.ats) for (const m of (AT.get(a) || { covers: [] }).covers) if (!builtAt.has(m)) builtAt.set(m, sl.id);
    for (const n of sl.steps) litAt.set(n, sl.id);
  }
  const sliceNo = (id) => sliceIndex.get(id) + 1;
  const shortName = (sl) => sl.name.split('：')[0];
  const circled = (ns) => ns.map((n) => CIRCLED[n]).join('');

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const known = (id) => M.has(id) || INV.has(id) || AT.has(id) || SL.has(id);
  const refBtn = (id) => known(id)
    ? `<button type="button" class="ref" data-ref="${esc(id)}">${esc(id)}</button>`
    : `<span class="ref unknown" title="图上不存在">${esc(id)}</span>`;
  const edgeBtn = (id) => `<button type="button" class="ref" data-edgeref="${esc(id)}">箭头 ${esc(id)}</button>`;
  const anyRef = (id) => (E.has(id) ? edgeBtn(id) : refBtn(id));
  const revChip = (id) => (revKind(id) ? `<span class="chip rev">本版${revNew.has(id) ? '新增' : '改动'}</span>` : '');
  const revNote = (id) => {
    const its = revItems(id);
    return its.length ? `<div class="revision small"><ul>${its.map((it) => `<li>${esc(it.text)}</li>`).join('')}</ul></div>` : '';
  };
  const nameOf = (id) => (M.get(id) || INV.get(id) || AT.get(id) || SL.get(id) || {}).name || (INV.get(id) || {}).text || id;

  // ---------- 简易 Markdown ----------
  function inline(text) {
    return text.split(/(`[^`]+`)/).map((part) => {
      if (/^`[^`]+`$/.test(part)) return `<code>${esc(part.slice(1, -1))}</code>`;
      let s = esc(part);
      s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
      s = s.replace(/\[([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)\]/g, (_, id) => refBtn(id));
      return s;
    }).join('');
  }
  function table(rows) {
    const cells = (r) => r.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
    const head = cells(rows[0]);
    const body = rows.slice(2).map(cells);
    return `<div class="md-table"><table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>${body.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }
  function md(src) {
    const lines = src.split('\n');
    const out = [];
    let i = 0;
    const isBlockStart = (l) => /^\s*```|^\||^#{1,6} |^\s*[-*] |^\d+\. |^>/.test(l);
    while (i < lines.length) {
      const l = lines[i];
      if (/^\s*```/.test(l)) {
        const buf = [];
        i += 1;
        while (i < lines.length && !/^\s*```/.test(lines[i])) { buf.push(lines[i]); i += 1; }
        i += 1;
        out.push(`<pre><code>${esc(buf.join('\n'))}</code></pre>`);
      } else if (/^\|/.test(l)) {
        const rows = [];
        while (i < lines.length && /^\|/.test(lines[i])) { rows.push(lines[i]); i += 1; }
        out.push(table(rows));
      } else if (/^#{1,6} /.test(l)) {
        out.push(`<p><strong>${inline(l.replace(/^#+ /, ''))}</strong></p>`);
        i += 1;
      } else if (/^\s*[-*] /.test(l)) {
        const items = [];
        while (i < lines.length && (/^\s*[-*] /.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && !/^\s*```/.test(lines[i])))) {
          if (/^\s*[-*] /.test(lines[i])) items.push({ depth: lines[i].match(/^\s*/)[0].length, text: lines[i].replace(/^\s*[-*] /, '') });
          else items[items.length - 1].text += ' ' + lines[i].trim();
          i += 1;
        }
        let html = '<ul>';
        let depth = items.length ? items[0].depth : 0;
        for (const it of items) {
          if (it.depth > depth) html += '<ul>';
          if (it.depth < depth) html += '</ul>';
          depth = it.depth;
          html += `<li>${inline(it.text)}</li>`;
        }
        if (depth > (items[0] ? items[0].depth : 0)) html += '</ul>';
        out.push(html + '</ul>');
      } else if (/^\d+\. /.test(l)) {
        const items = [];
        while (i < lines.length && /^\d+\. /.test(lines[i])) { items.push(lines[i].replace(/^\d+\. /, '')); i += 1; }
        out.push(`<ol>${items.map((t) => `<li>${inline(t)}</li>`).join('')}</ol>`);
      } else if (/^>/.test(l)) {
        const buf = [];
        while (i < lines.length && /^>/.test(lines[i])) { buf.push(lines[i].replace(/^>\s?/, '')); i += 1; }
        out.push(`<blockquote>${md(buf.join('\n'))}</blockquote>`);
      } else if (!l.trim()) {
        i += 1;
      } else {
        const buf = [];
        while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) { buf.push(lines[i].trim()); i += 1; }
        out.push(`<p>${inline(buf.join(' '))}</p>`);
      }
    }
    return out.join('');
  }

  // ---------- 几何 ----------
  const center = (m) => [m.box.x + m.box.w / 2, m.box.y + m.box.h / 2];
  function clip(m, toward) {
    const [cx, cy] = center(m);
    const dx = toward[0] - cx;
    const dy = toward[1] - cy;
    if (!dx && !dy) return [cx, cy];
    const t = Math.min(dx ? m.box.w / 2 / Math.abs(dx) : Infinity, dy ? m.box.h / 2 / Math.abs(dy) : Infinity);
    return [cx + dx * t, cy + dy * t];
  }
  function pointsOf(e) {
    if (e.path) return e.path;
    const a = M.get(e.from);
    const b = M.get(e.to);
    return [clip(a, center(b)), clip(b, center(a))];
  }
  function midpoint(pts) {
    const segs = [];
    let total = 0;
    for (let i = 1; i < pts.length; i += 1) {
      const len = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
      segs.push(len);
      total += len;
    }
    let half = total / 2;
    for (let i = 0; i < segs.length; i += 1) {
      if (half <= segs[i]) {
        const t = segs[i] ? half / segs[i] : 0;
        return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t];
      }
      half -= segs[i];
    }
    return pts[pts.length - 1];
  }
  const d = (pts) => pts.map((p, i) => `${i ? 'L' : 'M'}${p[0]},${p[1]}`).join(' ');

  function el(name, attrs, parent) {
    const node = document.createElementNS(NS, name);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== undefined && v !== null) node.setAttribute(k, v);
    if (parent) parent.appendChild(node);
    return node;
  }
  function text(parent, x, y, str, cls, anchor) {
    const t = el('text', { x, y, class: cls, 'text-anchor': anchor || 'start' }, parent);
    t.textContent = str;
    return t;
  }

  // ---------- 画图 ----------
  const svg = document.getElementById('diagram');
  const edgeNodes = new Map();
  const modNodes = new Map();
  const badgeNodes = new Map();
  let extraLayer = null;

  function drawDiagram() {
    const { w, h } = model.canvas;
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    const defs = el('defs', {}, svg);
    for (const [id, cls] of [['arr', 'mk'], ['arr-hl', 'mk-hl'], ['arr-ok', 'mk-ok'], ['arr-bad', 'mk-bad'], ['arr-miss', 'mk-miss'], ['arr-rev', 'mk-rev']]) {
      const mk = el('marker', { id, viewBox: '0 0 10 10', refX: 9.5, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' }, defs);
      el('path', { d: 'M0,0 L10,5 L0,10 z', class: cls }, mk);
    }
    for (const r of model.regions) {
      const g = el('g', { class: 'region' }, svg);
      el('rect', { x: r.x, y: r.y, width: r.w, height: r.h, rx: 10 }, g);
      text(g, r.x + 14, r.y + 22, r.name);
      (r.notes || []).forEach((n, i) => text(g, r.x + 14, r.y + 42 + i * 18, n, 'note'));
    }
    for (const l of model.labels || []) text(svg, l.x, l.y, l.text, l.small ? 'row-label' : 'row-label big');
    if (model.boundary) {
      const b = model.boundary;
      const g = el('g', { class: 'boundary' }, svg);
      el('line', { x1: b.x1, y1: b.y1, x2: b.x2, y2: b.y2 }, g);
      text(g, b.labelX, b.labelY, b.label);
    }
    const edgeLayer = el('g', {}, svg);
    for (const e of model.edges) {
      const info = D.edgeInfo[e.id];
      const g = el('g', { class: `edge kind-${e.kind}${info.inSpec ? '' : ' not-in-spec'}`, 'data-edge': e.id }, edgeLayer);
      const pts = pointsOf(e);
      el('path', { d: d(pts), class: 'ln', 'marker-end': `url(#${info.inSpec ? 'arr' : 'arr-bad'})` }, g);
      el('path', { d: d(pts), class: 'hit' }, g);
      const title = el('title', {}, g);
      title.textContent = `${nameOf(e.from)} → ${nameOf(e.to)}：${e.label}`;
      g.addEventListener('click', () => select({ type: 'edge', id: e.id }));
      edgeNodes.set(e.id, g);
    }
    extraLayer = el('g', {}, svg);
    for (const m of model.modules) {
      const st = D.moduleStatus[m.id];
      const g = el('g', { class: `mod layer-${m.layer}${st.ok ? '' : ' has-problem'}`, tabindex: 0, role: 'button', 'aria-label': `${m.name}（${m.id}）`, 'data-mod': m.id }, svg);
      const b = m.box;
      el('rect', { class: 'box', x: b.x, y: b.y, width: b.w, height: b.h, rx: 7 }, g);
      const cx = b.x + b.w / 2;
      if (b.h < 40) {
        text(g, cx, b.y + b.h / 2 + 5, m.name, 'name', 'middle');
      } else if (b.h < 50) {
        text(g, cx, b.y + b.h / 2 + 5, `${m.name}　·　${m.sub}${m.dir ? '　·　' + m.dir : ''}`, 'name', 'middle');
      } else {
        const top = b.y + (b.h - 46) / 2;
        text(g, cx, top + 14, m.name, 'name', 'middle');
        text(g, cx, top + 31, m.sub, 'sub', 'middle');
        if (m.dir) text(g, cx, top + 45, m.dir, 'dir', 'middle');
      }
      const bx = b.x + b.w - 2;
      const by = b.y + 2;
      if (revKind(m.id)) {
        const tg = el('g', { class: 'rev-tag' }, g);
        el('rect', { x: b.x - 6, y: b.y - 8, width: 20, height: 15, rx: 4 }, tg);
        text(tg, b.x + 4, b.y + 3.5, revKind(m.id), '', 'middle');
      }
      el('circle', { cx: bx, cy: by, r: 7, class: st.ok ? 'badge-ok' : 'badge-bad' }, g);
      text(g, bx, by + 3.5, st.ok ? '✓' : '!', 'badge-mark', 'middle');
      const title = el('title', {}, g);
      title.textContent = st.ok ? `${m.name}：文字与图一致` : `${m.name}：${st.problems.length} 处不一致`;
      g.addEventListener('click', () => select({ type: 'module', id: m.id }));
      g.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); select({ type: 'module', id: m.id }); } });
      modNodes.set(m.id, g);
    }
    for (const s of model.flow) {
      const e = E.get(s.badgeEdge);
      if (!e) continue;
      const [x, y] = midpoint(pointsOf(e));
      const g = el('g', { class: 'step-badge', 'data-step': s.n }, svg);
      el('circle', { cx: x, cy: y, r: 10 }, g);
      text(g, x, y + 4, String(s.n), '', 'middle');
      const title = el('title', {}, g);
      title.textContent = `第 ${s.n} 步：${s.title}`;
      g.addEventListener('click', () => setStep(s.n));
      badgeNodes.set(s.n, g);
    }
  }

  function legend() {
    const box = document.getElementById('legend');
    const items = [];
    const dash = { call: '', load: '6 3 1.5 3', spawn: '5 4', external: '1.5 3.5' };
    for (const k of model.edgeKinds) {
      items.push(`<span><svg width="30" height="10" aria-hidden="true"><line x1="0" y1="5" x2="30" y2="5" stroke="currentColor" stroke-width="2" stroke-dasharray="${dash[k.id] || ''}"/></svg>${esc(k.name)}</span>`);
    }
    for (const l of model.layers) {
      items.push(`<span><i class="swatch" style="background:var(--lc-${l.id});border-color:var(--lc-${l.id}-s)"></i>${esc(l.name)}</span>`);
    }
    items.push('<span><svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="6" fill="var(--ok)"/></svg>文字与图一致</span>');
    items.push('<span><svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="6" fill="var(--bad)"/></svg>有偏差</span>');
    box.innerHTML = items.join('');
  }

  // ---------- 高亮 ----------
  // 切片视图：new = 本切片新建，built = 之前的切片已建，future = 之后的切片才建
  function sliceState(modId) {
    const at = builtAt.get(modId);
    if (!state.slice || !at) return state.slice ? 'future' : '';
    const d = sliceIndex.get(at) - sliceIndex.get(state.slice);
    return d === 0 ? 'new' : d < 0 ? 'built' : 'future';
  }
  function applyHighlight() {
    const step = state.step ? STEP.get(state.step) : null;
    // 本版改动只在没有选流程、切片、代码对比时显示，免得几种颜色叠在一起
    const showRev = state.rev && !state.step && !state.slice && !state.actual;
    svg.classList.toggle('show-rev', showRev);
    const stepEdges = new Set(step ? step.edges : []);
    const stepMods = new Set();
    for (const id of stepEdges) { const e = E.get(id); stepMods.add(e.from); stepMods.add(e.to); }
    const sl = state.slice ? SL.get(state.slice) : null;
    const edgeSlice = (e) => {
      const a = sliceState(e.from);
      const b = sliceState(e.to);
      if (a === 'future' || b === 'future') return 'dim';
      return a === 'new' || b === 'new' ? 'hl' : '';
    };
    for (const [id, g] of edgeNodes) {
      const info = D.edgeInfo[id];
      const es = sl ? edgeSlice(E.get(id)) : '';
      g.classList.toggle('hl', (!!step && stepEdges.has(id)) || es === 'hl');
      g.classList.toggle('dim', (!!step && !stepEdges.has(id)) || es === 'dim');
      g.classList.toggle('selected', state.sel && state.sel.type === 'edge' && state.sel.id === id);
      g.classList.remove('act-ok', 'act-missing');
      g.classList.toggle('rev-on', revIds.has(id));
      let marker = info.inSpec ? 'arr' : 'arr-bad';
      if (showRev && revIds.has(id)) marker = 'arr-rev';
      if (state.actual && D.actual) {
        const st = D.actual.edgeStatus[id];
        if (st === 'ok') { g.classList.add('act-ok'); marker = 'arr-ok'; }
        if (st === 'missing') { g.classList.add('act-missing'); marker = 'arr-miss'; }
      }
      if ((step && stepEdges.has(id)) || es === 'hl' || (state.sel && state.sel.type === 'edge' && state.sel.id === id)) marker = 'arr-hl';
      g.querySelector('.ln').setAttribute('marker-end', `url(#${marker})`);
    }
    for (const [id, g] of modNodes) {
      const ms = sl ? sliceState(id) : '';
      g.classList.toggle('dim', (!!step && !stepMods.has(id)) || ms === 'future');
      g.classList.toggle('hl', !!step && stepMods.has(id));
      g.classList.toggle('sl-new', ms === 'new');
      g.classList.toggle('rev-on', revIds.has(id));
      g.classList.toggle('selected', state.sel && state.sel.type === 'module' && state.sel.id === id);
    }
    for (const [n, g] of badgeNodes) {
      const lit = litAt.get(n);
      const notYet = !!sl && (!lit || sliceIndex.get(lit) > sliceIndex.get(sl.id));
      g.classList.toggle('dim', (!!step && n !== state.step) || notYet);
    }
    extraLayer.innerHTML = '';
    if (state.actual && D.actual) {
      for (const x of D.actual.extra) {
        const a = M.get(x.from);
        const b = M.get(x.to);
        const g = el('g', { class: 'edge act-extra' }, extraLayer);
        el('path', { d: d([clip(a, center(b)), clip(b, center(a))]), class: 'ln', 'marker-end': 'url(#arr-bad)' }, g);
        const title = el('title', {}, g);
        title.textContent = `图上没有的调用：${x.from} → ${x.to}`;
      }
    }
    document.querySelectorAll('#steps button').forEach((b) => b.setAttribute('aria-pressed', String(Number(b.dataset.step) === state.step && !(state.step === 0 && state.slice))));
    document.querySelectorAll('#slices button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.slice === state.slice)));
    const t = document.getElementById('actual-toggle');
    t.setAttribute('aria-pressed', String(state.actual));
    const rt = document.getElementById('rev-toggle');
    if (rt) rt.setAttribute('aria-pressed', String(showRev));
  }

  // ---------- 右侧面板 ----------
  const panel = document.getElementById('panel');
  function sectionHtml(id) {
    const s = D.sections[id];
    if (!s) return '<div class="problems">SPEC.md 里没有这一节。</div>';
    return `<p class="spec-src">SPEC.md 第 ${s.line} 行起的原文</p><div class="md">${md(s.body)}</div>`;
  }
  function edgeLine(e, dir) {
    const other = dir === 'out' ? e.to : e.from;
    return `<li>${dir === 'out' ? '→' : '←'} ${refBtn(other)} ${esc(nameOf(other))} <span class="via">· ${esc(e.label)}</span></li>`;
  }
  function overview() {
    const failed = D.checks.filter((c) => !c.ok);
    const okCount = D.checks.length - failed.length;
    const revHtml = REV ? `<div class="revision">
        <h3>这一版改了什么（${esc(REV.from)} → ${esc(REV.version)}）</h3>
        <p><strong>${esc(REV.title)}</strong></p>
        <ol>${REV.items.map((it) => `<li>${esc(it.text)}<div class="rev-refs">${it.refs.map(anyRef).join(' ')}</div></li>`).join('')}</ol>
        <p class="spec-src">图上橙色虚线框、橙色箭头和"新""改"标记就是这些改动。点上方"标出本版改动"可以关掉。</p>
      </div>` : '';
    return `${revHtml}<h2>如何审阅</h2>
      <div class="big-status ${failed.length ? 'bad' : 'ok'}"><strong>${okCount}/${D.checks.length}</strong><span>项一致性检查通过</span></div>
      <ol class="howto">
        <li>看图：每个方框右上角都应是绿色对勾。红色感叹号表示文字和图对不上，点开能看到具体哪里不一致。</li>
        <li>点方框：右侧显示 SPEC.md 里这个模块的原文，以及图上它调用谁、被谁调用、由哪些验收场景证明。只需判断原文和你心里的设计是否一致。</li>
        <li>点上方 ① 到 ${CIRCLED[model.flow.length]}：图上会只亮出这一步经过的模块和箭头，用来核对${esc(FLOW)}。</li>
        <li>点上方"切片 1"到"切片 ${model.slices.length}"：蓝色粗框是这个切片新建的模块，淡色是后面的切片才做的。每个切片做完都能跑一条演示命令。</li>
        <li>施工后：打开"对比实际代码"，绿色是代码已按图实现，灰色虚线是还没实现，红色是图上没有的多余调用。</li>
      </ol>
      <h3>图上有</h3>
      <div class="chips"><span class="chip">${model.modules.length} 个模块</span><span class="chip">${model.edges.length} 根箭头</span><span class="chip">${model.invariants.length} 条不变量</span><span class="chip">${model.acceptance.length} 个验收场景</span><span class="chip">${model.slices.length} 个施工切片</span></div>`;
  }
  function modulePanel(id) {
    const m = M.get(id);
    const st = D.moduleStatus[id];
    const outs = model.edges.filter((e) => e.from === id);
    const ins = model.edges.filter((e) => e.to === id);
    const ats = model.acceptance.filter((a) => a.covers.includes(id));
    const invs = model.invariants.filter((inv) => inv.verifiedBy.some((a) => ats.some((x) => x.id === a)));
    return `<h2>${esc(m.name)}</h2>
      <p class="idline">${esc(m.id)} · ${esc(LAYER.get(m.layer).name)} · ${esc(m.owner)}${m.dir ? ' · ' + esc(m.dir) : ''}</p>
      <div class="chips">
        <span class="chip ${D.sections[id] ? 'ok' : 'bad'}">${D.sections[id] ? '✓ 有规格章节' : '✗ 缺规格章节'}</span>
        <span class="chip ${st.ok ? 'ok' : 'bad'}">${st.ok ? '✓ 文字与图一致' : `✗ ${st.problems.length} 处不一致`}</span>
        <span class="chip ${ats.length ? 'ok' : 'bad'}">${ats.length ? `✓ ${ats.length} 个验收覆盖` : '✗ 没有验收'}</span>
        ${builtAt.has(id) ? `<span class="chip">在 ${refBtn(builtAt.get(id))} 新建</span>` : ''}
        ${revChip(id)}
      </div>
      ${revNote(id)}
      ${st.ok ? '' : `<div class="problems"><ul>${st.problems.map((p) => `<li>${inline(p)}</li>`).join('')}</ul></div>`}
      <h3>图上：它调用</h3>
      ${outs.length ? `<ul class="links">${outs.map((e) => edgeLine(e, 'out')).join('')}</ul>` : '<p class="spec-src">不调用其他模块</p>'}
      <h3>图上：谁调用它</h3>
      ${ins.length ? `<ul class="links">${ins.map((e) => edgeLine(e, 'in')).join('')}</ul>` : '<p class="spec-src">没有调用方</p>'}
      <h3>由这些验收证明</h3>
      ${ats.length ? `<ul class="links">${ats.map((a) => `<li>${refBtn(a.id)} ${esc(a.name)}</li>`).join('')}</ul>` : '<p class="spec-src">无</p>'}
      ${invs.length ? `<h3>相关不变量</h3><ul class="links">${invs.map((x) => `<li>${refBtn(x.id)} ${esc(x.text)}</li>`).join('')}</ul>` : ''}
      <h3>规格原文</h3>
      ${sectionHtml(id)}`;
  }
  function edgePanel(id) {
    const e = E.get(id);
    const info = D.edgeInfo[id];
    const kind = KIND.get(e.kind);
    let actualLine = '';
    if (D.actual && D.actual.edgeStatus[id]) {
      actualLine = D.actual.edgeStatus[id] === 'ok'
        ? '<span class="chip ok">✓ 代码里已有这条调用</span>'
        : '<span class="chip">代码里还没有这条调用</span>';
    }
    return `<h2>${esc(nameOf(e.from))} → ${esc(nameOf(e.to))}</h2>
      <p class="idline">${esc(e.id)} · ${esc(kind ? kind.name : e.kind)}</p>
      <p>${esc(e.label)}</p>
      <div class="chips">
        <span class="chip ${info.inSpec ? 'ok' : 'bad'}">${info.inSpec ? '✓ 文字里写了这条调用' : '✗ 文字里没写这条调用'}</span>
        ${actualLine}
        ${revChip(id)}
      </div>
      ${revNote(id)}
      <h3>怎么保证代码照此实现</h3>
      <p>${info.guard === 'arch'
        ? `依赖检查规则 <code>${esc(info.rule || '')}</code>：<code>${esc(D.archCommand || '架构检查')}</code> 会拒绝图上没画的 import。`
        : '这类关系不是 import，由运行时测试证明：'}</p>
      ${info.ats.length ? `<ul class="links">${info.ats.map((a) => `<li>${refBtn(a)} ${esc(AT.get(a).name)}</li>`).join('')}</ul>` : ''}
      ${info.steps.length ? `<h3>属于${esc(FLOW)}</h3><ul class="links">${info.steps.map((n) => `<li><button type="button" class="ref" data-step="${n}">${CIRCLED[n]}</button> ${esc(STEP.get(n).title)}</li>`).join('')}</ul>` : ''}
      <h3>两端模块</h3>
      <ul class="links"><li>${refBtn(e.from)} ${esc(nameOf(e.from))}</li><li>${refBtn(e.to)} ${esc(nameOf(e.to))}</li></ul>`;
  }
  // ---------- 协议时序：flow 里某一步可选的 detail 和 sequence ----------
  const SEQ_KIND = {
    spawn: '启动进程',
    request: '请求（要回复）',
    response: '回复',
    notify: '通知（不回复）',
    local: '进程内调用或非协议交互',
  };
  const SEQ_H = 22;
  const SEQ_Y = 11;
  function seqArrow(x1, x2, kind, w) {
    let g = '';
    if (x1 === x2) {
      // 自己做的事：在生命线右侧画一个小回环
      g = `<path class="seq-ln" d="M${x1},5 h16 v12 h-9"/><path class="seq-head" d="M${x1 + 1},17 l7,-4 v8 z"/>`;
    } else {
      const dir = x2 > x1 ? 1 : -1;
      const tip = x2 - dir * 1.5;
      const base = x2 - dir * 9;
      g = `<line class="seq-ln" x1="${x1}" y1="${SEQ_Y}" x2="${base + dir}" y2="${SEQ_Y}"/>`;
      g += kind === 'notify'
        ? `<path class="seq-head open" d="M${base},${SEQ_Y - 4.5} L${tip},${SEQ_Y} L${base},${SEQ_Y + 4.5}"/>`
        : `<path class="seq-head" d="M${tip},${SEQ_Y} L${base},${SEQ_Y - 4.5} L${base},${SEQ_Y + 4.5} z"/>`;
      if (kind === 'spawn') g += `<circle class="seq-head" cx="${x1}" cy="${SEQ_Y}" r="3"/>`;
    }
    return `<svg class="seq-arrow k-${kind}" width="${w}" height="${SEQ_H}" aria-hidden="true">${g}</svg>`;
  }
  function seqHtml(seq) {
    const parts = seq.participants;
    const gap = parts.length <= 3 ? 56 : parts.length === 4 ? 50 : 44;
    const pad = 24;
    const w = pad * 2 + gap * (parts.length - 1);
    const X = new Map(parts.map((p, i) => [p.id, pad + i * gap]));
    const label = (p) => p.name || (M.get(p.id) || {}).name || p.id;
    const head = parts.map((p) => {
      const m = M.get(p.id);
      const style = m ? ` style="background:var(--lc-${m.layer});border-color:var(--lc-${m.layer}-s)"` : '';
      return `<span class="seq-p${m ? '' : ' ext'}"${style} title="${esc(m ? `${p.id} · ${m.name}` : label(p))}">${esc(label(p))}</span>`;
    });
    const lanes = `<div class="seq-lanes" style="width:${w}px">${head.map((h, i) => `<div class="seq-pcell" style="left:${pad + i * gap}px">${h}</div>`).join('')}</div>`;
    const life = `<svg class="seq-life" width="${w}" aria-hidden="true">${parts.map((p) => `<line x1="${X.get(p.id)}" x2="${X.get(p.id)}" y1="0" y2="100%"/>`).join('')}</svg>`;
    let no = 0;
    const rows = seq.messages.map((msg) => {
      if (msg.section) return `<li class="seq-sec">${inline(msg.section)}</li>`;
      no += 1;
      return `<li class="seq-row k-${msg.kind}">${seqArrow(X.get(msg.from), X.get(msg.to), msg.kind, w)}<div class="seq-msg"><span class="seq-no">${no}</span><div><div class="seq-text">${inline(msg.text)}</div>${msg.note ? `<div class="seq-note">${inline(msg.note)}</div>` : ''}</div></div></li>`;
    }).join('');
    const kinds = [...new Set(seq.messages.filter((x) => !x.section).map((x) => x.kind))];
    const kindLegend = kinds.map((k) => `<span>${seqArrow(4, 34, k, 40).replace('class="seq-arrow', 'class="seq-arrow mini')}${esc(SEQ_KIND[k] || k)}</span>`).join('');
    const who = parts.filter((p) => M.has(p.id)).map((p) => `<li>${esc(label(p))} = ${refBtn(p.id)} ${esc(M.get(p.id).name)}</li>`).join('');
    return `<div class="seq" style="--seq-w:${w}px">
        <div class="seq-headrow">${lanes}<div></div></div>
        <div class="seq-wrap">${life}<ol class="seq-body">${rows}</ol></div>
      </div>
      <div class="seq-legend">${kindLegend}</div>
      ${who ? `<ul class="links seq-who">${who}</ul>` : ''}`;
  }
  const detailHtml = (s) => (s.detail ? [].concat(s.detail).map((p) => `<p class="step-detail">${inline(p)}</p>`).join('') : '');

  function stepPanel(n) {
    const s = STEP.get(n);
    const ats = model.acceptance.filter((a) => a.flowSteps.includes(n));
    let traceHtml = '';
    if (D.trace) {
      const seen = [...new Set(D.trace.filter((ev) => ev.step === n).map((ev) => ev.module))];
      const expected = [...new Set(s.edges.flatMap((id) => [E.get(id).from, E.get(id).to]))];
      const missing = expected.filter((x) => !seen.includes(x));
      const later = (x) => builtAt.has(x) && D.trace.every((ev) => ev.module !== x) ? `（${refBtn(builtAt.get(x))} 才建）` : '';
      // 轨迹来自哪个切片的验收；后续切片才建的模块没经过是正常的
      const srcSlice = model.slices.find((sl) => sl.ats.includes(D.traceSource));
      const srcIdx = srcSlice ? sliceIndex.get(srcSlice.id) : Infinity;
      const notYet = (x) => builtAt.has(x) && sliceIndex.get(builtAt.get(x)) > srcIdx;
      const realMissing = missing.filter((x) => !notYet(x));
      const chip = realMissing.length
        ? `<span class="chip bad">✗ 还有 ${realMissing.length} 个模块没经过</span>`
        : missing.length
          ? `<span class="chip ok">✓ 当前切片该经过的都经过了</span><span class="chip">${missing.length} 个模块在后续切片</span>`
          : '<span class="chip ok">✓ 与图一致</span>';
      traceHtml = `<h3>实际运行轨迹${D.traceSource ? `（来自 ${refBtn(D.traceSource)}）` : ''}</h3>
        <div class="chips">${chip}</div>
        <p>${seen.length ? seen.map(refBtn).join(' → ') : '这一步没有记录到事件'}</p>
        ${missing.length ? `<p class="spec-src">没经过：${missing.map((x) => refBtn(x) + later(x)).join(' ')}</p>` : ''}`;
    }
    return `<h2>${CIRCLED[n]} ${esc(s.title)}</h2>
      <p class="idline">${esc(FLOW)}第 ${n} 步${litAt.has(n) ? ` · 在 ${refBtn(litAt.get(n))} 亮起` : ''}</p>
      ${detailHtml(s)}
      ${s.sequence ? `<h3>${esc(s.sequence.title || '协议时序')}</h3>${seqHtml(s.sequence)}` : ''}
      <h3>经过的箭头</h3>
      <ul class="links">${s.edges.map((id) => { const e = E.get(id); return `<li>${refBtn(e.from)} → ${refBtn(e.to)} <span class="via">· ${esc(e.label)}</span></li>`; }).join('')}</ul>
      <h3>由这些验收证明</h3>
      ${ats.length ? `<ul class="links">${ats.map((a) => `<li>${refBtn(a.id)} ${esc(a.name)}</li>`).join('')}</ul>` : '<div class="problems">没有验收覆盖这一步</div>'}
      ${traceHtml || '<p class="spec-src">施工完成并跑过 AT-1 后，这里会显示实际运行轨迹，用来和图对比。</p>'}`;
  }
  function docPanel(id) {
    const inv = INV.get(id);
    const at = AT.get(id);
    let head = '';
    if (inv) head = `<h2>${esc(inv.text)}</h2><p class="idline">${esc(id)} · 不变量</p><div class="chips">${inv.verifiedBy.map((a) => `<span class="chip">由 ${refBtn(a)} 证明</span>`).join('')}</div>`;
    if (at) head = `<h2>${esc(at.name)}</h2><p class="idline">${esc(id)} · 验收场景</p><div class="chips">${at.covers.length ? `<span class="chip">覆盖 ${at.covers.length} 个模块</span>` : '<span class="chip">全局检查</span>'}${at.flowSteps.length ? `<span class="chip">覆盖流程 ${at.flowSteps.map((n) => CIRCLED[n]).join('')}</span>` : ''}</div>`;
    return `${head}${revChip(id) ? `<div class="chips">${revChip(id)}</div>${revNote(id)}` : ''}<h3>规格原文</h3>${sectionHtml(id)}`;
  }
  function slicePanel(id) {
    const sl = SL.get(id);
    const idx = sliceIndex.get(id);
    const newMods = model.modules.filter((m) => builtAt.get(m.id) === id);
    const litSoFar = model.flow.filter((s) => litAt.has(s.n) && sliceIndex.get(litAt.get(s.n)) <= idx);
    return `<h2>${esc(sl.name)}</h2>
      <p class="idline">${esc(id)} · 第 ${idx + 1} 个切片，共 ${model.slices.length} 个</p>
      <div class="chips">
        <span class="chip">新建 ${newMods.length} 个模块</span>
        <span class="chip">${sl.steps.length ? `新亮起 ${circled(sl.steps)}` : '不新增流程'}</span>
        <span class="chip">流程已亮 ${litSoFar.length}/${model.flow.length}</span>
        ${revChip(id)}
      </div>
      ${revNote(id)}
      <p class="spec-src">图上：蓝色粗框是这个切片新建的模块，正常显示的是之前切片已建好的，淡色是后面的切片才做的。</p>
      <h3>做完后跑这条命令看结果</h3>
      <pre class="demo"><code>${esc(sl.demo)}</code></pre>
      <h3>由这些验收证明</h3>
      <ul class="links">${sl.ats.map((a) => `<li>${refBtn(a)} ${esc(AT.get(a).name)}</li>`).join('')}</ul>
      <h3>这个切片新建的模块</h3>
      ${newMods.length ? `<ul class="links">${newMods.map((m) => `<li>${refBtn(m.id)} ${esc(m.name)}</li>`).join('')}</ul>` : '<p class="spec-src">不新建模块，只加固已有模块</p>'}
      <h3>规格原文</h3>
      ${sectionHtml(id)}`;
  }
  function renderPanel() {
    let html;
    if (state.sel && state.sel.type === 'module') html = modulePanel(state.sel.id);
    else if (state.sel && state.sel.type === 'edge') html = edgePanel(state.sel.id);
    else if (state.sel && state.sel.type === 'doc') html = docPanel(state.sel.id);
    else if (state.step) html = stepPanel(state.step);
    else if (state.slice) html = slicePanel(state.slice);
    else html = overview();
    const back = state.sel || state.step || state.slice ? '<p><button type="button" class="ref" data-home="1">← 返回审阅说明</button></p>' : '';
    panel.innerHTML = back + html;
    panel.scrollTop = 0;
  }
  panel.addEventListener('click', (ev) => {
    const btn = ev.target.closest('button');
    if (!btn) return;
    if (btn.dataset.home) { state.sel = null; state.step = 0; state.slice = ''; }
    else if (btn.dataset.step) { state.sel = null; state.slice = ''; state.step = Number(btn.dataset.step); }
    else if (btn.dataset.edgeref) state.sel = { type: 'edge', id: btn.dataset.edgeref };
    else if (btn.dataset.ref) {
      const id = btn.dataset.ref;
      if (SL.has(id)) { state.sel = null; state.step = 0; state.slice = id; }
      else state.sel = M.has(id) ? { type: 'module', id } : { type: 'doc', id };
    }
    applyHighlight();
    renderPanel();
  });

  function select(sel) {
    state.sel = sel;
    applyHighlight();
    renderPanel();
    if (window.matchMedia('(max-width: 1100px)').matches) panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  function setStep(n) {
    state.step = state.step === n ? 0 : n;
    state.slice = '';
    state.sel = null;
    applyHighlight();
    renderPanel();
  }
  function setSlice(id) {
    state.slice = state.slice === id ? '' : id;
    state.step = 0;
    state.sel = null;
    applyHighlight();
    renderPanel();
  }

  // ---------- 其他区域 ----------
  function titleBlock() {
    const failed = D.checks.filter((c) => !c.ok).length;
    const rows = [
      ['图号', model.drawingNo],
      ['版本', model.version],
      ['生成', D.generatedAt.replace('T', ' ').slice(0, 16) + ' UTC'],
      ['一致性', failed ? `${failed} 项未通过` : `全部 ${D.checks.length} 项通过`],
      ['代码对比', D.actual ? `已读取 ${D.actual.files} 个文件` : '尚未施工'],
    ];
    document.getElementById('titleblock').innerHTML = rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
  }
  function toolbar() {
    const steps = document.getElementById('steps');
    steps.innerHTML = `<button type="button" data-step="0" aria-pressed="true">全部</button>` +
      model.flow.map((s) => `<button type="button" data-step="${s.n}" aria-pressed="false" title="${esc(s.title)}">${CIRCLED[s.n]} ${esc(s.title.length > 8 ? s.title.slice(0, 8) + '…' : s.title)}</button>`).join('');
    steps.addEventListener('click', (ev) => {
      const b = ev.target.closest('button');
      if (!b) return;
      const n = Number(b.dataset.step);
      if (n === 0) { state.step = 0; state.slice = ''; state.sel = null; applyHighlight(); renderPanel(); } else setStep(n);
    });
    const slices = document.getElementById('slices');
    slices.innerHTML = model.slices.map((sl) => `<button type="button" data-slice="${esc(sl.id)}" aria-pressed="false" title="${esc(sl.name)}">切片 ${sliceNo(sl.id)} · ${esc(shortName(sl))}</button>`).join('');
    slices.addEventListener('click', (ev) => {
      const b = ev.target.closest('button');
      if (b) setSlice(b.dataset.slice);
    });
    const rt = document.getElementById('rev-toggle');
    if (rt && REV) {
      rt.hidden = false;
      rt.textContent = `标出本版改动（${REV.version}）`;
      rt.addEventListener('click', () => {
        const visible = state.rev && !state.step && !state.slice && !state.actual;
        if (visible) state.rev = false;
        else { state.rev = true; state.step = 0; state.slice = ''; state.actual = false; }
        applyHighlight();
        renderPanel();
      });
    }
    const t = document.getElementById('actual-toggle');
    if (D.actual) {
      t.textContent = '对比实际代码';
      t.addEventListener('click', () => { state.actual = !state.actual; applyHighlight(); });
    } else {
      t.textContent = '对比实际代码（施工后可用）';
      t.disabled = true;
    }
  }
  function checksList() {
    document.getElementById('checks').innerHTML = D.checks.map((c) => `<li>
      <span class="state ${c.ok ? 'ok' : 'bad'}">${c.ok ? '通过' : '未通过'}</span>
      <div><div class="t">${esc(c.title)}</div><div class="e">${esc(c.explain)}</div>
      ${c.problems.length ? `<ul>${c.problems.map((p) => `<li>${inline(p)}</li>`).join('')}</ul>` : ''}</div>
    </li>`).join('');
  }
  function invTable() {
    document.getElementById('inv-table').innerHTML = `<thead><tr><th>编号</th><th>绝不能发生</th><th>由谁证明</th></tr></thead><tbody>${model.invariants.map((x) =>
      `<tr><td>${refBtn(x.id)}</td><td>${esc(x.text)} ${revChip(x.id)}</td><td>${x.verifiedBy.map(refBtn).join(' ')}</td></tr>`).join('')}</tbody>`;
  }
  function sliceList() {
    document.getElementById('phases').innerHTML = model.slices.map((p) => `<li>
      <div class="ph-head">${refBtn(p.id)}<span class="ph-name">${esc(p.name)} ${revChip(p.id)}</span><span class="ph-steps">${p.steps.length ? `亮起 ${circled(p.steps)}` : '不新增流程'}</span></div>
      <div class="ph-demo"><code>${esc(p.demo)}</code></div>
      <div class="ph-ats">${p.ats.map((a) => `<span>${refBtn(a)} ${esc(AT.get(a).name)} ${revChip(a)}</span>`).join('')}</div>
    </li>`).join('');
  }
  document.addEventListener('click', (ev) => {
    const btn = ev.target.closest('.report .ref[data-ref]');
    if (!btn) return;
    const id = btn.dataset.ref;
    if (SL.has(id)) {
      setSlice(id);
      if (state.slice !== id) setSlice(id);
      document.querySelector('.toolbar').scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    select(M.has(id) ? { type: 'module', id } : { type: 'doc', id });
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  document.getElementById('foot').textContent = `由 design/tools/build.mjs 根据 design/architecture.json 和 design/SPEC.md 生成。改图或改文字后重新运行即可更新本页。`;

  titleBlock();
  toolbar();
  drawDiagram();
  legend();
  checksList();
  invTable();
  sliceList();
  applyHighlight();
  renderPanel();
})();
