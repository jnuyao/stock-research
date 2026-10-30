#!/usr/bin/env node
// 施工蓝图生成器（blueprint-kit）。从 architecture.json 生成审阅页和 Mermaid 图，并检查 SPEC.md、CLAUDE.md 是否与图一致。
// 代码 import 检查按 architecture.json 的 arch.tool 选择：
//   "python"     由 design/tools/arch_check.py 直接读图检查（只用标准库）
//   "depcruise"  本脚本生成 design/generated/depcruise.cjs，交给 dependency-cruiser 检查（TS/JS 项目）
//   "none"       不检查代码
// 用法：
//   node design/tools/build.mjs                       生成全部产物
//   node design/tools/build.mjs --check               生成并检查，不一致时退出码为 1
//   node design/tools/build.mjs --actual <json>       叠加实际依赖（arch_check.py --json 或 depcruise --output-type json 的输出）
//   node design/tools/build.mjs --artifact-out <html> 另外输出一份不含 <html>/<head> 外壳的页面片段
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const designDir = resolve(here, '..');
const rootDir = resolve(designDir, '..');
const outDir = join(designDir, 'generated');

const args = process.argv.slice(2);
const hasFlag = (name) => args.includes(name);
const option = (name) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
};

const model = JSON.parse(readFileSync(join(designDir, 'architecture.json'), 'utf8'));
const specText = readFileSync(join(designDir, 'SPEC.md'), 'utf8');
const claudePath = join(rootDir, 'CLAUDE.md');
const claudeText = existsSync(claudePath) ? readFileSync(claudePath, 'utf8') : null;

const FLOW = model.flowName || '流程';
const ARCH = model.arch || { tool: 'none' };
const modules = new Map(model.modules.map((m) => [m.id, m]));
const edges = new Map(model.edges.map((e) => [e.id, e]));
const invariants = new Map(model.invariants.map((x) => [x.id, x]));
const acceptance = new Map(model.acceptance.map((x) => [x.id, x]));
const slices = new Map(model.slices.map((x) => [x.id, x]));
const knownIds = new Set([...modules.keys(), ...invariants.keys(), ...acceptance.keys(), ...slices.keys()]);

// ---------- 解析 SPEC.md ----------
const ID_RE = /\[([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)\]/g;

function parseSpec(md) {
  const sections = new Map();
  const duplicates = [];
  const refs = [];
  let current = null;
  let inFence = false;
  md.split('\n').forEach((line, index) => {
    if (/^\s*```/.test(line)) {
      inFence = !inFence;
      if (current) current.lines.push(line);
      return;
    }
    if (!inFence) {
      const heading = line.match(/^(#{2,3}) \[([A-Z][A-Z0-9-]*)\]\s*(.*)$/);
      if (heading) {
        current = { id: heading[2], title: heading[3].trim(), line: index + 1, lines: [] };
        if (sections.has(current.id)) duplicates.push(current.id);
        sections.set(current.id, current);
        refs.push({ id: heading[2], line: index + 1 });
        return;
      }
      if (/^#{1,3} /.test(line)) {
        current = null;
        return;
      }
      for (const m of line.replace(/`[^`]*`/g, '').matchAll(ID_RE)) refs.push({ id: m[1], line: index + 1 });
    }
    if (current) current.lines.push(line);
  });
  for (const s of sections.values()) {
    while (s.lines.length && s.lines[s.lines.length - 1].trim() === '') s.lines.pop();
    while (s.lines.length && s.lines[0].trim() === '') s.lines.shift();
    s.body = s.lines.join('\n');
  }
  return { sections, duplicates, refs };
}

// 读取章节里 "- 字段：..." 这一行中的编号；没有这一行时返回 null
function fieldIds(section, field) {
  if (!section) return null;
  let inFence = false;
  for (const line of section.lines) {
    if (/^\s*```/.test(line)) inFence = !inFence;
    if (inFence) continue;
    const m = line.match(new RegExp(`^- ${field}[：:](.*)$`));
    if (m) return [...m[1].matchAll(ID_RE)].map((x) => x[1]);
  }
  return null;
}

const spec = parseSpec(specText);

// ---------- 由图推导的关系 ----------
const outgoing = (id) => [...new Set(model.edges.filter((e) => e.from === id).map((e) => e.to))];
const atsCovering = (id) => model.acceptance.filter((a) => a.covers.includes(id)).map((a) => a.id);
const sameSet = (a, b) => a.length === b.length && a.every((x) => b.includes(x));
const diff = (a, b) => a.filter((x) => !b.includes(x));
const tag = (ids) => (ids.length ? ids.map((x) => `[${x}]`).join('、') : '无');

// ---------- 一致性检查 ----------
const checks = [];
const moduleProblems = new Map(model.modules.map((m) => [m.id, []]));
function addCheck(id, title, explain, problems) {
  checks.push({ id, title, explain, ok: problems.length === 0, problems: problems.map((p) => p.text) });
  for (const p of problems) if (p.module && moduleProblems.has(p.module)) moduleProblems.get(p.module).push(p.text);
}

{
  const problems = [];
  const seen = new Set();
  for (const m of model.modules) {
    if (seen.has(m.id)) problems.push({ text: `模块编号 [${m.id}] 重复` });
    seen.add(m.id);
    if (!model.layers.some((l) => l.id === m.layer)) problems.push({ module: m.id, text: `[${m.id}] 的分层 ${m.layer} 不存在` });
  }
  const edgeIds = new Set();
  for (const e of model.edges) {
    if (edgeIds.has(e.id)) problems.push({ text: `箭头编号 ${e.id} 重复` });
    edgeIds.add(e.id);
    if (!modules.has(e.from)) problems.push({ text: `箭头 ${e.id} 的起点 [${e.from}] 不存在` });
    if (!modules.has(e.to)) problems.push({ text: `箭头 ${e.id} 的终点 [${e.to}] 不存在` });
    if (!model.edgeKinds.some((k) => k.id === e.kind)) problems.push({ text: `箭头 ${e.id} 的类型 ${e.kind} 不存在` });
  }
  const SEQ_KINDS = ['spawn', 'request', 'response', 'notify', 'local'];
  const textRefs = (str) => [...String(str || '').replace(/`[^`]*`/g, '').matchAll(ID_RE)].map((x) => x[1]);
  for (const step of model.flow) {
    for (const id of step.edges) if (!edges.has(id)) problems.push({ text: `流程第 ${step.n} 步引用的箭头 ${id} 不存在` });
    if (!step.edges.includes(step.badgeEdge)) problems.push({ text: `流程第 ${step.n} 步的编号标记不在它自己的箭头上` });
    const texts = [].concat(step.detail || []);
    const seq = step.sequence;
    if (seq) {
      const parts = seq.participants || [];
      const pids = new Set();
      if (parts.length < 2 || parts.length > 5) problems.push({ text: `流程第 ${step.n} 步的时序图要有 2 到 5 个参与者` });
      for (const p of parts) {
        if (pids.has(p.id)) problems.push({ text: `流程第 ${step.n} 步的时序图参与者 ${p.id} 重复` });
        pids.add(p.id);
        if (!modules.has(p.id) && !p.name) problems.push({ text: `流程第 ${step.n} 步的时序图参与者 ${p.id} 不是图上的模块，需要写 name` });
      }
      for (const [i, msg] of (seq.messages || []).entries()) {
        if (msg.section) { texts.push(msg.section); continue; }
        const at = `流程第 ${step.n} 步时序图第 ${i + 1} 行`;
        if (!pids.has(msg.from) || !pids.has(msg.to)) problems.push({ text: `${at}的两端 ${msg.from} → ${msg.to} 不在参与者里` });
        if (!SEQ_KINDS.includes(msg.kind)) problems.push({ text: `${at}的类型 ${msg.kind} 不存在（可用：${SEQ_KINDS.join('、')}）` });
        texts.push(msg.text, msg.note);
      }
    }
    for (const ref of texts.flatMap(textRefs)) if (!knownIds.has(ref)) problems.push({ text: `流程第 ${step.n} 步的说明引用了不存在的 [${ref}]` });
  }
  for (const x of [...model.invariants, ...model.acceptance, ...model.slices]) {
    for (const ref of [...(x.verifiedBy || []), ...(x.covers || []), ...(x.ats || [])]) {
      if (!knownIds.has(ref)) problems.push({ text: `[${x.id}] 引用了不存在的 [${ref}]` });
    }
  }
  addCheck('C0', '图本身没有断线', '每根箭头两端的模块都存在，编号不重复；流程的时序图只引用存在的参与者。', problems);
}

{
  const problems = [];
  for (const m of model.modules) {
    if (!spec.sections.has(m.id)) problems.push({ module: m.id, text: `[${m.id}] ${m.name} 在 SPEC.md 里没有章节` });
  }
  for (const id of spec.duplicates) problems.push({ module: id, text: `SPEC.md 里 [${id}] 章节出现了不止一次` });
  addCheck('C1', '图上每个模块都有文字说明', '每个方框在 SPEC.md 里都有一个同编号的章节。', problems);
}

{
  const problems = [];
  const unknown = new Map();
  for (const r of spec.refs) if (!knownIds.has(r.id)) unknown.set(r.id, r.line);
  for (const [id, line] of unknown) problems.push({ text: `SPEC.md 第 ${line} 行提到的 [${id}] 在图上不存在` });
  addCheck('C2', '文字里没有图上不存在的东西', 'SPEC.md 中出现的每个编号都能在图上找到。', problems);
}

{
  const problems = [];
  for (const m of model.modules) {
    const section = spec.sections.get(m.id);
    if (!section) continue;
    const written = fieldIds(section, '调用');
    const drawn = outgoing(m.id);
    if (written === null) {
      problems.push({ module: m.id, text: `[${m.id}] 的章节缺少"- 调用："这一行（图上是：${tag(drawn)}）` });
      continue;
    }
    for (const x of diff(written, drawn)) problems.push({ module: m.id, text: `[${m.id}] 的文字写了调用 [${x}]，图上没有这根箭头` });
    for (const x of diff(drawn, written)) problems.push({ module: m.id, text: `图上有 [${m.id}] → [${x}]，文字里没写` });
  }
  addCheck('C3', '文字写的调用关系与箭头完全一致', '每个模块章节的"调用"一行，与图上从它出发的箭头逐一对应。', problems);
}

{
  const problems = [];
  for (const m of model.modules) {
    const section = spec.sections.get(m.id);
    if (!section) continue;
    const written = fieldIds(section, '验收');
    const expected = atsCovering(m.id);
    if (written === null) {
      problems.push({ module: m.id, text: `[${m.id}] 的章节缺少"- 验收："这一行（应为：${tag(expected)}）` });
      continue;
    }
    if (!sameSet(written, expected)) problems.push({ module: m.id, text: `[${m.id}] 的文字写的验收是 ${tag(written)}，按图应为 ${tag(expected)}` });
  }
  for (const a of model.acceptance) {
    const section = spec.sections.get(a.id);
    if (!section) { problems.push({ text: `验收场景 [${a.id}] ${a.name} 在 SPEC.md 里没有章节` }); continue; }
    const written = fieldIds(section, '覆盖');
    if (written === null) problems.push({ text: `[${a.id}] 的章节缺少"- 覆盖："这一行` });
    else if (!sameSet(written, a.covers)) problems.push({ text: `[${a.id}] 的文字写的覆盖范围是 ${tag(written)}，图上是 ${tag(a.covers)}` });
  }
  addCheck('C4', '验收场景的覆盖范围与图一致', '模块章节的"验收"、验收章节的"覆盖"，都与 architecture.json 对得上。', problems);
}

{
  const problems = [];
  for (const inv of model.invariants) {
    const section = spec.sections.get(inv.id);
    if (!section) { problems.push({ text: `不变量 [${inv.id}] 在 SPEC.md 里没有章节` }); continue; }
    if (!/^- 检查[：:]\s*\S/m.test(section.body)) problems.push({ text: `[${inv.id}] 没有写明怎么检查` });
    const written = fieldIds(section, '验收');
    if (written === null || !sameSet(written, inv.verifiedBy)) problems.push({ text: `[${inv.id}] 的文字写的验收是 ${tag(written || [])}，图上是 ${tag(inv.verifiedBy)}` });
  }
  addCheck('C5', '每条不变量都有检查方法和验收', '"绝不能发生的事"都写明了用什么测试来证明。', problems);
}

{
  const problems = [];
  for (const m of model.modules) {
    if (atsCovering(m.id).length === 0) problems.push({ module: m.id, text: `[${m.id}] ${m.name} 没有任何验收场景覆盖` });
  }
  const coveredSteps = new Set(model.acceptance.flatMap((a) => a.flowSteps));
  for (const step of model.flow) if (!coveredSteps.has(step.n)) problems.push({ text: `流程第 ${step.n} 步没有验收场景覆盖` });
  addCheck('C6', '每个模块和每一步流程都有验收', '图上没有"写了但没人测"的部分。', problems);
}

{
  const problems = [];
  const planned = model.slices.flatMap((p) => p.ats);
  for (const a of model.acceptance) if (!planned.includes(a.id)) problems.push({ text: `验收场景 [${a.id}] 没有排进任何施工切片` });
  for (const id of new Set(planned)) if (planned.filter((x) => x === id).length > 1) problems.push({ text: `验收场景 [${id}] 排进了不止一个切片` });
  for (const p of model.slices) {
    const section = spec.sections.get(p.id);
    if (!section) { problems.push({ text: `施工切片 [${p.id}] 在 SPEC.md 里没有章节` }); continue; }
    const written = fieldIds(section, '验收');
    if (written === null || !sameSet(written, p.ats)) problems.push({ text: `[${p.id}] 的文字写的验收是 ${tag(written || [])}，图上是 ${tag(p.ats)}` });
  }
  addCheck('C7', '每个验收都排进了施工切片', '施工顺序覆盖全部验收场景，每个验收只在一个切片里。', problems);
}

// 切片：亮起的流程要有验收证明，验收用到的流程要已经亮起，每个切片都有演示命令
const CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩';
const circled = (ns) => (ns.length ? ns.map((n) => CIRCLED[n - 1]).join('') : '无');
function fieldLine(section, field) {
  if (!section) return null;
  const line = section.lines.find((l) => new RegExp(`^- ${field}[：:]`).test(l));
  return line === undefined ? null : line.replace(new RegExp(`^- ${field}[：:]\\s*`), '');
}
{
  const problems = [];
  const litBy = new Map();
  const lit = new Set();
  const proven = new Set();
  for (const p of model.slices) {
    for (const n of p.steps) {
      if (!model.flow.some((s) => s.n === n)) problems.push({ text: `[${p.id}] 亮起的第 ${n} 步不在流程里` });
      if (litBy.has(n)) problems.push({ text: `流程第 ${n} 步在 [${litBy.get(n)}] 和 [${p.id}] 都写了亮起` });
      litBy.set(n, p.id);
      lit.add(n);
    }
    for (const a of p.ats) for (const n of acceptance.get(a)?.flowSteps || []) proven.add(n);
    for (const n of p.steps) if (!proven.has(n)) problems.push({ text: `[${p.id}] 亮起了第 ${n} 步，但到这个切片为止没有验收场景证明它` });
    for (const a of p.ats) for (const n of acceptance.get(a)?.flowSteps || []) {
      if (!lit.has(n)) problems.push({ text: `[${p.id}] 的验收 [${a}] 要跑第 ${n} 步，但这一步到这个切片还没亮起` });
    }
    const section = spec.sections.get(p.id);
    if (!section) continue;
    const litLine = fieldLine(section, '亮起的流程');
    if (litLine === null) problems.push({ text: `[${p.id}] 的章节缺少"- 亮起的流程："这一行（应为：${circled(p.steps)}）` });
    else {
      const written = [...litLine].map((c) => CIRCLED.indexOf(c) + 1).filter((n) => n > 0);
      if (!sameSet(written, p.steps)) problems.push({ text: `[${p.id}] 的文字写的亮起流程是 ${circled(written)}，图上是 ${circled(p.steps)}` });
    }
    const demoLine = fieldLine(section, '演示');
    if (!p.demo) problems.push({ text: `[${p.id}] 在图上没有演示命令` });
    else if (demoLine === null || !demoLine.includes('`' + p.demo + '`')) problems.push({ text: `[${p.id}] 的文字里没有写演示命令 \`${p.demo}\`` });
  }
  for (const s of model.flow) if (!lit.has(s.n)) problems.push({ text: `流程第 ${s.n} 步没有排进任何切片` });
  addCheck('C11', '每个切片都能跑通、能演示', '切片亮起的流程都有验收证明，验收要跑的流程都已亮起，每个切片写明了演示命令。', problems);
}

{
  const problems = [];
  const codeModules = model.modules.filter((m) => m.code);
  for (const a of codeModules) {
    if (!a.dir) problems.push({ module: a.id, text: `[${a.id}] 是代码模块但没有代码目录` });
    for (const b of codeModules) {
      if (a !== b && a.dir && b.dir && b.dir.startsWith(a.dir)) problems.push({ module: a.id, text: `[${a.id}] 的目录 ${a.dir} 包含了 [${b.id}] 的目录 ${b.dir}` });
    }
  }
  addCheck('C8', '每个代码模块有独立目录', '方框与代码目录一一对应，才能自动检查箭头。', problems);
}

// ---------- 依赖检查规则（dependency-cruiser） ----------
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
function depcruiseConfig() {
  const roots = ARCH.roots || ['src'];
  const rootsRe = `^(${roots.map(escapeRe).join('|')})/`;
  const srcRoot = ARCH.srcRoot || 'src/';
  const forbidden = [];
  const codeModules = model.modules.filter((m) => m.code && m.dir);
  for (const m of codeModules) {
    const isPlugin = Boolean(ARCH.pluginDir && model.sharedDirs.plugin && m.dir.startsWith(ARCH.pluginDir));
    const allowed = [m.dir, isPlugin ? model.sharedDirs.plugin : model.sharedDirs.host];
    for (const e of model.edges) {
      if (e.from === m.id && e.kind === 'call') {
        const target = modules.get(e.to);
        if (target && target.dir) allowed.push(target.dir);
      }
    }
    forbidden.push({
      name: `only-drawn-calls-${m.id}`,
      comment: `[${m.id}] ${m.name} 只能调用图上画了箭头的模块：${allowed.join(', ')}`,
      severity: 'error',
      from: { path: `^${escapeRe(m.dir)}` },
      to: { path: rootsRe, pathNot: allowed.map((d) => `^${escapeRe(d)}`) },
    });
  }
  forbidden.push({
    name: 'shared-stays-shared',
    comment: '公共目录不能引用任何其他模块',
    severity: 'error',
    from: { path: `^${escapeRe(model.sharedDirs.host)}` },
    to: { path: rootsRe, pathNot: [`^${escapeRe(model.sharedDirs.host)}`] },
  });
  forbidden.push({
    name: 'no-unmapped-source',
    comment: '源码必须放在图上某个模块的目录或公共目录里',
    severity: 'error',
    from: { path: `^${escapeRe(srcRoot)}`, pathNot: [...codeModules.filter((m) => m.dir.startsWith(srcRoot)).map((m) => `^${escapeRe(m.dir)}`), `^${escapeRe(model.sharedDirs.host)}`] },
    to: {},
  });
  forbidden.push({ name: 'no-circular', comment: '禁止循环依赖', severity: 'error', from: {}, to: { circular: true } });
  return {
    forbidden,
    options: {
      doNotFollow: { path: 'node_modules' },
      tsPreCompilationDeps: true,
      tsConfig: { fileName: 'tsconfig.json' },
      enhancedResolveOptions: { extensions: ['.ts', '.mts', '.js', '.mjs', '.json'] },
    },
  };
}

// ---------- 实际依赖叠加 ----------
function moduleForPath(path) {
  let best = null;
  for (const m of model.modules) {
    if (!m.code || !m.dir) continue;
    if (path.startsWith(m.dir) && (!best || m.dir.length > best.dir.length)) best = m;
  }
  return best ? best.id : null;
}

function readActual(file) {
  const data = JSON.parse(readFileSync(resolve(process.cwd(), file), 'utf8'));
  const seen = new Map();
  let files = 0;
  for (const mod of data.modules || []) {
    const from = moduleForPath(mod.source);
    if (!from) continue;
    files += 1;
    for (const dep of mod.dependencies || []) {
      const to = moduleForPath(dep.resolved || '');
      if (!to || to === from) continue;
      const key = `${from}>${to}`;
      if (!seen.has(key)) seen.set(key, { from, to, example: `${mod.source} → ${dep.resolved}` });
    }
  }
  const drawn = model.edges.filter((e) => e.kind === 'call' && modules.get(e.from)?.code && modules.get(e.to)?.code);
  const edgeStatus = {};
  for (const e of drawn) edgeStatus[e.id] = seen.has(`${e.from}>${e.to}`) ? 'ok' : 'missing';
  const extra = [...seen.values()].filter((x) => !drawn.some((e) => e.from === x.from && e.to === x.to));
  const problems = extra.map((x) => ({ module: x.from, text: `代码里有 [${x.from}] → [${x.to}]，图上没有这根箭头（例：${x.example}）` }));
  addCheck('C9', '实际代码的调用关系与图一致', `由 ${ARCH.command || '架构检查'} 读取真实 import 后对比。`, problems);
  return { source: file, files, edgeStatus, extra, generatedAt: new Date().toISOString() };
}

function readTrace() {
  const file = join(outDir, 'trace.json');
  if (!existsSync(file)) return null;
  try {
    const events = JSON.parse(readFileSync(file, 'utf8'));
    return Array.isArray(events) ? events : events.trace || null;
  } catch {
    return null;
  }
}
// trace.json 由哪个验收场景写出（用于判断"没经过的模块"是不是后续切片才建）
function readTraceSource() {
  const file = join(outDir, 'trace.json');
  if (!existsSync(file)) return null;
  try {
    const events = JSON.parse(readFileSync(file, 'utf8'));
    return Array.isArray(events) ? null : events.acceptance || null;
  } catch {
    return null;
  }
}

// CLAUDE.md 中提到的 design/ 路径必须存在（在生成产物之后检查）
function checkClaude() {
  const problems = [];
  if (claudeText === null) {
    problems.push({ text: '项目根目录缺少 CLAUDE.md' });
  } else {
    const paths = new Set([...claudeText.matchAll(/`(design\/[^`\s]+)`/g)].map((m) => m[1]));
    for (const p of paths) if (!existsSync(join(rootDir, p))) problems.push({ text: `CLAUDE.md 提到的 ${p} 不存在` });
    if (!claudeText.includes('design/architecture.json')) problems.push({ text: 'CLAUDE.md 没有指向 design/architecture.json' });
  }
  addCheck('C10', 'CLAUDE.md 指向的文件都存在', 'Claude Code 每次开工先读 CLAUDE.md，它指向的图和规格必须真实存在。', problems);
}

// ---------- Mermaid ----------
function mermaid() {
  const nid = (id) => id.replace(/-/g, '_');
  const lines = ['flowchart TB'];
  const groups = model.layers.map((l) => [l.id.replace(/-/g, '_'), l.name, (m) => m.layer === l.id]);
  for (const [gid, gname, pick] of groups) {
    lines.push(`  subgraph ${gid}["${gname}"]`);
    for (const m of model.modules.filter(pick)) lines.push(`    ${nid(m.id)}["${m.name}<br/><small>${m.id}</small>"]`);
    lines.push('  end');
  }
  const arrow = { call: '-->', load: '-.->', spawn: '-.->', external: '==>' };
  for (const e of model.edges) lines.push(`  ${nid(e.from)} ${arrow[e.kind] || '-->'}|"${e.label}"| ${nid(e.to)}`);
  return lines.join('\n') + '\n';
}

// ---------- 审阅页 ----------
const pageCss = readFileSync(join(here, 'review', 'page.css'), 'utf8');
const pageJs = readFileSync(join(here, 'review', 'page.js'), 'utf8');
// 分层配色：layer.color 可选 page.css 色板里的 9 个名字之一，不写就按顺序取
const PALETTE = ['shell', 'api', 'agent', 'platform', 'security', 'skill', 'plugin', 'resource', 'store'];
const layerCss = model.layers.map((l, i) => {
  const k = PALETTE.includes(l.color) ? l.color : PALETTE[i % PALETTE.length];
  return `:root { --lc-${l.id}: var(--l-${k}); --lc-${l.id}-s: var(--l-${k}-s); }\n.layer-${l.id} rect.box { fill: var(--lc-${l.id}); stroke: var(--lc-${l.id}-s); }`;
}).join('\n');
const escHtml = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

function pageParts(data) {
  const json = JSON.stringify(data).replace(/</g, '\\u003c');
  const head = `<title>${escHtml(model.title)}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>${pageCss}\n${layerCss}</style>`;
  const body = `<div class="page">
  <header class="masthead">
    <div class="masthead-text">
      ${model.eyebrow ? `<p class="eyebrow">${escHtml(model.eyebrow)}</p>` : ''}
      <h1>${escHtml(model.title)}</h1>
      <p class="lede">图、文字规格、代码是否一致，在这一页看清。点图上的方框或箭头，右侧显示 SPEC.md 里对应的原文。</p>
    </div>
    <dl class="titleblock" id="titleblock"></dl>
  </header>
  <nav class="toolbar" aria-label="查看方式">
    <div class="tb-row"><span class="tb-label">${escHtml(FLOW)}</span><div class="steps" id="steps" role="group" aria-label="${escHtml(FLOW)}"></div><button type="button" class="toggle rev" id="rev-toggle" aria-pressed="false" hidden></button></div>
    <div class="tb-row"><span class="tb-label">施工切片</span><div class="steps" id="slices" role="group" aria-label="施工切片"></div><button type="button" class="toggle" id="actual-toggle" aria-pressed="false"></button></div>
  </nav>
  <main class="workspace">
    <section class="diagram-card" aria-label="架构图">
      <div class="diagram-scroll"><svg id="diagram" role="img" aria-label="${escHtml(model.title)} 架构图"></svg></div>
      <div class="legend" id="legend"></div>
    </section>
    <aside class="panel" id="panel" aria-live="polite"></aside>
  </main>
  <section class="report" aria-labelledby="checks-title">
    <h2 id="checks-title">一致性检查</h2>
    <p class="section-note">这些检查由 <code>design/tools/build.mjs</code> 在生成本页时完成。全部通过，说明文字和图没有偏差。</p>
    <ol class="checks" id="checks"></ol>
  </section>
  <section class="report two-col">
    <div>
      <h2>不变量：绝不能发生的事</h2>
      <div class="table-scroll"><table class="grid" id="inv-table"></table></div>
    </div>
    <div>
      <h2>施工切片</h2>
      <p class="section-note">每个切片做完都能跑演示命令看到结果。点切片编号，图上会标出它新建的模块。</p>
      <ol class="phases" id="phases"></ol>
    </div>
  </section>
  <footer class="foot" id="foot"></footer>
</div>
<script id="bp-data" type="application/json">${json}</script>
<script>${pageJs}</script>`;
  return { head, body };
}

// ---------- 运行 ----------
mkdirSync(outDir, { recursive: true });
let actual = null;
const actualFile = option('--actual') || (existsSync(join(outDir, 'actual-deps.json')) ? join(outDir, 'actual-deps.json') : null);
if (actualFile) actual = readActual(actualFile);
const trace = readTrace();

if (ARCH.tool === 'depcruise') {
  writeFileSync(join(outDir, 'depcruise.cjs'), `// 由 design/tools/build.mjs 根据 architecture.json 生成，不要手工修改。\nmodule.exports = ${JSON.stringify(depcruiseConfig(), null, 2)};\n`);
}
writeFileSync(join(outDir, 'architecture.mmd'), mermaid());

// 先写一次占位页面，保证 CLAUDE.md 引用的产物存在，再做最终检查
writeFileSync(join(outDir, 'review.html'), '<!doctype html><meta charset="utf-8"><title>生成中</title>');
checkClaude();

checks.sort((a, b) => Number(a.id.slice(1)) - Number(b.id.slice(1)));
const sections = {};
for (const [id, s] of spec.sections) sections[id] = { title: s.title, body: s.body, line: s.line };
const moduleStatus = {};
for (const [id, problems] of moduleProblems) moduleStatus[id] = { ok: problems.length === 0, problems };
const edgeInfo = {};
for (const e of model.edges) {
  const written = fieldIds(spec.sections.get(e.from), '调用') || [];
  const kind = model.edgeKinds.find((k) => k.id === e.kind);
  edgeInfo[e.id] = {
    inSpec: written.includes(e.to),
    guard: kind ? kind.guard : 'test',
    ats: model.acceptance.filter((a) => a.covers.includes(e.from) && a.covers.includes(e.to)).map((a) => a.id),
    steps: model.flow.filter((s) => s.edges.includes(e.id)).map((s) => s.n),
    rule: e.kind === 'call' && modules.get(e.from)?.code ? `only-drawn-calls-${e.from}` : null,
  };
}

const data = {
  model,
  flowName: FLOW,
  archCommand: ARCH.command || '',
  sections,
  checks,
  moduleStatus,
  edgeInfo,
  actual,
  trace,
  traceSource: readTraceSource(),
  generatedAt: new Date().toISOString(),
};
const { head, body } = pageParts(data);
writeFileSync(join(outDir, 'review.html'), `<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n${head}\n</head>\n<body>\n${body}\n</body>\n</html>\n`);
const artifactOut = option('--artifact-out');
if (artifactOut) writeFileSync(resolve(process.cwd(), artifactOut), `${head}\n${body}\n`);

const failed = checks.filter((c) => !c.ok);
writeFileSync(join(outDir, 'check-report.json'), JSON.stringify({ generatedAt: data.generatedAt, checks }, null, 2) + '\n');

for (const c of checks) {
  console.log(`${c.ok ? '通过' : '失败'}  ${c.id} ${c.title}`);
  for (const p of c.problems) console.log(`      - ${p}`);
}
console.log(`\n审阅页：${join(outDir, 'review.html')}`);
if (hasFlag('--check') && failed.length) {
  console.error(`\n${failed.length} 项检查未通过。`);
  process.exit(1);
}
