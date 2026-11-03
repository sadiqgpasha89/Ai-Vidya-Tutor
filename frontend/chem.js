// Chemistry tools: periodic table, equation balancer (exact rational arithmetic), and 3D ball-and-stick molecules.
import { t } from './i18n.js';
import { esc } from './render.js';
import { $, $$ } from './ui.js';

// [Z, symbol, name, atomic mass, group (0 = f-block), period, category]
const E = `1,H,Hydrogen,1.008,1,1,nonmetal;2,He,Helium,4.0026,18,1,noble;3,Li,Lithium,6.94,1,2,alkali;4,Be,Beryllium,9.0122,2,2,alkaline;5,B,Boron,10.81,13,2,metalloid;6,C,Carbon,12.011,14,2,nonmetal;7,N,Nitrogen,14.007,15,2,nonmetal;8,O,Oxygen,15.999,16,2,nonmetal;9,F,Fluorine,18.998,17,2,halogen;10,Ne,Neon,20.180,18,2,noble;
11,Na,Sodium,22.990,1,3,alkali;12,Mg,Magnesium,24.305,2,3,alkaline;13,Al,Aluminium,26.982,13,3,post;14,Si,Silicon,28.085,14,3,metalloid;15,P,Phosphorus,30.974,15,3,nonmetal;16,S,Sulphur,32.06,16,3,nonmetal;17,Cl,Chlorine,35.45,17,3,halogen;18,Ar,Argon,39.948,18,3,noble;19,K,Potassium,39.098,1,4,alkali;20,Ca,Calcium,40.078,2,4,alkaline;
21,Sc,Scandium,44.956,3,4,transition;22,Ti,Titanium,47.867,4,4,transition;23,V,Vanadium,50.942,5,4,transition;24,Cr,Chromium,51.996,6,4,transition;25,Mn,Manganese,54.938,7,4,transition;26,Fe,Iron,55.845,8,4,transition;27,Co,Cobalt,58.933,9,4,transition;28,Ni,Nickel,58.693,10,4,transition;29,Cu,Copper,63.546,11,4,transition;30,Zn,Zinc,65.38,12,4,transition;
31,Ga,Gallium,69.723,13,4,post;32,Ge,Germanium,72.630,14,4,metalloid;33,As,Arsenic,74.922,15,4,metalloid;34,Se,Selenium,78.971,16,4,nonmetal;35,Br,Bromine,79.904,17,4,halogen;36,Kr,Krypton,83.798,18,4,noble;37,Rb,Rubidium,85.468,1,5,alkali;38,Sr,Strontium,87.62,2,5,alkaline;39,Y,Yttrium,88.906,3,5,transition;40,Zr,Zirconium,91.224,4,5,transition;
41,Nb,Niobium,92.906,5,5,transition;42,Mo,Molybdenum,95.95,6,5,transition;43,Tc,Technetium,98,7,5,transition;44,Ru,Ruthenium,101.07,8,5,transition;45,Rh,Rhodium,102.91,9,5,transition;46,Pd,Palladium,106.42,10,5,transition;47,Ag,Silver,107.87,11,5,transition;48,Cd,Cadmium,112.41,12,5,transition;49,In,Indium,114.82,13,5,post;50,Sn,Tin,118.71,14,5,post;
51,Sb,Antimony,121.76,15,5,metalloid;52,Te,Tellurium,127.60,16,5,metalloid;53,I,Iodine,126.90,17,5,halogen;54,Xe,Xenon,131.29,18,5,noble;55,Cs,Caesium,132.91,1,6,alkali;56,Ba,Barium,137.33,2,6,alkaline;57,La,Lanthanum,138.91,0,6,lanthanide;58,Ce,Cerium,140.12,0,6,lanthanide;59,Pr,Praseodymium,140.91,0,6,lanthanide;60,Nd,Neodymium,144.24,0,6,lanthanide;
61,Pm,Promethium,145,0,6,lanthanide;62,Sm,Samarium,150.36,0,6,lanthanide;63,Eu,Europium,151.96,0,6,lanthanide;64,Gd,Gadolinium,157.25,0,6,lanthanide;65,Tb,Terbium,158.93,0,6,lanthanide;66,Dy,Dysprosium,162.50,0,6,lanthanide;67,Ho,Holmium,164.93,0,6,lanthanide;68,Er,Erbium,167.26,0,6,lanthanide;69,Tm,Thulium,168.93,0,6,lanthanide;70,Yb,Ytterbium,173.05,0,6,lanthanide;
71,Lu,Lutetium,174.97,3,6,transition;72,Hf,Hafnium,178.49,4,6,transition;73,Ta,Tantalum,180.95,5,6,transition;74,W,Tungsten,183.84,6,6,transition;75,Re,Rhenium,186.21,7,6,transition;76,Os,Osmium,190.23,8,6,transition;77,Ir,Iridium,192.22,9,6,transition;78,Pt,Platinum,195.08,10,6,transition;79,Au,Gold,196.97,11,6,transition;80,Hg,Mercury,200.59,12,6,transition;
81,Tl,Thallium,204.38,13,6,post;82,Pb,Lead,207.2,14,6,post;83,Bi,Bismuth,208.98,15,6,post;84,Po,Polonium,209,16,6,metalloid;85,At,Astatine,210,17,6,halogen;86,Rn,Radon,222,18,6,noble;87,Fr,Francium,223,1,7,alkali;88,Ra,Radium,226,2,7,alkaline;89,Ac,Actinium,227,0,7,actinide;90,Th,Thorium,232.04,0,7,actinide;
91,Pa,Protactinium,231.04,0,7,actinide;92,U,Uranium,238.03,0,7,actinide;93,Np,Neptunium,237,0,7,actinide;94,Pu,Plutonium,244,0,7,actinide;95,Am,Americium,243,0,7,actinide;96,Cm,Curium,247,0,7,actinide;97,Bk,Berkelium,247,0,7,actinide;98,Cf,Californium,251,0,7,actinide;99,Es,Einsteinium,252,0,7,actinide;100,Fm,Fermium,257,0,7,actinide;
101,Md,Mendelevium,258,0,7,actinide;102,No,Nobelium,259,0,7,actinide;103,Lr,Lawrencium,266,3,7,transition;104,Rf,Rutherfordium,267,4,7,transition;105,Db,Dubnium,268,5,7,transition;106,Sg,Seaborgium,269,6,7,transition;107,Bh,Bohrium,270,7,7,transition;108,Hs,Hassium,277,8,7,transition;109,Mt,Meitnerium,278,9,7,unknown;110,Ds,Darmstadtium,281,10,7,unknown;
111,Rg,Roentgenium,282,11,7,unknown;112,Cn,Copernicium,285,12,7,transition;113,Nh,Nihonium,286,13,7,unknown;114,Fl,Flerovium,289,14,7,unknown;115,Mc,Moscovium,290,15,7,unknown;116,Lv,Livermorium,293,16,7,unknown;117,Ts,Tennessine,294,17,7,unknown;118,Og,Oganesson,294,18,7,unknown`;
export const ELEMENTS = E.replace(/\n/g, '').split(';').map((r) => { const [z, sym, name, mass, group, period, cat] = r.split(','); return { z: +z, sym, name, mass: +mass, group: +group, period: +period, cat }; });
const CAT = { alkali: '#f87171', alkaline: '#fb923c', transition: '#fbbf24', post: '#a3e635', metalloid: '#34d399', nonmetal: '#38bdf8', halogen: '#22d3ee', noble: '#a78bfa', lanthanide: '#f472b6', actinide: '#e879f9', unknown: '#9ca3af' };
const catLabel = { alkali: 'Alkali metal', alkaline: 'Alkaline earth metal', transition: 'Transition metal', post: 'Post-transition metal', metalloid: 'Metalloid', nonmetal: 'Reactive non-metal', halogen: 'Halogen', noble: 'Noble gas', lanthanide: 'Lanthanide', actinide: 'Actinide', unknown: 'Unknown properties' };

export function periodic(root) {
  const cell = (el, col, row) => `<button class="el" style="grid-column:${col};grid-row:${row};background:${CAT[el.cat]}" data-z="${el.z}" aria-label="${el.name}"><small>${el.z}</small><b>${el.sym}</b></button>`;
  const f = ELEMENTS.filter((e) => e.group === 0); const main = ELEMENTS.filter((e) => e.group !== 0);
  let g = main.map((e) => cell(e, e.group, e.period)).join('');
  g += f.map((e, i) => cell(e, 3 + (e.z >= 89 ? e.z - 89 : e.z - 57), e.z >= 89 ? 10 : 9)).join('');
  root.innerHTML = `<div class="ptable-wrap"><div class="ptable">${g}</div></div><div class="row legend">${Object.entries(CAT).map(([k, c]) => `<span class="chip" style="background:${c}33;border:1px solid ${c}">${t('cat.' + k, catLabel[k])}</span>`).join('')}</div>
    <div id="elinfo" class="card pad" aria-live="polite">${t('pt.tap', 'Tap an element.')}</div>`;
  $$('.el', root).forEach((b) => (b.onclick = () => { const e = ELEMENTS[+b.dataset.z - 1]; const shells = []; let n = e.z; for (const cap of [2, 8, 18, 32, 32, 18, 8]) { if (n <= 0) break; shells.push(Math.min(cap, n)); n -= cap; }
    $('#elinfo', root).innerHTML = `<h3 style="margin:0">${e.sym} — ${esc(e.name)}</h3><p>${t('pt.z', 'Atomic number')}: <b>${e.z}</b> · ${t('pt.mass', 'Atomic mass')}: <b>${e.mass}</b> · ${t('pt.period', 'Period')}: <b>${e.period}</b> · ${t('pt.group', 'Group')}: <b>${e.group || '—'}</b> · ${esc(t('cat.' + e.cat, catLabel[e.cat]))}</p><p>${t('pt.shells', 'Electrons in shells (K, L, M…)')}: <b>${shells.join(', ')}</b> · ${t('pt.protons', 'Protons')} = ${t('pt.electrons', 'electrons')} = ${e.z} · ${t('pt.neutrons', 'Neutrons (most common isotope)')} ≈ ${Math.round(e.mass) - e.z}</p>`; }));
}

// ---- equation balancer ----------------------------------------------------------------------------------------------
const gcd = (a, b) => { a = a < 0n ? -a : a; b = b < 0n ? -b : b; while (b) [a, b] = [b, a % b]; return a; };
class Fr { constructor(n, d = 1n) { if (d < 0n) { n = -n; d = -d; } const g = gcd(n, d) || 1n; this.n = n / g; this.d = d / g; } add(o) { return new Fr(this.n * o.d + o.n * this.d, this.d * o.d); } sub(o) { return new Fr(this.n * o.d - o.n * this.d, this.d * o.d); } mul(o) { return new Fr(this.n * o.n, this.d * o.d); } div(o) { return new Fr(this.n * o.d, this.d * o.n); } isZero() { return this.n === 0n; } }
function parseFormula(f) { // -> {Fe: 2, O: 3}; supports ( ) groups and hydrates like CuSO4.5H2O
  const [main, ...hyd] = f.split(/[.·*]/); const total = {};
  const parse = (s, mult) => { const stack = [{}]; const re = /([A-Z][a-z]?)(\d*)|(\()|(\))(\d*)/g; let m; while ((m = re.exec(s))) { if (m[1]) { const c = stack[stack.length - 1]; c[m[1]] = (c[m[1]] || 0) + (m[2] ? +m[2] : 1); } else if (m[3]) stack.push({}); else if (m[4]) { const inner = stack.pop(), k = m[5] ? +m[5] : 1, top = stack[stack.length - 1]; for (const [el, c] of Object.entries(inner)) top[el] = (top[el] || 0) + c * k; } } for (const [el, c] of Object.entries(stack[0])) total[el] = (total[el] || 0) + c * mult; };
  parse(main.replace(/^\d+/, ''), 1); hyd.forEach((h) => { const m = /^(\d+)(.*)$/.exec(h); parse(m ? m[2] : h, m ? +m[1] : 1); });
  if (!Object.keys(total).length) throw new Error(`Cannot read “${f}”`); return total;
}
export function balance(eq) {
  const [l, r] = eq.replace(/→|⟶|=>|->|=/g, '=').split('='); if (!r) throw new Error('Write the equation like: H2 + O2 -> H2O');
  const side = (s) => s.split('+').map((x) => x.trim().replace(/^\d+\s*/, '')).filter(Boolean); const L = side(l), R = side(r), all = [...L, ...R]; const comps = all.map(parseFormula);
  const els = [...new Set(comps.flatMap((c) => Object.keys(c)))]; const rows = els.map((el) => comps.map((c, j) => new Fr(BigInt((c[el] || 0) * (j < L.length ? 1 : -1))))); const n = all.length;
  let lead = 0; const piv = []; for (let c = 0; c < n && lead < rows.length; c++) { let p = lead; while (p < rows.length && rows[p][c].isZero()) p++; if (p === rows.length) continue; [rows[lead], rows[p]] = [rows[p], rows[lead]]; const pv = rows[lead][c]; rows[lead] = rows[lead].map((x) => x.div(pv)); rows.forEach((row, i) => { if (i !== lead && !row[c].isZero()) { const k = row[c]; rows[i] = row.map((x, j) => x.sub(k.mul(rows[lead][j]))); } }); piv.push(c); lead++; }
  const free = [...Array(n).keys()].filter((c) => !piv.includes(c)); if (free.length !== 1) throw new Error(free.length ? 'This equation has more than one solution - check the formulas.' : 'This cannot be balanced - check the formulas.');
  const sol = Array(n).fill(null); sol[free[0]] = new Fr(1n); piv.forEach((c, i) => { sol[c] = new Fr(0n).sub(rows[i][free[0]]); });
  let den = 1n; sol.forEach((x) => { den = (den * x.d) / gcd(den, x.d); }); const co = sol.map((x) => (x.n * den) / x.d); if (co.some((x) => x <= 0n)) throw new Error('No positive whole-number solution - check the formulas.');
  const g = co.reduce((a, b) => gcd(a, b)); const nums = co.map((x) => Number(x / g)); const fmt = (names, off) => names.map((nm, i) => `${nums[off + i] > 1 ? nums[off + i] : ''}${nm}`).join(' + ');
  return { text: `${fmt(L, 0)} → ${fmt(R, L.length)}`, coefficients: nums, species: all };
}
export function balancer(root) {
  const examples = ['H2 + O2 -> H2O', 'Fe + O2 -> Fe2O3', 'C3H8 + O2 -> CO2 + H2O', 'Al + H2SO4 -> Al2(SO4)3 + H2', 'KMnO4 + HCl -> KCl + MnCl2 + H2O + Cl2'];
  root.innerHTML = `<div class="field"><label for="beq">${t('bal.input', 'Unbalanced equation')}</label><input id="beq" type="text" value="${examples[2]}" autocomplete="off"></div><div class="row">${examples.map((e) => `<button class="chip" data-e="${esc(e)}">${esc(e)}</button>`).join('')}</div><div id="bout" class="explain" aria-live="polite"></div><div id="bmass" class="muted small"></div>`;
  const go = () => { const out = $('#bout', root), mass = $('#bmass', root); try { const r = balance($('#beq', root).value); out.className = 'explain good'; out.innerHTML = `<b style="font-size:1.2rem">${esc(r.text)}</b>`;
    mass.textContent = r.species.map((s, i) => { const f = parseFormula(s); const m = Object.entries(f).reduce((a, [el, c]) => a + c * (ELEMENTS.find((x) => x.sym === el)?.mass || 0), 0); return `${s}: ${m.toFixed(2)} g/mol × ${r.coefficients[i]}`; }).join('  |  '); } catch (e) { out.className = 'explain bad'; out.textContent = e.message; mass.textContent = ''; } };
  $('#beq', root).addEventListener('input', go); $$('[data-e]', root).forEach((b) => (b.onclick = () => { $('#beq', root).value = b.dataset.e; go(); })); go();
}

// ---- 3D molecules --------------------------------------------------------------------------------------------------------
const COL = { H: '#e5e7eb', C: '#374151', O: '#ef4444', N: '#3b82f6', Cl: '#22c55e', F: '#a3e635', B: '#f59e0b', S: '#facc15' }; const RAD = { H: 9, C: 16, O: 15, N: 15, Cl: 19, F: 12, B: 15, S: 20 };
const ring = (r, z, el, n) => Array.from({ length: n }, (_, i) => [el, r * Math.cos((2 * Math.PI * i) / n), r * Math.sin((2 * Math.PI * i) / n), z]);
const MOLS = {
  'Water H₂O': { atoms: [['O', 0, 0, 0], ['H', 0.757, 0.586, 0], ['H', -0.757, 0.586, 0]], bonds: [[0, 1, 1], [0, 2, 1]], note: 'Bent, 104.5°' },
  'Carbon dioxide CO₂': { atoms: [['C', 0, 0, 0], ['O', 1.16, 0, 0], ['O', -1.16, 0, 0]], bonds: [[0, 1, 2], [0, 2, 2]], note: 'Linear, 180°' },
  'Methane CH₄': { atoms: [['C', 0, 0, 0], ['H', 0.63, 0.63, 0.63], ['H', -0.63, -0.63, 0.63], ['H', -0.63, 0.63, -0.63], ['H', 0.63, -0.63, -0.63]], bonds: [[0, 1, 1], [0, 2, 1], [0, 3, 1], [0, 4, 1]], note: 'Tetrahedral, 109.5°' },
  'Ammonia NH₃': { atoms: [['N', 0, 0, 0], ['H', 0.94, -0.33, 0], ['H', -0.47, -0.33, 0.81], ['H', -0.47, -0.33, -0.81]], bonds: [[0, 1, 1], [0, 2, 1], [0, 3, 1]], note: 'Trigonal pyramidal, 107°' },
  'Ethene C₂H₄': { atoms: [['C', 0.67, 0, 0], ['C', -0.67, 0, 0], ['H', 1.24, 0.93, 0], ['H', 1.24, -0.93, 0], ['H', -1.24, 0.93, 0], ['H', -1.24, -0.93, 0]], bonds: [[0, 1, 2], [0, 2, 1], [0, 3, 1], [1, 4, 1], [1, 5, 1]], note: 'Planar, 120°' },
  'Ethyne C₂H₂': { atoms: [['C', 0.6, 0, 0], ['C', -0.6, 0, 0], ['H', 1.66, 0, 0], ['H', -1.66, 0, 0]], bonds: [[0, 1, 3], [0, 2, 1], [1, 3, 1]], note: 'Linear, triple bond' },
  'Hydrogen chloride HCl': { atoms: [['H', -0.63, 0, 0], ['Cl', 0.63, 0, 0]], bonds: [[0, 1, 1]], note: 'Polar covalent' },
  'Oxygen O₂': { atoms: [['O', 0.6, 0, 0], ['O', -0.6, 0, 0]], bonds: [[0, 1, 2]], note: 'Double bond' },
  'Nitrogen N₂': { atoms: [['N', 0.55, 0, 0], ['N', -0.55, 0, 0]], bonds: [[0, 1, 3]], note: 'Triple bond' },
  'Boron trifluoride BF₃': { atoms: [['B', 0, 0, 0], ['F', 1.3, 0, 0], ['F', -0.65, 1.126, 0], ['F', -0.65, -1.126, 0]], bonds: [[0, 1, 1], [0, 2, 1], [0, 3, 1]], note: 'Trigonal planar, 120° (incomplete octet)' },
  'Sulphur hexafluoride SF₆': { atoms: [['S', 0, 0, 0], ['F', 1.56, 0, 0], ['F', -1.56, 0, 0], ['F', 0, 1.56, 0], ['F', 0, -1.56, 0], ['F', 0, 0, 1.56], ['F', 0, 0, -1.56]], bonds: [[0, 1, 1], [0, 2, 1], [0, 3, 1], [0, 4, 1], [0, 5, 1], [0, 6, 1]], note: 'Octahedral, 90° (expanded octet)' },
  'Benzene C₆H₆': { atoms: [...ring(1.4, 0, 'C', 6), ...ring(2.48, 0, 'H', 6)], bonds: [...Array.from({ length: 6 }, (_, i) => [i, (i + 1) % 6, i % 2 ? 1 : 2]), ...Array.from({ length: 6 }, (_, i) => [i, i + 6, 1])], note: 'Planar ring, delocalised electrons' },
};
export function molecules(root) {
  root.innerHTML = `<div class="field"><label for="mol">${t('mol.pick', 'Molecule')}</label><select id="mol">${Object.keys(MOLS).map((k) => `<option>${k}</option>`).join('')}</select></div><canvas id="mc" width="560" height="360" class="plot" role="img" aria-label="3D molecule"></canvas><p class="muted small" id="mnote"></p><p class="muted small">${t('mol.drag', 'Drag to rotate. It also spins slowly by itself.')}</p>`;
  const cv = $('#mc', root), ctx = cv.getContext('2d'); let ay = 0.6, ax = 0.3, drag = null, raf = 0, mol = MOLS[Object.keys(MOLS)[0]];
  const set = () => { mol = MOLS[$('#mol', root).value]; $('#mnote', root).textContent = mol.note; }; $('#mol', root).onchange = set; set();
  cv.onpointerdown = (e) => { drag = [e.clientX, e.clientY]; cv.setPointerCapture(e.pointerId); }; cv.onpointerup = () => { drag = null; }; cv.onpointermove = (e) => { if (!drag) return; ay += (e.clientX - drag[0]) * 0.01; ax += (e.clientY - drag[1]) * 0.01; drag = [e.clientX, e.clientY]; };
  const proj = ([el, x, y, z]) => { const cy = Math.cos(ay), sy = Math.sin(ay), cx = Math.cos(ax), sx = Math.sin(ax); const x1 = x * cy + z * sy, z1 = -x * sy + z * cy, y1 = y * cx - z1 * sx, z2 = y * sx + z1 * cx; const s = 90 / (1 + z2 * 0.05); return { el, X: 280 + x1 * s, Y: 180 - y1 * s, z: z2, r: (RAD[el] || 14) * (1 + z2 * 0.05) }; };
  const loop = () => { if (!root.isConnected) return; if (!drag) ay += 0.008; const P = mol.atoms.map(proj); ctx.clearRect(0, 0, 560, 360); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, 560, 360);
    const items = [...mol.bonds.map(([a, b, o]) => ({ kind: 'b', a: P[a], b: P[b], o, z: (P[a].z + P[b].z) / 2 })), ...P.map((p) => ({ kind: 'a', p, z: p.z }))].sort((u, v) => u.z - v.z);
    for (const it of items) { if (it.kind === 'b') { const { a, b, o } = it; const dx = b.X - a.X, dy = b.Y - a.Y, len = Math.hypot(dx, dy) || 1, nx = -dy / len, ny = dx / len; ctx.strokeStyle = '#6b7280'; ctx.lineWidth = 4; for (let k = 0; k < o; k++) { const off = (k - (o - 1) / 2) * 7; ctx.beginPath(); ctx.moveTo(a.X + nx * off, a.Y + ny * off); ctx.lineTo(b.X + nx * off, b.Y + ny * off); ctx.stroke(); } } else { const { p } = it; const g = ctx.createRadialGradient(p.X - p.r / 3, p.Y - p.r / 3, 2, p.X, p.Y, p.r); g.addColorStop(0, '#fff'); g.addColorStop(1, COL[p.el] || '#9ca3af'); ctx.fillStyle = g; ctx.beginPath(); ctx.arc(p.X, p.Y, p.r, 0, 6.3); ctx.fill(); ctx.strokeStyle = '#111'; ctx.lineWidth = 1; ctx.stroke(); ctx.fillStyle = '#111'; ctx.font = '12px sans-serif'; ctx.textAlign = 'center'; ctx.fillText(p.el, p.X, p.Y + 4); } }
    raf = requestAnimationFrame(loop); };
  raf = requestAnimationFrame(loop); import('./app.js').then((m) => m.setLeave(() => cancelAnimationFrame(raf)));
}
