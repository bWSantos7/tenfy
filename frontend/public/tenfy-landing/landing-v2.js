/* ───────── Tenfy v2 — cinematic interactions ───────── */

const nav = document.getElementById('nav');
const progress = document.getElementById('progress');
const docEl = document.documentElement;

/* scroll progress + nav state */
function onScroll() {
  const max = docEl.scrollHeight - docEl.clientHeight;
  progress.style.width = (window.scrollY / max * 100) + '%';
  nav.classList.toggle('solid', window.scrollY > 60);
}
onScroll();
window.addEventListener('scroll', onScroll, { passive: true });

/* ── generic reveals ── */
const rvIO = new IntersectionObserver((es) => {
  es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); rvIO.unobserve(e.target); } });
}, { threshold: 0.18, rootMargin: '0px 0px -8% 0px' });
document.querySelectorAll('.rv, .reveal-h').forEach(el => rvIO.observe(el));

/* ── media reveals (mask wipe + image scale) ── */
const mediaIO = new IntersectionObserver((es) => {
  es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); mediaIO.unobserve(e.target); } });
}, { threshold: 0.25 });
document.querySelectorAll('[data-reveal-media]').forEach(el => mediaIO.observe(el));

/* ── parallax (rAF-batched) ── */
const parallaxEls = [...document.querySelectorAll('[data-parallax]')].map(el => ({
  el, speed: parseFloat(el.dataset.parallax)
}));
let ticking = false;
function parallax() {
  const vh = window.innerHeight;
  parallaxEls.forEach(({ el, speed }) => {
    const rect = el.parentElement.getBoundingClientRect();
    if (rect.bottom < -200 || rect.top > vh + 200) return;
    const offset = (rect.top + rect.height / 2 - vh / 2) * -speed;
    el.style.transform = `translate3d(0, ${offset.toFixed(1)}px, 0)`;
  });
  ticking = false;
}
window.addEventListener('scroll', () => {
  if (!ticking) { requestAnimationFrame(parallax); ticking = true; }
}, { passive: true });
parallax();

/* ── manifesto: word-by-word highlight tied to scroll ── */
(() => {
  const p = document.getElementById('mtext');
  if (!p) return;
  // lime keywords
  const limeWords = new Set(['consolida', 'informações', 'notifica', 'antes', 'encerramento']);
  const words = p.textContent.trim().split(/\s+/);
  p.innerHTML = words.map(w => {
    const clean = w.replace(/[.,—]/g, '').toLowerCase();
    const lime = limeWords.has(clean);
    return `<span class="mw${lime ? ' lime' : ''}">${w}</span>`;
  }).join(' ');
  const mws = [...p.querySelectorAll('.mw')];
  const section = p.closest('.manifesto');
  const tall = section.querySelector('.tall');

  function update() {
    const rect = tall.getBoundingClientRect();
    const total = rect.height - window.innerHeight;
    let prog = (-rect.top) / total;
    prog = Math.max(0, Math.min(1, prog));
    // map 0.05..0.85 of scroll to 0..1 of words
    const eased = Math.max(0, Math.min(1, (prog - 0.05) / 0.8));
    const lit = Math.round(eased * mws.length);
    mws.forEach((w, i) => w.classList.toggle('on', i < lit));
  }
  update();
  window.addEventListener('scroll', () => requestAnimationFrame(update), { passive: true });
  window.addEventListener('resize', update);
})();

/* ── magnetic CTA buttons ── */
document.querySelectorAll('.btn-lime').forEach(btn => {
  btn.addEventListener('mousemove', (e) => {
    const r = btn.getBoundingClientRect();
    const x = (e.clientX - r.left - r.width / 2) * 0.18;
    const y = (e.clientY - r.top - r.height / 2) * 0.3;
    btn.style.transform = `translate(${x}px, ${y - 2}px)`;
  });
  btn.addEventListener('mouseleave', () => { btn.style.transform = ''; });
});

/* ── duplicate marquee content to guarantee seamless loop width ── */
(() => {
  const track = document.getElementById('mtrack');
  if (track && track.scrollWidth < window.innerWidth * 2) {
    track.innerHTML += track.innerHTML;
  }
})();
