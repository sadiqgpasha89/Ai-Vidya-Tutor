// Markdown + LaTeX rendering (sanitised) and turning text into something a speech engine reads well.
import { esc } from './ui.js';
export { esc };

export function md(src) {
  if (!src) return '';
  const maths = [];
  const stash = (tex, display) => { maths.push({ tex, display }); return `@@M${maths.length - 1}@@`; };
  const text = String(src)
    .replace(/\$\$([\s\S]+?)\$\$/g, (_, t) => stash(t, true))
    .replace(/\\\[([\s\S]+?)\\\]/g, (_, t) => stash(t, true))
    .replace(/\\\(([\s\S]+?)\\\)/g, (_, t) => stash(t, false))
    .replace(/\$([^\n$]+?)\$/g, (_, t) => stash(t, false));
  let html = typeof window !== 'undefined' && window.marked ? window.marked.parse(text, { gfm: true, breaks: true }) : `<p>${esc(text).replace(/\n/g, '<br>')}</p>`;
  if (typeof window !== 'undefined' && window.DOMPurify) html = window.DOMPurify.sanitize(html);
  return html.replace(/@@M(\d+)@@/g, (_, i) => {
    const { tex, display } = maths[+i];
    if (typeof window === 'undefined' || !window.katex) return esc(tex);
    try { return window.katex.renderToString(tex, { displayMode: display, throwOnError: false }); } catch { return esc(tex); }
  });
}

// ---- speech clean-up ------------------------------------------------------------------------------
const GREEK = { alpha: 'alpha', beta: 'beta', gamma: 'gamma', delta: 'delta', Delta: 'delta', theta: 'theta', lambda: 'lambda', mu: 'mu', pi: 'pi', rho: 'rho', sigma: 'sigma', omega: 'omega', Omega: 'omega', phi: 'phi', epsilon: 'epsilon', tau: 'tau', eta: 'eta', nu: 'nu' };
// operator words per language (best effort for the Indian languages; English is the reference)
const OPS = {
  en: { plus: 'plus', minus: 'minus', times: 'times', div: 'divided by', eq: 'equals', sq: 'squared', cube: 'cubed', pow: 'to the power', root: 'square root of', over: 'over', per: 'per', deg: 'degrees', gives: 'gives', approx: 'approximately', ne: 'not equal to', le: 'less than or equal to', ge: 'greater than or equal to' },
  hi: { plus: 'जोड़', minus: 'घटा', times: 'गुणा', div: 'भाग', eq: 'बराबर', sq: 'का वर्ग', cube: 'का घन', pow: 'घात', root: 'वर्गमूल', over: 'बटा', per: 'प्रति', deg: 'डिग्री', gives: 'से मिलता है', approx: 'लगभग', ne: 'बराबर नहीं', le: 'से कम या बराबर', ge: 'से अधिक या बराबर' },
  mr: { plus: 'अधिक', minus: 'वजा', times: 'गुणिले', div: 'भागिले', eq: 'बरोबर', sq: 'वर्ग', cube: 'घन', pow: 'घात', root: 'वर्गमूळ', over: 'भागिले', per: 'प्रति', deg: 'अंश', gives: 'येते', approx: 'सुमारे', ne: 'बरोबर नाही', le: 'पेक्षा कमी किंवा बरोबर', ge: 'पेक्षा जास्त किंवा बरोबर' },
  bn: { plus: 'যোগ', minus: 'বিয়োগ', times: 'গুণ', div: 'ভাগ', eq: 'সমান', sq: 'বর্গ', cube: 'ঘন', pow: 'ঘাত', root: 'বর্গমূল', over: 'ভাগ', per: 'প্রতি', deg: 'ডিগ্রি', gives: 'পাওয়া যায়', approx: 'প্রায়', ne: 'সমান নয়', le: 'ছোট বা সমান', ge: 'বড় বা সমান' },
  te: { plus: 'ప్లస్', minus: 'మైనస్', times: 'గుణకారం', div: 'భాగహారం', eq: 'సమానం', sq: 'వర్గం', cube: 'ఘనం', pow: 'ఘాతం', root: 'వర్గమూలం', over: 'భాగించు', per: 'ప్రతి', deg: 'డిగ్రీలు', gives: 'వస్తుంది', approx: 'సుమారు', ne: 'సమానం కాదు', le: 'తక్కువ లేదా సమానం', ge: 'ఎక్కువ లేదా సమానం' },
  ta: { plus: 'கூட்டல்', minus: 'கழித்தல்', times: 'பெருக்கல்', div: 'வகுத்தல்', eq: 'சமம்', sq: 'வர்க்கம்', cube: 'கனம்', pow: 'அடுக்கு', root: 'வர்க்கமூலம்', over: 'வகுத்தல்', per: 'ஒன்றுக்கு', deg: 'டிகிரி', gives: 'கிடைக்கும்', approx: 'ஏறத்தாழ', ne: 'சமமில்லை', le: 'குறைவு அல்லது சமம்', ge: 'அதிகம் அல்லது சமம்' },
  kn: { plus: 'ಕೂಡು', minus: 'ಕಳೆ', times: 'ಗುಣಿಸು', div: 'ಭಾಗಿಸು', eq: 'ಸಮ', sq: 'ವರ್ಗ', cube: 'ಘನ', pow: 'ಘಾತ', root: 'ವರ್ಗಮೂಲ', over: 'ಭಾಗಿಸು', per: 'ಪ್ರತಿ', deg: 'ಡಿಗ್ರಿ', gives: 'ಬರುತ್ತದೆ', approx: 'ಸುಮಾರು', ne: 'ಸಮವಲ್ಲ', le: 'ಕಡಿಮೆ ಅಥವಾ ಸಮ', ge: 'ಹೆಚ್ಚು ಅಥವಾ ಸಮ' },
  gu: { plus: 'વત્તા', minus: 'ઓછા', times: 'ગુણ્યા', div: 'ભાગ્યા', eq: 'બરાબર', sq: 'નો વર્ગ', cube: 'નો ઘન', pow: 'ઘાત', root: 'વર્ગમૂળ', over: 'ઉપર', per: 'પ્રતિ', deg: 'અંશ', gives: 'આપે છે', approx: 'લગભગ', ne: 'બરાબર નથી', le: 'થી ઓછું અથવા બરાબર', ge: 'થી વધુ અથવા બરાબર' },
  ur: { plus: 'جمع', minus: 'منفی', times: 'ضرب', div: 'تقسیم', eq: 'برابر', sq: 'کا مربع', cube: 'کا مکعب', pow: 'طاقت', root: 'جذر', over: 'بر', per: 'فی', deg: 'ڈگری', gives: 'دیتا ہے', approx: 'تقریباً', ne: 'برابر نہیں', le: 'سے کم یا برابر', ge: 'سے زیادہ یا برابر' },
  or: { plus: 'ଯୋଗ', minus: 'ବିୟୋଗ', times: 'ଗୁଣନ', div: 'ଭାଗ', eq: 'ସମାନ', sq: 'ବର୍ଗ', cube: 'ଘନ', pow: 'ଘାତ', root: 'ବର୍ଗମୂଳ', over: 'ଉପରେ', per: 'ପ୍ରତି', deg: 'ଡିଗ୍ରୀ', gives: 'ଦିଏ', approx: 'ପ୍ରାୟ', ne: 'ସମାନ ନୁହେଁ', le: 'ରୁ କମ୍ କିମ୍ବା ସମାନ', ge: 'ରୁ ଅଧିକ କିମ୍ବା ସମାନ' },
  ml: { plus: 'കൂട്ടൽ', minus: 'കുറയ്ക്കൽ', times: 'ഗുണനം', div: 'ഹരണം', eq: 'തുല്യം', sq: 'വർഗ്ഗം', cube: 'ഘനം', pow: 'ഘാതം', root: 'വർഗ്ഗമൂലം', over: 'മേൽ', per: 'ഓരോ', deg: 'ഡിഗ്രി', gives: 'തരുന്നു', approx: 'ഏകദേശം', ne: 'തുല്യമല്ല', le: 'ൽ കുറവോ തുല്യമോ', ge: 'ൽ കൂടുതലോ തുല്യമോ' },
  zh: { plus: '加', minus: '减', times: '乘以', div: '除以', eq: '等于', sq: '的平方', cube: '的立方', pow: '的幂', root: '平方根', over: '分之', per: '每', deg: '度', gives: '得', approx: '约等于', ne: '不等于', le: '小于或等于', ge: '大于或等于' },
  es: { plus: 'más', minus: 'menos', times: 'por', div: 'dividido entre', eq: 'es igual a', sq: 'al cuadrado', cube: 'al cubo', pow: 'elevado a', root: 'raíz cuadrada de', over: 'sobre', per: 'por', deg: 'grados', gives: 'da', approx: 'aproximadamente', ne: 'distinto de', le: 'menor o igual que', ge: 'mayor o igual que' },
  fr: { plus: 'plus', minus: 'moins', times: 'fois', div: 'divisé par', eq: 'égale', sq: 'au carré', cube: 'au cube', pow: 'puissance', root: 'racine carrée de', over: 'sur', per: 'par', deg: 'degrés', gives: 'donne', approx: 'environ', ne: 'différent de', le: 'inférieur ou égal à', ge: 'supérieur ou égal à' },
  ar: { plus: 'زائد', minus: 'ناقص', times: 'ضرب', div: 'مقسوم على', eq: 'يساوي', sq: 'تربيع', cube: 'تكعيب', pow: 'أس', root: 'الجذر التربيعي ل', over: 'على', per: 'لكل', deg: 'درجة', gives: 'يعطي', approx: 'تقريباً', ne: 'لا يساوي', le: 'أصغر من أو يساوي', ge: 'أكبر من أو يساوي' },
  pt: { plus: 'mais', minus: 'menos', times: 'vezes', div: 'dividido por', eq: 'igual a', sq: 'ao quadrado', cube: 'ao cubo', pow: 'elevado a', root: 'raiz quadrada de', over: 'sobre', per: 'por', deg: 'graus', gives: 'dá', approx: 'aproximadamente', ne: 'diferente de', le: 'menor ou igual a', ge: 'maior ou igual a' },
  ru: { plus: 'плюс', minus: 'минус', times: 'умножить на', div: 'разделить на', eq: 'равно', sq: 'в квадрате', cube: 'в кубе', pow: 'в степени', root: 'квадратный корень из', over: 'на', per: 'в', deg: 'градусов', gives: 'даёт', approx: 'примерно', ne: 'не равно', le: 'меньше или равно', ge: 'больше или равно' },
  id: { plus: 'tambah', minus: 'kurang', times: 'kali', div: 'dibagi', eq: 'sama dengan', sq: 'kuadrat', cube: 'kubik', pow: 'pangkat', root: 'akar kuadrat dari', over: 'per', per: 'per', deg: 'derajat', gives: 'menghasilkan', approx: 'kira-kira', ne: 'tidak sama dengan', le: 'kurang dari atau sama dengan', ge: 'lebih dari atau sama dengan' },
  de: { plus: 'plus', minus: 'minus', times: 'mal', div: 'geteilt durch', eq: 'gleich', sq: 'zum Quadrat', cube: 'hoch drei', pow: 'hoch', root: 'Quadratwurzel aus', over: 'durch', per: 'pro', deg: 'Grad', gives: 'ergibt', approx: 'ungefähr', ne: 'ungleich', le: 'kleiner oder gleich', ge: 'größer oder gleich' },
  ja: { plus: 'プラス', minus: 'マイナス', times: 'かける', div: 'わる', eq: 'イコール', sq: 'の二乗', cube: 'の三乗', pow: 'のべき乗', root: 'ルート', over: '分の', per: 'あたり', deg: '度', gives: 'となる', approx: 'およそ', ne: 'ノットイコール', le: '以下', ge: '以上' },
};
const ELEMENTS = new Set('H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr'.split(' '));
const DIGITS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'];
const UNITS = [[/(\d)\s?m\/s(?:\^2|2|²)\b/g, '$1 metres per second squared'], [/(\d)\s?m\/s\b/g, '$1 metres per second'], [/(\d)\s?km\/h\b/g, '$1 kilometres per hour'], [/(\d)\s?kg\b/g, '$1 kilograms'],
  [/(\d)\s?kJ\b/g, '$1 kilojoules'], [/(\d)\s?kW\b/g, '$1 kilowatts'], [/(\d)\s?N\b/g, '$1 newtons'], [/(\d)\s?J\b/g, '$1 joules'], [/(\d)\s?W\b/g, '$1 watts'], [/(\d)\s?Pa\b/g, '$1 pascals'],
  [/(\d)\s?Hz\b/g, '$1 hertz'], [/(\d)\s?mol\b/g, '$1 moles'], [/(\d)\s?(?:°|º)\s?C\b/g, '$1 degrees Celsius'], [/(\d)\s?(?:Ω|ohm)\b/g, '$1 ohms'], [/(\d)\s?cm\b/g, '$1 centimetres'], [/(\d)\s?mm\b/g, '$1 millimetres'],
  [/(\d)\s?km\b/g, '$1 kilometres'], [/(\d)\s?m\b/g, '$1 metres'], [/(\d)\s?s\b/g, '$1 seconds']];

function speakFormula(token) { // "H2SO4" -> "H two S O four"; returns null when it is not a chemical formula
  const parts = []; let i = 0, symbols = 0, hasDigit = false;
  while (i < token.length) {
    const m = /^([A-Z][a-z]?)(\d*)/.exec(token.slice(i)) || /^(\()|^(\))(\d*)/.exec(token.slice(i));
    if (!m) return null;
    if (m[0][0] === '(' || m[0][0] === ')') { i += m[0].length; if (m[0].length > 1) { hasDigit = true; parts.push(`close, ${[...m[0].slice(1)].map((d) => DIGITS[+d]).join(' ')}`); } else parts.push(m[0] === '(' ? 'open' : 'close'); continue; }
    let sym = m[1]; if (!ELEMENTS.has(sym)) { if (sym.length === 2 && ELEMENTS.has(sym[0])) { m[0] = sym[0] + m[2]; sym = sym[0]; } else return null; }
    symbols++; if (m[2]) hasDigit = true;
    parts.push(sym.split('').join(' ') + (m[2] ? ' ' + [...m[2]].map((d) => DIGITS[+d]).join(' ') : ''));
    i += m[0].length || sym.length + (m[2] || '').length;
  }
  return symbols >= 2 || (symbols === 1 && hasDigit) ? parts.join(' ') : null;
}

function texToWords(tex, lang) {
  const o = OPS[lang] || OPS.en; const words = lang !== 'xx';
  let t = tex; const rep = (re, to) => { t = t.replace(re, to); };
  for (let i = 0; i < 3; i++) rep(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, (_, a, b) => ` ${a} ${o.over} ${b} `);
  rep(/\\sqrt\s*\{([^{}]*)\}/g, ` ${o.root} $1 `); rep(/\^\s*\{?2\}?/g, ` ${o.sq} `); rep(/\^\s*\{?3\}?/g, ` ${o.cube} `);
  rep(/\^\s*\{([^{}]*)\}/g, ` ${o.pow} $1 `); rep(/\^\s*(\w)/g, ` ${o.pow} $1 `); rep(/_\s*\{([^{}]*)\}/g, ' $1 '); rep(/_\s*(\w)/g, ' $1 ');
  rep(/\\(times|cdot)/g, ` ${o.times} `); rep(/\\div/g, ` ${o.div} `); rep(/\\(rightarrow|to|Rightarrow)/g, ` ${o.gives} `); rep(/\\approx/g, ` ${o.approx} `);
  rep(/\\(neq|ne)\b/g, ` ${o.ne} `); rep(/\\(leq|le)\b/g, ` ${o.le} `); rep(/\\(geq|ge)\b/g, ` ${o.ge} `); rep(/\\degree|\^\s*\\circ/g, ` ${o.deg} `);
  rep(/\\(text|mathrm|mathbf|operatorname)\s*\{([^{}]*)\}/g, ' $2 '); rep(/\\([a-zA-Z]+)/g, (_, n) => ` ${GREEK[n] || n} `);
  if (words) { rep(/=/g, ` ${o.eq} `); rep(/\+/g, ` ${o.plus} `); rep(/(\w|\)|\s)-(\s?\w)/g, `$1 ${o.minus} $2`); rep(/\//g, ` ${o.per} `); }
  rep(/[{}\\]/g, ' ');
  return t.replace(/\s+/g, ' ').trim();
}

/** Markdown / LaTeX -> plain text for a speech engine. `lang` is the lesson language code (en, hi, te...). */
export function toSpeakable(src, lang = 'en') {
  let t = String(src || '');
  const maths = []; // protect spoken maths from the unit / formula rewriting below
  const keep = (words) => { maths.push(` ${words} `); return `\u0000${maths.length - 1}\u0000`; };
  t = t.replace(/```[\s\S]*?```/g, ' (see the code on the screen) ');
  t = t.replace(/\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]/g, (_, a, b) => keep(texToWords(a || b, lang)));
  t = t.replace(/\\\(([\s\S]+?)\\\)|\$([^\n$]+?)\$/g, (_, a, b) => keep(texToWords(a || b, lang)));
  t = t.replace(/!\[[^\]]*\]\([^)]*\)/g, ' ').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/\[(\d{1,2})\]/g, ' ');
  t = t.replace(/^\s{0,3}#{1,6}\s*/gm, '').replace(/^\s*[-*+]\s+/gm, '').replace(/^\s*\d+[.)]\s+/gm, '');
  t = t.replace(/[*_`~>|]+/g, ' ').replace(/\p{Extended_Pictographic}/gu, ' ');
  if (lang === 'en') {
    for (const [re, to] of UNITS) t = t.replace(re, to);
    t = t.replace(/\b((?:[A-Z][a-z]?|\()[A-Za-z0-9()]*\d[A-Za-z0-9()]*|[A-Z][a-z]?[A-Z][A-Za-z0-9()]*)\b/g, (m) => speakFormula(m) ?? m);
  }
  t = t.replace(/\u0000(\d+)\u0000/g, (_, i) => maths[+i]);
  return t.replace(/\s+/g, ' ').trim();
}
