// Daily 5: five quick questions a day, picked from what you are about to forget, got wrong, or are studying now.
import { api, get } from './api.js';
import { t } from './i18n.js';
import { md, esc } from './render.js';
import { $, $$, ring } from './ui.js';
import { refreshProgress } from './state.js';
import { rewardToast } from './lesson.js';

const LETTERS = ['A', 'B', 'C', 'D'];
const dots = (week) => `<span class="week-dots" role="img" aria-label="${t('daily.week', 'The last seven days')}">${week.map((d) => `<i class="${d.done ? 'done' : ''}" title="${esc(d.day)}"></i>`).join('')}</span>`;

/** The card on the home page. Reads a small status only: nothing is generated until the student opens it. */
export async function homeCard(el) {
  let s;
  try { s = await get('/api/daily'); } catch { return; }
  const text = {
    locked: [t('daily.locked.title', 'Daily 5'), t('daily.locked', 'Study any topic and your Daily 5 will be ready.')],
    new: [t('daily.new.title', 'Your Daily 5 is ready'), t('daily.new', 'Five quick questions from what you are learning. About 5 minutes.')],
    started: [t('daily.started.title', 'Finish your Daily 5'), t('daily.started', '{n} of 5 done. Keep going!', { n: s.answered })],
    done: [t('daily.done.title', 'Daily 5 done ✓'), t('daily.done', 'You scored {n} out of 5 today. Come back tomorrow.', { n: s.score })],
  }[s.state];
  const body = `<div class="daily-icon" aria-hidden="true">☀️</div><div style="flex:1"><b>${text[0]}</b><div class="muted small">${text[1]}</div></div>${dots(s.week)}
    ${s.state === 'locked' ? '' : `<span class="btn ${s.state === 'done' ? '' : 'primary'} sm">${s.state === 'done' ? t('daily.review', 'See answers') : s.state === 'started' ? t('common.continue', 'Continue') : t('daily.start', 'Start')}</span>`}`;
  el.innerHTML = s.state === 'locked' ? `<div class="card pad daily-card row">${body}</div>` : `<a class="card pad daily-card row" href="#/daily">${body}</a>`;
}

export async function renderDaily(view) {
  const crumbs = `<div class="crumbs"><a href="#/">${t('nav.home', 'Home')}</a> › ☀️ ${t('daily.heading', 'Daily 5')}</div>`;
  view.innerHTML = `${crumbs}<h1>☀️ ${t('daily.heading', 'Daily 5')}</h1><p class="muted">${t('daily.preparing', 'AIVidya is choosing five questions for you from what you have been learning…')}</p><div class="skeleton"></div><div class="skeleton" style="width:70%"></div>`;
  let set;
  try { set = await api('/api/daily/open', {}); } catch (e) {
    view.innerHTML = `${crumbs}<h1>☀️ ${t('daily.heading', 'Daily 5')}</h1><div class="banner" role="alert">${esc(e.message)}</div><p><a class="btn" href="#/">${t('nav.home', 'Home')}</a></p>`;
    return;
  }
  const questions = set.questions;
  let i = Math.max(0, questions.findIndex((q) => !q.answered));
  if (set.done) return result(view, crumbs, set, set.summary, null);

  const show = () => {
    const q = questions[i];
    view.innerHTML = `${crumbs}<h1>☀️ ${t('daily.heading', 'Daily 5')}</h1>
      <section class="card pad"><div class="row"><b>${t('quiz.q', 'Question')} ${i + 1} ${t('common.of', 'of')} ${questions.length}</b><span class="spacer"></span><span class="chip">${esc(q.topic)}</span>${q.source === 'mistake' ? `<span class="chip warn">${t('daily.again', 'You missed this before')}</span>` : ''}</div>
        <div class="progress-dots">${questions.map((x, k) => `<i class="${x.answered ? 'done' : ''}"></i>`).join('')}</div>
        <div class="prose qtext">${md(q.question)}</div>
        <div id="opts" role="group" aria-label="${t('quiz.options', 'Answer options')}">${q.options.map((o, k) => `<button class="q-opt" data-k="${k}"><b>${LETTERS[k]}</b><span class="prose">${md(o)}</span></button>`).join('')}</div>
        <div id="fb" aria-live="polite"></div></section>`;
    $$('.q-opt', view).forEach((b) => (b.onclick = () => pick(+b.dataset.k)));
    $('.q-opt', view).focus();
  };
  const pick = async (k) => {
    const q = questions[i];
    $$('.q-opt', view).forEach((b) => (b.disabled = true));
    let r;
    try { r = await api('/api/daily/answer', { question_id: q.id, choice: k }); } catch (e) { $('#fb', view).innerHTML = `<p class="error">${esc(e.message)}</p>`; $$('.q-opt', view).forEach((b) => (b.disabled = false)); return; }
    q.answered = r.answered;
    $$('.q-opt', view).forEach((b, idx) => { if (idx === r.answered.answer_index) b.classList.add('right'); else if (idx === k) b.classList.add('wrong'); });
    const last = r.done;
    $('#fb', view).innerHTML = `<div class="explain"><b>${r.answered.correct ? `✅ ${t('quiz.right', 'Correct!')}` : `❌ ${t('quiz.wrong', 'Not quite.')}`}</b>${r.answered.explanation ? `<div class="prose">${md(r.answered.explanation)}</div>` : ''}</div>
      <div class="row" style="margin-top:12px"><span class="spacer"></span><button class="btn primary" id="next">${last ? t('daily.finish', 'See my result') : t('quiz.next', 'Next')}</button></div>`;
    $('#next', view).onclick = () => { if (last) { refreshProgress(); result(view, crumbs, { questions }, r.summary, r.reward); } else { i = questions.findIndex((x) => !x.answered); show(); } };
    $('#next', view).focus();
  };
  show();
}

function result(view, crumbs, set, summary, reward) {
  const pct = Math.round((100 * summary.score) / summary.total);
  const msg = summary.score === summary.total ? t('daily.perfect', 'Perfect! Every answer right.') : pct >= 60 ? t('daily.good', 'Good work. A little more practice will make it solid.') : t('daily.low', 'A few to revisit. They are now in your Mistakes notebook, and will come back to help you.');
  view.innerHTML = `${crumbs}<h1>☀️ ${t('daily.heading', 'Daily 5')}</h1>
    <section class="card pad"><div class="row" style="gap:20px">${ring(pct, `${summary.score}/${summary.total}`)}<div><b>${msg}</b><p class="muted">🔥 ${t('daily.streak', '{n}-day streak', { n: summary.streak })}${reward?.points ? ` · +${reward.points} XP` : ''}</p></div></div>
      <h3>${t('daily.bytopic', 'By topic')}</h3><ul class="plain">${summary.topics.map((x) => `<li class="row"><a href="#/learn/${esc(x.subtopic_id)}">${esc(x.title)}</a><span class="spacer"></span><span class="chip ${x.correct === x.total ? 'ok' : ''}">${x.correct}/${x.total}</span></li>`).join('')}</ul>
      <details><summary>${t('daily.answers', 'My answers')}</summary>${set.questions.filter((q) => q.answered).map((q, n) => `<div class="explain" style="margin-top:8px"><b>${n + 1}. ${q.answered.correct ? '✅' : '❌'}</b><div class="prose">${md(q.question)}</div>
        <p class="small">${t('daily.right', 'Right answer')}: <b>${LETTERS[q.answered.answer_index]}</b> — ${md(q.options[q.answered.answer_index]).replace(/<\/?p>/g, '')}</p>${q.answered.explanation ? `<div class="prose small">${md(q.answered.explanation)}</div>` : ''}</div>`).join('')}</details>
      <div class="row" style="margin-top:14px"><a class="btn primary" href="#/">${t('nav.home', 'Home')}</a><a class="btn" href="#/mistakes">🛠️ ${t('nav.mistakes', 'Mistakes')}</a><a class="btn" href="#/coach">✍️ ${t('coach.heading', 'Answer coach')}</a></div></section>`;
  if (reward) rewardToast(reward);
}
