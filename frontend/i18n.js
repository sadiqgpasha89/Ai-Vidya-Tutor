// Interface translation. t('key', 'English default', {vars}) - English lives in the code; other languages are JSON overrides in /locales.
let dict = {};
let current = 'en';
export const UI_LANGS = ['en', 'hi', 'bn', 'mr', 'te', 'ta', 'gu', 'ur', 'kn', 'or', 'ml', 'zh', 'es', 'fr', 'ar', 'pt', 'ru', 'id', 'de', 'ja'];
const RTL = new Set(['ar', 'ur']);

export async function setUiLang(code) {
  current = UI_LANGS.includes(code) ? code : 'en';
  dict = {};
  if (current !== 'en') {
    try { dict = await (await fetch(`/locales/${current}.json`, { cache: 'no-cache' })).json(); } catch { dict = {}; }
  }
  document.documentElement.lang = current; document.documentElement.dir = RTL.has(current) ? 'rtl' : 'ltr';
}
export const uiLang = () => current;

export function t(key, fallback, vars) {
  let s = dict[key] ?? fallback ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, v);
  return s;
}
