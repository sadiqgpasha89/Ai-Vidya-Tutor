// Interactive tools: simulations, chemistry tools, unit converter, code runner, and the voice check page.
import { api, get } from './api.js';
import { t } from './i18n.js';
import { esc } from './render.js';
import { $, $$, toast } from './ui.js';
import { state, langInfo } from './state.js';
import { compile } from './calc.js';
import { speaker, listener, listVoices, pickVoice, supportsBrowserTTS, supportsBrowserSTT, supportsRecording, serverVoice } from './voice.js';

const slider = (id, label, min, max, step, val, unit = '') => `<label class="sl"><span>${label}: <b id="${id}-v">${val}</b>${unit}</span><input type="range" id="${id}" min="${min}" max="${max}" step="${step}" value="${val}"></label>`;
const num = (el) => parseFloat(el.value);
const fmt = (n, d = 2) => (Number.isFinite(n) ? +n.toFixed(d) : '—');
const wire = (root, ids, fn) => ids.forEach((id) => { const el = $(`#${id}`, root); el.addEventListener('input', () => { const v = $(`#${id}-v`, root); if (v) v.textContent = el.value; fn(); }); });

/* ============================================================ simulations ============================================================ */
export const SIMS = {
  grapher: { icon: '📈', title: 'Function grapher', match: (tp) => tp.subject === 'maths' || /graph|linear|quadratic|polynomial|trigonometric|function|coordinate/i.test(tp.title + tp.chapter) },
  projectile: { icon: '🏹', title: 'Projectile motion', match: (tp) => /projectile|motion in a plane|free fall/i.test(tp.title + tp.chapter) },
  motion: { icon: '🚗', title: 'Motion graphs', match: (tp) => tp.subject === 'physics' && /motion|velocity|acceleration|speed|graphs/i.test(tp.title + tp.chapter) },
  ohm: { icon: '🔌', title: "Ohm's law & circuits", match: (tp) => tp.subject === 'physics' && /ohm|resist|electric|current|circuit/i.test(tp.title + tp.chapter) },
  shm: { icon: '🌊', title: 'Pendulum & waves', match: (tp) => tp.subject === 'physics' && /oscillat|pendulum|wave|sound|harmonic/i.test(tp.title + tp.chapter) },
  lens: { icon: '🔍', title: 'Lenses & mirrors', match: (tp) => tp.subject === 'physics' && /lens|mirror|refraction|reflection|light|optic/i.test(tp.title + tp.chapter) },
  ph: { icon: '🧫', title: 'pH scale', match: (tp) => tp.subject === 'chemistry' && /acid|base|ph\b|salt|neutral/i.test(tp.title + tp.chapter) },
  periodic: { icon: '🧪', title: 'Periodic table', match: (tp) => tp.subject === 'chemistry' && /periodic|element|atom|classification/i.test(tp.title + tp.chapter) },
  balancer: { icon: '⚖️', title: 'Equation balancer', match: (tp) => tp.subject === 'chemistry' && /equation|reaction|stoich|mole/i.test(tp.title + tp.chapter) },
  molecules: { icon: '🧬', title: '3D molecules', match: (tp) => tp.subject === 'chemistry' && /bond|molecul|carbon|hydrocarbon|structure|geometry/i.test(tp.title + tp.chapter) },
  numsys: { icon: '🔢', title: 'Number systems', match: (tp) => tp.subject === 'computers' && /number|binary|encoding|system/i.test(tp.title + tp.chapter) },
  gates: { icon: '🔀', title: 'Logic gates', match: (tp) => tp.subject === 'computers' && /boolean|logic|gate/i.test(tp.title + tp.chapter) },
  units: { icon: '📏', title: 'Unit converter', match: (tp) => ['physics', 'chemistry'].includes(tp.subject) },
};
export const simsFor = (topic) => Object.entries(SIMS).filter(([, s]) => s.match(topic)).slice(0, 3).map(([id, s]) => ({ id, icon: s.icon, title: t(`sim.${id}`, s.title) }));

export function mountSim(id, host) {
  host.innerHTML = `<div class="card pad sim" data-sim="${id}"><div class="row"><h2 style="margin:0">${SIMS[id].icon} ${t(`sim.${id}`, SIMS[id].title)}</h2></div><div class="sim-body"></div></div>`;
  const body = $('.sim-body', host); SIM_IMPL[id](body); host.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

const SIM_IMPL = {
  grapher(root) {
    root.innerHTML = `<p class="muted small">${t('sim.graph.help', 'Type up to three functions of x. Use a, b, c with the sliders. Example: a*x^2 + b*x + c, sin(x), 1/x')}</p>
      ${[1, 2, 3].map((n, i) => `<div class="field"><label for="fx${n}">y${n} =</label><input id="fx${n}" type="text" value="${['a*x^2 + b*x + c', 'sin(x)', ''][i]}"></div>`).join('')}
      <div class="sl-grid">${slider('ga', 'a', -5, 5, 0.1, 1)}${slider('gb', 'b', -5, 5, 0.1, 0)}${slider('gc', 'c', -5, 5, 0.1, -2)}${slider('gxr', 'x range ±', 2, 30, 1, 8)}</div><p class="error" id="gerr" hidden></p><svg id="gsvg" viewBox="0 0 600 400" class="plot" role="img" aria-label="graph"></svg>`;
    const draw = () => {
      const R = num($('#gxr', root)), vars = { a: num($('#ga', root)), b: num($('#gb', root)), c: num($('#gc', root)) }; const colors = ['#2563eb', '#dc2626', '#16a34a']; const curves = []; let err = '';
      [1, 2, 3].forEach((n, i) => { const src = $(`#fx${n}`, root).value.trim(); if (!src) return; try { const f = compile(src); const pts = []; for (let k = 0; k <= 400; k++) { const x = -R + (2 * R * k) / 400; let y; try { y = f({ ...vars, x }); } catch { y = NaN; } pts.push([x, Number.isFinite(y) ? y : null]); } curves.push({ pts, color: colors[i], src }); } catch (e) { err = `y${n}: ${e.message}`; } });
      const ys = curves.flatMap((c) => c.pts.map((p) => p[1]).filter((v) => v !== null)).sort((a, b) => a - b); const lo = ys.length ? ys[Math.floor(ys.length * 0.02)] : -R, hi = ys.length ? ys[Math.floor(ys.length * 0.98)] : R; const pad = (hi - lo || 2) * 0.1; const y0 = lo - pad, y1 = hi + pad;
      const sx = (x) => 40 + ((x + R) / (2 * R)) * 520, sy = (y) => 360 - ((y - y0) / (y1 - y0)) * 320; let g = '<rect width="600" height="400" fill="#fff"/>';
      for (let x = Math.ceil(-R); x <= R; x += Math.max(1, Math.round(R / 5))) g += `<line x1="${sx(x)}" y1="40" x2="${sx(x)}" y2="360" stroke="#e5e7eb"/><text x="${sx(x)}" y="378" font-size="12" text-anchor="middle" fill="#374151">${x}</text>`;
      if (y0 < 0 && y1 > 0) g += `<line x1="40" y1="${sy(0)}" x2="560" y2="${sy(0)}" stroke="#111" stroke-width="1.5"/>`; if (-R < 0) g += `<line x1="${sx(0)}" y1="40" x2="${sx(0)}" y2="360" stroke="#111" stroke-width="1.5"/>`;
      curves.forEach((c, k) => { let seg = []; const flush = () => { if (seg.length > 1) g += `<polyline points="${seg.join(' ')}" fill="none" stroke="${c.color}" stroke-width="2.5"/>`; seg = []; }; c.pts.forEach(([x, y]) => { if (y === null || y < y0 - (y1 - y0) || y > y1 + (y1 - y0)) flush(); else seg.push(`${sx(x).toFixed(1)},${sy(y).toFixed(1)}`); }); flush(); g += `<text x="556" y="${56 + 16 * k}" font-size="13" text-anchor="end" fill="${c.color}">${esc(c.src)}</text>`; });
      $('#gsvg', root).innerHTML = g; const e = $('#gerr', root); e.textContent = err; e.hidden = !err;
    };
    wire(root, ['ga', 'gb', 'gc', 'gxr'], draw); $$('input[type=text]', root).forEach((i) => i.addEventListener('input', draw)); draw();
  },
  projectile(root) {
    root.innerHTML = `<div class="sl-grid">${slider('pv', 'Speed', 5, 60, 1, 25, ' m/s')}${slider('pa', 'Angle', 5, 85, 1, 45, '°')}${slider('pg', 'Gravity g', 1.6, 25, 0.1, 9.8, ' m/s²')}${slider('ph', 'Launch height', 0, 30, 1, 0, ' m')}</div><div id="pout" class="chips" aria-live="polite"></div><svg id="psvg" viewBox="0 0 600 300" class="plot" role="img" aria-label="trajectory"></svg>`;
    const draw = () => {
      const v = num($('#pv', root)), a = (num($('#pa', root)) * Math.PI) / 180, g = num($('#pg', root)), h0 = num($('#ph', root)); const vx = v * Math.cos(a), vy = v * Math.sin(a);
      const T = (vy + Math.sqrt(vy * vy + 2 * g * h0)) / g, R = vx * T, H = h0 + (vy * vy) / (2 * g); const W = Math.max(R, 10) * 1.1, Hh = Math.max(H, 5) * 1.2; const sx = (x) => 30 + (x / W) * 550, sy = (y) => 270 - (y / Hh) * 240;
      let pts = ''; for (let i = 0; i <= 80; i++) { const tt = (T * i) / 80; pts += `${sx(vx * tt).toFixed(1)},${sy(h0 + vy * tt - 0.5 * g * tt * tt).toFixed(1)} `; }
      $('#psvg', root).innerHTML = `<rect width="600" height="300" fill="#fff"/><line x1="30" y1="270" x2="590" y2="270" stroke="#111" stroke-width="2"/><polyline points="${pts}" fill="none" stroke="#2563eb" stroke-width="3" stroke-dasharray="6 4"/><circle r="9" fill="#dc2626"><animateMotion dur="${Math.max(1.2, T / 2).toFixed(1)}s" repeatCount="indefinite" path="M${pts.trim().split(' ').join(' L')}"/></circle>`;
      $('#pout', root).innerHTML = `<span class="chip">${t('sim.range', 'Range')}: <b>${fmt(R)}</b> m</span><span class="chip">${t('sim.maxh', 'Max height')}: <b>${fmt(H)}</b> m</span><span class="chip">${t('sim.time', 'Time of flight')}: <b>${fmt(T)}</b> s</span>`;
    };
    wire(root, ['pv', 'pa', 'pg', 'ph'], draw); draw();
  },
  motion(root) {
    root.innerHTML = `<div class="sl-grid">${slider('mu', 'Initial speed u', -20, 40, 1, 5, ' m/s')}${slider('ma', 'Acceleration a', -10, 10, 0.5, 2, ' m/s²')}${slider('mt', 'Time', 2, 20, 1, 10, ' s')}</div><div id="mout" class="chips" aria-live="polite"></div><svg id="msvg" viewBox="0 0 600 220" class="plot" role="img" aria-label="velocity-time and position-time graphs"></svg>
      <p class="muted small">${t('sim.motion.help', 'Left: velocity–time graph (area = distance). Right: position–time graph (slope = velocity).')}</p>`;
    const draw = () => {
      const u = num($('#mu', root)), a = num($('#ma', root)), T = num($('#mt', root)); const v = (tt) => u + a * tt, s = (tt) => u * tt + 0.5 * a * tt * tt; const N = 60; const tv = [], ts = []; for (let i = 0; i <= N; i++) { const tt = (T * i) / N; tv.push([tt, v(tt)]); ts.push([tt, s(tt)]); }
      const panel = (pts, x0, color, label) => { const ys = pts.map((p) => p[1]); const lo = Math.min(0, ...ys), hi = Math.max(0.0001, ...ys), span = hi - lo || 1; const X = (tt) => x0 + 20 + (tt / T) * 240, Y = (y) => 190 - ((y - lo) / span) * 160; return `<rect x="${x0}" y="10" width="280" height="200" fill="#fff" stroke="#e5e7eb"/><line x1="${x0 + 20}" y1="${Y(0)}" x2="${x0 + 270}" y2="${Y(0)}" stroke="#111"/><polyline fill="none" stroke="${color}" stroke-width="3" points="${pts.map(([tt, y]) => `${X(tt).toFixed(1)},${Y(y).toFixed(1)}`).join(' ')}"/><text x="${x0 + 150}" y="28" text-anchor="middle" font-size="13" fill="#111" font-weight="bold">${label}</text>`; };
      $('#msvg', root).innerHTML = panel(tv, 10, '#2563eb', 'v (m/s) vs t (s)') + panel(ts, 310, '#dc2626', 's (m) vs t (s)');
      $('#mout', root).innerHTML = `<span class="chip">v = u + at = <b>${fmt(v(T))}</b> m/s</span><span class="chip">s = ut + ½at² = <b>${fmt(s(T))}</b> m</span><span class="chip">v² = u² + 2as ✓ ${fmt(v(T) ** 2)} = ${fmt(u * u + 2 * a * s(T))}</span>`;
    };
    wire(root, ['mu', 'ma', 'mt'], draw); draw();
  },
  ohm(root) {
    root.innerHTML = `<div class="sl-grid">${slider('ov', 'Battery V', 1, 24, 0.5, 9, ' V')}${slider('o1', 'R₁', 1, 100, 1, 10, ' Ω')}${slider('o2', 'R₂', 1, 100, 1, 20, ' Ω')}</div><div class="choice-row" id="omode"><button class="choice" data-v="series" aria-pressed="true">${t('sim.series', 'Series')}</button><button class="choice" data-v="parallel" aria-pressed="false">${t('sim.parallel', 'Parallel')}</button></div><div id="oout" class="chips" aria-live="polite"></div><svg id="osvg" viewBox="0 0 600 240" class="plot" role="img" aria-label="circuit"></svg>`;
    const draw = () => {
      const V = num($('#ov', root)), r1 = num($('#o1', root)), r2 = num($('#o2', root)), par = $('#omode .choice[aria-pressed="true"]', root).dataset.v === 'parallel'; const Req = par ? (r1 * r2) / (r1 + r2) : r1 + r2, I = V / Req, I1 = par ? V / r1 : I, I2 = par ? V / r2 : I;
      const res = (x, y, l) => `<rect x="${x}" y="${y - 12}" width="64" height="24" fill="#fff" stroke="#111" stroke-width="2"/><text x="${x + 32}" y="${y + 5}" text-anchor="middle" font-size="13">${l}</text>`;
      $('#osvg', root).innerHTML = `<rect width="600" height="240" fill="#fff"/>` + (par ? `<polyline points="80,40 80,200 520,200 520,40 80,40" fill="none" stroke="#111" stroke-width="2"/><line x1="300" y1="40" x2="300" y2="200" stroke="#111" stroke-width="2"/>${res(150, 90, `R₁ ${r1}Ω`)}${res(360, 90, `R₂ ${r2}Ω`)}<text x="116" y="150" font-size="13" fill="#2563eb">${fmt(I1)} A</text><text x="400" y="150" font-size="13" fill="#2563eb">${fmt(I2)} A</text>` : `<polyline points="80,40 520,40 520,200 80,200 80,40" fill="none" stroke="#111" stroke-width="2"/>${res(150, 40, `R₁ ${r1}Ω`)}${res(360, 40, `R₂ ${r2}Ω`)}<text x="300" y="130" font-size="14" fill="#2563eb" text-anchor="middle">I = ${fmt(I)} A</text>`)
        + `<g><line x1="60" y1="110" x2="100" y2="110" stroke="#111" stroke-width="3"/><line x1="70" y1="124" x2="90" y2="124" stroke="#111" stroke-width="3"/><text x="106" y="120" font-size="13">${V} V</text></g>`;
      $('#oout', root).innerHTML = `<span class="chip">R<sub>eq</sub> = <b>${fmt(Req)}</b> Ω</span><span class="chip">I = V/R = <b>${fmt(I)}</b> A</span><span class="chip">P = VI = <b>${fmt(V * I)}</b> W</span><span class="chip">${par ? 'V same across both' : 'V₁ = ' + fmt(I * r1) + ' V, V₂ = ' + fmt(I * r2) + ' V'}</span>`;
    };
    wire(root, ['ov', 'o1', 'o2'], draw); $$('#omode .choice', root).forEach((b) => (b.onclick = () => { $$('#omode .choice', root).forEach((x) => x.setAttribute('aria-pressed', x === b)); draw(); })); draw();
  },
  shm(root) {
    root.innerHTML = `<div class="sl-grid">${slider('sl', 'Pendulum length', 0.2, 3, 0.1, 1, ' m')}${slider('sg', 'g', 1.6, 25, 0.1, 9.8, ' m/s²')}${slider('sa', 'Amplitude', 5, 60, 1, 25, '°')}</div><div id="sout" class="chips" aria-live="polite"></div><svg id="ssvg" viewBox="0 0 600 220" class="plot" role="img" aria-label="pendulum"></svg>
      <h4>${t('sim.waves', 'Two waves adding up (superposition)')}</h4><div class="sl-grid">${slider('w1', 'Frequency 1', 1, 8, 0.5, 3)}${slider('w2', 'Frequency 2', 1, 8, 0.5, 4)}</div><svg id="wsvg" viewBox="0 0 600 160" class="plot" role="img" aria-label="waves"></svg><p class="muted small" id="wout"></p>`;
    let raf = 0, t0 = performance.now();
    const loop = (now) => { if (!root.isConnected) return; const L = num($('#sl', root)), g = num($('#sg', root)), A = (num($('#sa', root)) * Math.PI) / 180, T = 2 * Math.PI * Math.sqrt(L / g); const th = A * Math.cos((2 * Math.PI * (now - t0)) / 1000 / T); const px = 300 + Math.sin(th) * L * 60, py = 20 + Math.cos(th) * L * 60;
      $('#ssvg', root).innerHTML = `<rect width="600" height="220" fill="#fff"/><line x1="300" y1="20" x2="${px}" y2="${py}" stroke="#111" stroke-width="2"/><circle cx="${px}" cy="${py}" r="14" fill="#dc2626"/><circle cx="300" cy="20" r="4"/>`;
      $('#sout', root).innerHTML = `<span class="chip">T = 2π√(L/g) = <b>${fmt(T)}</b> s</span><span class="chip">f = <b>${fmt(1 / T)}</b> Hz</span>`; raf = requestAnimationFrame(loop); };
    raf = requestAnimationFrame(loop); import('./app.js').then((m) => m.setLeave(() => cancelAnimationFrame(raf)));
    const wave = () => { const f1 = num($('#w1', root)), f2 = num($('#w2', root)); const y = (x, k) => 80 - k * 28 * Math.sin(2 * Math.PI * x); const line = (fn, color) => `<polyline fill="none" stroke="${color}" stroke-width="2" points="${Array.from({ length: 201 }, (_, i) => `${(i * 3).toFixed(0)},${fn(i / 200).toFixed(1)}`).join(' ')}"/>`; $('#wsvg', root).innerHTML = `<rect width="600" height="160" fill="#fff"/><line x1="0" y1="80" x2="600" y2="80" stroke="#e5e7eb"/>${line((x) => 80 - 28 * Math.sin(2 * Math.PI * f1 * x), '#2563eb')}${line((x) => 80 - 28 * Math.sin(2 * Math.PI * f2 * x), '#16a34a')}${line((x) => 80 - 28 * (Math.sin(2 * Math.PI * f1 * x) + Math.sin(2 * Math.PI * f2 * x)) / 1.4, '#dc2626')}`; $('#wout', root).textContent = `${t('sim.beat', 'Red = sum. Beat frequency')} |f₁ − f₂| = ${fmt(Math.abs(f1 - f2))} Hz`; };
    wire(root, ['w1', 'w2'], wave); wave();
  },
  lens(root) {
    root.innerHTML = `<div class="choice-row" id="lt"><button class="choice" data-v="lens" aria-pressed="true">${t('sim.convexlens', 'Convex lens')}</button><button class="choice" data-v="mirror" aria-pressed="false">${t('sim.concavemirror', 'Concave mirror')}</button></div><div class="sl-grid">${slider('lu', 'Object distance u', 5, 60, 1, 30, ' cm')}${slider('lf', 'Focal length f', 5, 30, 1, 10, ' cm')}${slider('lh', 'Object height', 1, 10, 1, 4, ' cm')}</div><div id="lout" class="chips" aria-live="polite"></div><svg id="lsvg" viewBox="0 0 640 260" class="plot" role="img" aria-label="ray diagram"></svg>`;
    const draw = () => {
      const lens = $('#lt .choice[aria-pressed="true"]', root).dataset.v === 'lens', u = num($('#lu', root)), f = num($('#lf', root)), h = num($('#lh', root));
      // sign convention: lens 1/v - 1/u = 1/f with u negative; mirror 1/v + 1/u = 1/f with u negative
      const U = -u; let v = lens ? 1 / (1 / f + 1 / U) : 1 / (1 / f - 1 / U); if (!lens) v = 1 / (1 / (-f) - 1 / U); const m = lens ? v / U : -v / U; const hi = m * h; const cx = 320, k = 4;
      const X = (d) => cx + d * k, Y = (y) => 130 - y * k * 1.6; let g = `<rect width="640" height="260" fill="#fff"/><line x1="0" y1="130" x2="640" y2="130" stroke="#9ca3af"/>`; g += lens ? `<line x1="${cx}" y1="30" x2="${cx}" y2="230" stroke="#2563eb" stroke-width="4"/>` : `<path d="M${cx + 20} 30 Q${cx - 10} 130 ${cx + 20} 230" fill="none" stroke="#2563eb" stroke-width="4"/>`;
      g += `<line x1="${X(-u)}" y1="130" x2="${X(-u)}" y2="${Y(h)}" stroke="#16a34a" stroke-width="4"/><text x="${X(-u)}" y="${Y(h) - 6}" font-size="12" text-anchor="middle">O</text>`;
      const fx = lens ? [X(-f), X(f)] : [X(-f)]; fx.forEach((x, i) => { g += `<circle cx="${x}" cy="130" r="3"/><text x="${x}" y="148" font-size="11" text-anchor="middle">F${lens ? '' : ''}</text>`; });
      if (Number.isFinite(v) && Math.abs(v) < 160) { const real = lens ? v > 0 : v < 0; const ix = lens ? X(v) : X(v); g += `<line x1="${ix}" y1="130" x2="${ix}" y2="${Y(hi)}" stroke="#dc2626" stroke-width="4" ${real ? '' : 'stroke-dasharray="5 4"'}/><text x="${ix}" y="${Y(hi) + (hi > 0 ? -6 : 14)}" font-size="12" text-anchor="middle" fill="#dc2626">I</text>`; g += `<line x1="${X(-u)}" y1="${Y(h)}" x2="${cx}" y2="${Y(h)}" stroke="#f59e0b" stroke-width="1.5"/><line x1="${cx}" y1="${Y(h)}" x2="${ix}" y2="${Y(hi)}" stroke="#f59e0b" stroke-width="1.5" ${real ? '' : 'stroke-dasharray="4 3"'}/>`; }
      $('#lsvg', root).innerHTML = g;
      const nature = !Number.isFinite(v) || Math.abs(v) > 500 ? t('sim.atinf', 'image at infinity') : ((lens ? v > 0 : v < 0) ? t('sim.real', 'real, inverted') : t('sim.virtual', 'virtual, erect'));
      $('#lout', root).innerHTML = `<span class="chip">v = <b>${fmt(v)}</b> cm</span><span class="chip">m = <b>${fmt(m)}</b></span><span class="chip">${nature}</span><span class="chip">${lens ? '1/v − 1/u = 1/f' : '1/v + 1/u = 1/f'}</span>`;
    };
    wire(root, ['lu', 'lf', 'lh'], draw); $$('#lt .choice', root).forEach((b) => (b.onclick = () => { $$('#lt .choice', root).forEach((x) => x.setAttribute('aria-pressed', x === b)); draw(); })); draw();
  },
  ph(root) {
    const items = [[0, 'Battery acid'], [1, 'Stomach acid'], [2.5, 'Lemon juice'], [3, 'Vinegar'], [4, 'Tomato'], [5, 'Black coffee'], [6.5, 'Milk'], [7, 'Pure water'], [8, 'Baking soda'], [9, 'Toothpaste'], [11, 'Milk of magnesia'], [12, 'Soap'], [13, 'Bleach'], [14, 'Drain cleaner']];
    root.innerHTML = `${slider('pp', 'pH', 0, 14, 0.1, 7)}<div id="pbar" class="phbar" aria-hidden="true"></div><div id="pout2" class="chips" aria-live="polite"></div><div class="small muted" id="pnear"></div>`;
    $('#pbar', root).style.background = 'linear-gradient(90deg,#e11d48,#f97316,#eab308,#22c55e,#06b6d4,#3b82f6,#7c3aed)';
    const draw = () => { const p = num($('#pp', root)); const H = 10 ** -p; const near = items.slice().sort((a, b) => Math.abs(a[0] - p) - Math.abs(b[0] - p)).slice(0, 2).map((x) => x[1]).join(', ');
      $('#pout2', root).innerHTML = `<span class="chip">[H⁺] = <b>${H.toExponential(1)}</b> mol/L</span><span class="chip">pOH = <b>${fmt(14 - p, 1)}</b></span><span class="chip">${p < 6.95 ? t('sim.acidic', 'Acidic (litmus turns red)') : p > 7.05 ? t('sim.basic', 'Basic (litmus turns blue)') : t('sim.neutral', 'Neutral')}</span>`; $('#pnear', root).textContent = `${t('sim.like', 'Like')}: ${near}`; };
    wire(root, ['pp'], draw); draw();
  },
  periodic(root) { import('./chem.js').then((m) => m.periodic(root)); },
  balancer(root) { import('./chem.js').then((m) => m.balancer(root)); },
  molecules(root) { import('./chem.js').then((m) => m.molecules(root)); },
  numsys(root) {
    root.innerHTML = `<div class="field"><label for="nv">${t('sim.number', 'Type a number in any box')}</label></div><div class="sl-grid"><label class="sl">Decimal<input id="nd" type="text" value="156"></label><label class="sl">Binary<input id="nb" type="text"></label><label class="sl">Octal<input id="no" type="text"></label><label class="sl">Hexadecimal<input id="nh" type="text"></label></div><p class="muted small" id="nx"></p>`;
    const set = (n, skip) => { const ids = { d: 10, b: 2, o: 8, h: 16 }; for (const [k, base] of Object.entries(ids)) if (k !== skip) $(`#n${k}`, root).value = Number.isNaN(n) ? '' : n.toString(base).toUpperCase(); $('#nx', root).textContent = Number.isNaN(n) ? '' : `${n} = ${n.toString(2).split('').reverse().map((b, i) => (b === '1' ? `2^${i}` : null)).filter(Boolean).reverse().join(' + ') || '0'}`; };
    [['d', 10], ['b', 2], ['o', 8], ['h', 16]].forEach(([k, base]) => $(`#n${k}`, root).addEventListener('input', (e) => set(e.target.value.trim() && /^[0-9a-f]+$/i.test(e.target.value) ? parseInt(e.target.value, base) : NaN, k))); set(156, '');
  },
  gates(root) {
    const G = { AND: (a, b) => a & b, OR: (a, b) => a | b, NOT: (a) => 1 - a, NAND: (a, b) => 1 - (a & b), NOR: (a, b) => 1 - (a | b), XOR: (a, b) => a ^ b, XNOR: (a, b) => 1 - (a ^ b) };
    root.innerHTML = `<div class="choice-row" id="gg">${Object.keys(G).map((n, i) => `<button class="choice" data-v="${n}" aria-pressed="${i === 0}">${n}</button>`).join('')}</div><div class="row"><label class="check"><input type="checkbox" id="ga1"> A = 1</label><label class="check"><input type="checkbox" id="gb1"> B = 1</label><span class="chip" id="gout"></span></div><table class="tt" id="gtt"></table>`;
    const draw = () => { const n = $('#gg .choice[aria-pressed="true"]', root).dataset.v, a = +$('#ga1', root).checked, b = +$('#gb1', root).checked; $('#gout', root).textContent = `${n}(${a}${n === 'NOT' ? '' : ', ' + b}) = ${G[n](a, b)}`; $('#gtt', root).innerHTML = `<tr><th>A</th>${n === 'NOT' ? '' : '<th>B</th>'}<th>${n}</th></tr>` + (n === 'NOT' ? [0, 1].map((x) => `<tr class="${x === a ? 'on' : ''}"><td>${x}</td><td>${G[n](x)}</td></tr>`) : [[0, 0], [0, 1], [1, 0], [1, 1]].map(([x, y]) => `<tr class="${x === a && y === b ? 'on' : ''}"><td>${x}</td><td>${y}</td><td>${G[n](x, y)}</td></tr>`)).join(''); };
    $$('input', root).forEach((i) => i.addEventListener('change', draw)); $$('#gg .choice', root).forEach((b) => (b.onclick = () => { $$('#gg .choice', root).forEach((x) => x.setAttribute('aria-pressed', x === b)); draw(); })); draw();
  },
  units(root) {
    root.innerHTML = `<div class="sl-grid"><label class="sl">${t('sim.value', 'Value')}<input id="uv" type="number" value="72" step="any"></label><label class="sl">${t('sim.from', 'From')}<input id="uf" type="text" value="km/h"></label><label class="sl">${t('sim.to', 'To')}<input id="ut" type="text" value="m/s"></label></div><div id="uout" class="chips" aria-live="polite"></div><details><summary>${t('sim.units', 'Supported units')}</summary><div id="ulist" class="small muted"></div></details>`;
    const go = async () => { try { const r = await get(`/api/units/convert?value=${encodeURIComponent($('#uv', root).value)}&src=${encodeURIComponent($('#uf', root).value)}&dst=${encodeURIComponent($('#ut', root).value)}`); $('#uout', root).innerHTML = `<span class="chip"><b>${+r.result.toPrecision(8)}</b> ${esc($('#ut', root).value)}</span>`; } catch (e) { $('#uout', root).innerHTML = `<span class="chip warn">${esc(e.message)}</span>`; } };
    $$('input', root).forEach((i) => i.addEventListener('input', go)); go(); get('/api/units').then((u) => { $('#ulist', root).innerHTML = Object.entries(u).map(([k, v]) => `<p><b>${k}:</b> ${v.join(', ')}</p>`).join(''); });
  },
};

/* ============================================================ code runner (Python in the browser, HTML preview) ============================================================ */
const EXAMPLES = { 'Hello': 'name = input_name = "Asha"\nprint("Hello,", name)\nfor i in range(1, 4):\n    print(i, "x 7 =", i * 7)', 'Loop & list': 'squares = [n * n for n in range(1, 6)]\nprint(squares)\nprint(sum(squares))', 'Function': 'def is_prime(n):\n    if n < 2:\n        return False\n    for d in range(2, int(n ** 0.5) + 1):\n        if n % d == 0:\n            return False\n    return True\n\nprint([n for n in range(2, 30) if is_prime(n)])' };
export function mountCodeRunner(host) {
  host.innerHTML = `<div class="card pad sim"><div class="row"><h2 style="margin:0">💻 ${t('code.title', 'Code runner')}</h2><span class="spacer"></span><div class="choice-row" id="cl"><button class="choice" data-v="py" aria-pressed="true">Python</button><button class="choice" data-v="html" aria-pressed="false">HTML</button></div></div>
    <div class="row"><label class="small">${t('code.example', 'Example')}: <select id="cex">${Object.keys(EXAMPLES).map((k) => `<option>${k}</option>`).join('')}</select></label></div>
    <textarea id="code" class="code" spellcheck="false" rows="10" aria-label="${t('code.editor', 'Code editor')}">${esc(EXAMPLES.Hello)}</textarea>
    <div class="row"><button class="btn primary" id="run">▶ ${t('code.run', 'Run')}</button><button class="btn" id="askcode">💬 ${t('code.ask', 'Ask AIVidya about this')}</button><span class="muted small" id="cstat"></span></div>
    <pre class="output" id="cout" aria-live="polite"></pre><iframe id="prev" title="${t('code.preview', 'HTML preview')}" sandbox="" hidden></iframe><p class="muted small">${t('code.note', 'Your code runs only in your browser, in a sandbox: no network, no files.')}</p></div>`;
  const root = $('.sim', host); let mode = 'py', worker = null, seq = 0;
  $('#cex', root).onchange = (e) => { $('#code', root).value = EXAMPLES[e.target.value]; };
  $$('#cl .choice', root).forEach((b) => (b.onclick = () => { mode = b.dataset.v; $$('#cl .choice', root).forEach((x) => x.setAttribute('aria-pressed', x === b)); $('#prev', root).hidden = mode !== 'html'; $('#cout', root).hidden = mode === 'html'; $('#code', root).value = mode === 'html' ? '<h1>Hello!</h1>\n<p style="color:teal">My first page</p>\n<ul><li>one</li><li>two</li></ul>' : EXAMPLES.Hello; }));
  $('#code', root).addEventListener('keydown', (e) => { if (e.key === 'Tab') { e.preventDefault(); const el = e.target, s = el.selectionStart; el.value = el.value.slice(0, s) + '    ' + el.value.slice(el.selectionEnd); el.selectionStart = el.selectionEnd = s + 4; } if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') $('#run', root).click(); });
  $('#run', root).onclick = () => {
    const code = $('#code', root).value;
    if (mode === 'html') { $('#prev', root).srcdoc = code; return; }
    const out = $('#cout', root), stat = $('#cstat', root); out.textContent = ''; stat.textContent = t('code.running', 'Running…');
    worker ||= new Worker('/pyworker.js'); const id = ++seq; const kill = setTimeout(() => { worker.terminate(); worker = null; out.textContent += `\n⏱️ ${t('code.timeout', 'Stopped: it took longer than 10 seconds (infinite loop?)')}`; stat.textContent = ''; }, 10000);
    worker.onmessage = (e) => { if (e.data.id !== id) return; clearTimeout(kill); stat.textContent = ''; out.textContent = (e.data.output || '') + (e.data.ok ? (e.data.result ? `\n=> ${e.data.result}` : '') : `\n${e.data.error}`); out.classList.toggle('err', !e.data.ok); };
    worker.onerror = () => { clearTimeout(kill); stat.textContent = t('code.fail', 'The code runner could not start (it may still be downloading).'); };
    worker.postMessage({ id, code });
  };
  $('#askcode', root).onclick = async () => { const { L } = await import('./lesson.js'); if (!L.ctx) return toast(t('code.openlesson', 'Open this from a lesson to ask AIVidya.')); const { ask } = await import('./chat.js'); ask(`${t('code.askq', 'Here is my code. Can you explain it or tell me what is wrong?')}\n\n\`\`\`\n${$('#code', root).value}\n\`\`\`\n${$('#cout', root).textContent ? `Output:\n${$('#cout', root).textContent}` : ''}`); };
}

/* ============================================================ tools hub ============================================================ */
export async function route(view, name) {
  if (name === 'code') { view.innerHTML = `<div class="crumbs"><a href="#/tools">${t('nav.tools', 'Tools')}</a> › ${t('code.title', 'Code runner')}</div><h1 class="sr-only">${t('code.title', 'Code runner')}</h1><div id="host"></div>`; return mountCodeRunner($('#host', view)); }
  if (name && SIMS[name]) { view.innerHTML = `<div class="crumbs"><a href="#/">${t('nav.home', 'Home')}</a> › <a href="#/tools">${t('nav.tools', 'Tools')}</a> › ${esc(SIMS[name].title)}</div><h1 class="sr-only">${esc(SIMS[name].title)}</h1><div id="host"></div>`; return mountSim(name, $('#host', view)); }
  view.innerHTML = `<div class="crumbs"><a href="#/">${t('nav.home', 'Home')}</a> › ${t('nav.tools', 'Tools & simulations')}</div><h1>🧰 ${t('nav.tools', 'Tools & simulations')}</h1><p class="muted">${t('tools.help', 'Play with the ideas: change a number and watch what happens.')}</p>
    <div class="subject-grid">${Object.entries(SIMS).map(([id, s]) => `<a class="subject-card" href="#/tools/${id}"><div class="subject-icon" aria-hidden="true">${s.icon}</div><h3>${t(`sim.${id}`, s.title)}</h3></a>`).join('')}<a class="subject-card" href="#/tools/code"><div class="subject-icon" aria-hidden="true">💻</div><h3>${t('code.title', 'Code runner')}</h3></a><a class="subject-card" href="#/voicecheck"><div class="subject-icon" aria-hidden="true">🩺</div><h3>${t('voice.check', 'Voice check')}</h3></a></div>`;
}

/* ============================================================ voice check ============================================================ */
export async function renderVoiceCheck(view) {
  const lang = langInfo(state.profile?.language || 'en');
  view.innerHTML = `<div class="crumbs"><a href="#/">${t('nav.home', 'Home')}</a> › ${t('voice.check', 'Voice check')}</div><h1>🩺 ${t('voice.check', 'Voice check')}</h1><p class="muted">${t('vc.help', 'Run these tests on this device to see what will work. Language tested:')} <b>${esc(lang.name)} (${lang.speech})</b></p>
    <div class="list" id="vc"></div>`;
  const rows = [];
  const add = (title, run) => { const el = document.createElement('div'); el.className = 'card pad vc-row'; el.innerHTML = `<div class="row"><b>${title}</b><span class="spacer"></span><span class="chip" data-s>—</span><button class="btn sm" data-r>${t('vc.run', 'Run test')}</button></div><div class="muted small" data-d></div>`; $('#vc', view).append(el);
    const set = (s, d) => { $('[data-s]', el).textContent = s; $('[data-s]', el).className = `chip ${s.startsWith('✓') ? 'ok' : s.startsWith('✗') ? 'bad' : ''}`; $('[data-d]', el).innerHTML = d || ''; };
    $('[data-r]', el).onclick = async () => { set('…', ''); try { await run(set, el); } catch (e) { set(`✗ ${t('vc.fail', 'Failed')}`, esc(e.message || e)); } }; rows.push(el); };
  add(t('vc.supports', 'Browser support'), (set) => { set(supportsBrowserTTS || supportsBrowserSTT ? '✓' : '✗', `${t('vc.tts', 'Speech output')}: ${supportsBrowserTTS ? '✓' : '✗'} · ${t('vc.stt', 'Browser recognition')}: ${supportsBrowserSTT ? '✓' : '✗ (Chrome/Edge)'} · ${t('vc.rec', 'Recording')}: ${supportsRecording ? '✓' : '✗'} · ${t('vc.server', 'Server voices')}: ${serverVoice.tts.join(', ') || '—'} · ${t('vc.serverstt', 'Private recognition')}: ${serverVoice.stt ? '✓' : '✗'}`); });
  add(t('vc.voices', 'Device voices for this language'), (set) => { const all = listVoices(), mine = all.filter((v) => v.lang.toLowerCase().startsWith(lang.speech.slice(0, 2))); set(mine.length ? '✓' : '✗', mine.length ? mine.map((v) => `${esc(v.name)} (${esc(v.lang)})`).join('<br>') : `${t('vc.novoice', 'None installed')} (${all.length} ${t('vc.total', 'voices in total')}). ${serverVoice.tts.includes(lang.id) ? t('vc.useserver', 'The server voice can be used instead.') : ''}`); });
  add(t('vc.speak', 'Hear the device voice'), (set) => new Promise((resolve) => { if (!supportsBrowserTTS) throw new Error('Not supported'); const t0 = performance.now(); speaker.begin({ lang: lang.speech, langCode: lang.id, rate: 1, engine: 'browser', voiceURI: state.settings.voiceByLang[lang.id] || '', onIdle: () => { set('✓', t('vc.askheard', 'Did you hear it? If not, check volume or the voice list above.')); resolve(); }, onFail: (why) => { set('✗', esc(why)); resolve(); } }); speaker.push(t('voice.sample', 'Hello! I am AIVidya, your teacher. Let us learn something wonderful today.')); speaker.end(); void t0; }));
  add(t('vc.serverspeak', 'Hear the server voice'), (set) => new Promise((resolve) => { if (!serverVoice.tts.includes(lang.id)) throw new Error(t('vc.noserver', 'No server voice for this language')); speaker.begin({ lang: lang.speech, langCode: lang.id, rate: 1, engine: 'server', onIdle: () => { set('✓', t('vc.askheard', 'Did you hear it?')); resolve(); }, onFail: (why) => { set('✗', esc(why)); resolve(); } }); speaker.push(t('voice.sample', 'Hello! I am AIVidya, your teacher.')); speaker.end(); set('…', t('vc.dl', 'The first time, the voice file downloads (20–80 MB).')); }));
  add(t('vc.mic', 'Microphone & level'), async (set, el) => { const s = await navigator.mediaDevices.getUserMedia({ audio: true }); const ctx = new AudioContext(), an = ctx.createAnalyser(); ctx.createMediaStreamSource(s).connect(an); const buf = new Uint8Array(an.fftSize); let max = 0; const end = performance.now() + 3000; set('…', t('vc.speaknow', 'Say something for 3 seconds…')); await new Promise((r) => { const iv = setInterval(() => { an.getByteTimeDomainData(buf); let sum = 0; for (const v of buf) sum += ((v - 128) / 128) ** 2; max = Math.max(max, Math.sqrt(sum / buf.length)); $('[data-d]', el).innerHTML = `<div class="bar"><i style="width:${Math.min(100, max * 300)}%"></i></div>`; if (performance.now() > end) { clearInterval(iv); r(); } }, 60); }); s.getTracks().forEach((x) => x.stop()); ctx.close(); set(max > 0.02 ? '✓' : '✗', max > 0.02 ? t('vc.micok', 'Your microphone works.') : t('vc.micquiet', 'Very quiet — check the microphone volume or choose another input.')); });
  add(t('vc.browserstt', 'Browser recognition'), (set) => new Promise((resolve, reject) => { if (!supportsBrowserSTT) return reject(new Error('Not supported (use Chrome or Edge)')); set('…', t('vc.speaknow', 'Say something…')); listener.start({ lang: lang.speech, langCode: lang.id, onFinal: ({ text, confidence }) => set('✓', `“${esc(text)}” (${Math.round((confidence || 0) * 100)}%)`), onEnd: (got) => { if (!got) set('✗', t('vc.nothing', 'Nothing was heard')); resolve(); }, onError: (e) => { set('✗', esc(e)); resolve(); } }); }));
  add(t('vc.serverstt', 'Private recognition (server)'), async (set) => { if (!serverVoice.stt) throw new Error(t('vc.nostt', 'Not installed on this server')); const prev = state.settings.sttEngine; state.settings.sttEngine = 'server'; set('…', t('vc.speaknow', 'Say something…')); await new Promise((resolve) => { listener.start({ lang: lang.speech, langCode: lang.id, onFinal: ({ text, confidence }) => set('✓', `“${esc(text)}” (${Math.round((confidence || 0) * 100)}%)`), onEnd: (got) => { if (!got) set('✗', t('vc.nothing', 'Nothing was heard')); resolve(); }, onError: (e) => { set('✗', esc(e)); resolve(); } }); }); state.settings.sttEngine = prev; });
  add(t('vc.vad', 'Interrupt by speaking (barge-in)'), async (set) => { const { startBargeIn } = await import('./voice.js'); set('…', t('vc.speaknow', 'Say something…')); const stop = await startBargeIn(() => { set('✓', t('vc.vadok', 'Heard you — interrupting would work.')); stop?.(); }); if (!stop) throw new Error('No microphone'); setTimeout(() => stop(), 6000); });
  $$('[data-r]', view)[0].click(); $$('[data-r]', view)[1].click();
}
