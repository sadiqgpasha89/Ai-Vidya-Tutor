// Unit tests for the pure front-end logic (run with: node --test tests/js)
import assert from 'node:assert/strict';
import test from 'node:test';

import { compile } from '../../frontend/calc.js';
import { balance, ELEMENTS } from '../../frontend/chem.js';
import { toSpeakable } from '../../frontend/render.js';
import { splitSentences } from '../../frontend/voice.js';
import { t } from '../../frontend/i18n.js';

test('expression evaluator handles precedence, powers, functions and variables', () => {
  const f = compile('a*x^2 + 3*x - 1');
  assert.equal(f({ a: 2, x: 3 }), 26);
  assert.equal(compile('-2^2')({}), -4);
  assert.equal(compile('2^3^2')({}), 512);
  assert.ok(Math.abs(compile('sin(pi/2) + sqrt(16)')({}) - 5) < 1e-12);
  assert.equal(compile('2x')({ x: 4 }), 8); // implicit multiplication
  assert.throws(() => compile('process.exit()'), /Unknown function|Unsupported|Unexpected/);
  assert.throws(() => compile('x; alert(1)'), /Unsupported/);
  assert.throws(() => compile('constructor')({}), /Unknown name/);
});

test('equation balancer finds exact integer coefficients', () => {
  assert.equal(balance('H2 + O2 -> H2O').text, '2H2 + O2 → 2H2O');
  assert.equal(balance('Fe + O2 -> Fe2O3').text, '4Fe + 3O2 → 2Fe2O3');
  assert.equal(balance('C3H8 + O2 -> CO2 + H2O').text, 'C3H8 + 5O2 → 3CO2 + 4H2O');
  assert.equal(balance('Al + H2SO4 -> Al2(SO4)3 + H2').text, '2Al + 3H2SO4 → Al2(SO4)3 + 3H2');
  assert.equal(balance('KMnO4 + HCl -> KCl + MnCl2 + H2O + Cl2').text, '2KMnO4 + 16HCl → 2KCl + 2MnCl2 + 8H2O + 5Cl2');
  assert.equal(balance('CuSO4.5H2O -> CuSO4 + H2O').text, 'CuSO4.5H2O → CuSO4 + 5H2O');
  assert.throws(() => balance('H2 -> O2'), /cannot be balanced|more than one/i);
  assert.throws(() => balance('nonsense'), /Write the equation|Cannot read/);
});

test('periodic table data is complete and consistent', () => {
  assert.equal(ELEMENTS.length, 118);
  ELEMENTS.forEach((e, i) => assert.equal(e.z, i + 1));
  assert.equal(new Set(ELEMENTS.map((e) => e.sym)).size, 118);
  assert.equal(ELEMENTS[25].sym, 'Fe'); assert.equal(ELEMENTS[78].sym, 'Au'); assert.equal(ELEMENTS[91].sym, 'U');
  assert.ok(Math.abs(ELEMENTS[5].mass - 12.011) < 1e-6);
});

test('sentence splitting keeps utterances short and handles Indian full stops', () => {
  assert.deepEqual(splitSentences('Force is a push. It is measured in newtons! Why?'), ['Force is a push.', 'It is measured in newtons!', 'Why?']);
  assert.deepEqual(splitSentences('बल एक धक्का है। यह न्यूटन में मापा जाता है।'), ['बल एक धक्का है।', 'यह न्यूटन में मापा जाता है।']);
  const long = splitSentences(`${'word, '.repeat(80)}end.`);
  assert.ok(long.length > 1 && long.every((s) => s.length <= 225));
  assert.deepEqual(splitSentences('   '), []);
});

test('speakable text: maths, units, chemistry, markdown', () => {
  assert.match(toSpeakable('$v = u + at$', 'en'), /v equals u plus at/);
  assert.match(toSpeakable('$x^2$', 'en'), /x squared/);
  assert.match(toSpeakable('$\\frac{1}{2} m v^2$', 'en'), /1 over 2 m v squared/);
  assert.match(toSpeakable('The speed is 20 m/s and mass 5 kg.', 'en'), /20 metres per second and mass 5 kilograms/);
  assert.match(toSpeakable('Water is H2O and acid is H2SO4.', 'en'), /H two O.*H two S O four/);
  assert.equal(toSpeakable('No water here', 'en'), 'No water here');
  assert.match(toSpeakable('## Heading\n- **bold** item', 'en'), /^Heading bold item$/);
  assert.match(toSpeakable('```py\nprint(1)\n```', 'en'), /see the code on the screen/);
  assert.match(toSpeakable('$a = b$', 'hi'), /a बराबर b/);
  assert.doesNotMatch(toSpeakable('Hello 😀 world', 'en'), /😀/);
});

test('translation helper falls back to English and fills variables', () => {
  assert.equal(t('missing.key', 'Hello {name}', { name: 'Asha' }), 'Hello Asha');
  assert.equal(t('only.key'), 'only.key');
});
