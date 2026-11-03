// A small, safe expression evaluator (no eval / new Function, so it works under a strict Content-Security-Policy).
const FUNCS = { sin: Math.sin, cos: Math.cos, tan: Math.tan, asin: Math.asin, acos: Math.acos, atan: Math.atan, sqrt: Math.sqrt, abs: Math.abs, ln: Math.log, log: Math.log10, exp: Math.exp, floor: Math.floor, ceil: Math.ceil, sign: Math.sign };
const CONSTS = { pi: Math.PI, e: Math.E };

export function compile(src) {
  const toks = src.replace(/\s+/g, '').replace(/×/g, '*').replace(/−/g, '-').match(/\d+\.?\d*(?:e[-+]?\d+)?|[a-z_]\w*|\*\*|[-+*/^(),]/gi);
  if (!toks || toks.join('') !== src.replace(/\s+/g, '').replace(/×/g, '*').replace(/−/g, '-')) throw new Error('Unsupported characters');
  let i = 0; const peek = () => toks[i], next = () => toks[i++];
  function primary() {
    const tk = next(); if (tk === undefined) throw new Error('Unexpected end');
    if (tk === '(') { const v = sum(); if (next() !== ')') throw new Error('Missing )'); return v; }
    if (/^\d/.test(tk)) { const n = parseFloat(tk); return () => n; }
    if (peek() === '(') { next(); const fname = tk.toLowerCase(); const f = Object.hasOwn(FUNCS, fname) ? FUNCS[fname] : null; if (!f) throw new Error(`Unknown function ${tk}`); const a = sum(); if (next() !== ')') throw new Error('Missing )'); return (s) => f(a(s)); }
    const name = tk.toLowerCase(); if (Object.hasOwn(CONSTS, name)) return () => CONSTS[name];
    return (s) => { if (!Object.hasOwn(s, name)) throw new Error(`Unknown name ${tk}`); return s[name]; };
  }
  function unary() { return primary(); }
  function unaryMinus() { if (peek() === '-') { next(); const v = unaryMinus(); return (s) => -v(s); } if (peek() === '+') { next(); return unaryMinus(); } return power(); }
  function power() { const base = primary(); if (peek() === '^' || peek() === '**') { next(); const exp = unaryPow(); return (s) => base(s) ** exp(s); } return base; }
  function unaryPow() { if (peek() === '-') { next(); const v = unaryPow(); return (s) => -v(s); } return power(); }
  function product() { let l = unaryMinus(); while (peek() === '*' || peek() === '/' || (peek() && (/^[a-z(\d]/i.test(peek())) && peek() !== undefined && !['+', '-', ')', ','].includes(peek()))) { const op = ['*', '/'].includes(peek()) ? next() : '*'; const r = unaryMinus(); const a = l; l = op === '*' ? (s) => a(s) * r(s) : (s) => a(s) / r(s); } return l; }
  function sum() { let l = product(); while (peek() === '+' || peek() === '-') { const op = next(); const r = product(); const a = l; l = op === '+' ? (s) => a(s) + r(s) : (s) => a(s) - r(s); } return l; }
  const f = sum(); if (i !== toks.length) throw new Error('Unexpected input');
  return f;
}
