import React, { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import '../styles/landing.css';

const LOGO = '/landing/tenfy-logo-light.png';
const IMG_SERVE = '/landing/serve.jpg';
const IMG_COURT = '/landing/court.jpg';

const MANIFESTO =
  'Consultar dezenas de sites, regulamentos em PDF e mensagens dispersas deixou de ser necessário. ' +
  'O Tenfy consolida todas as informações em um só lugar e o notifica antes do encerramento de cada inscrição.';
const LIME_WORDS = new Set(['consolida', 'informações', 'notifica', 'antes', 'encerramento']);

const Arrow: React.FC<{ size?: number }> = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const LandingPage: React.FC = () => {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const docEl = document.documentElement;

    // Fundo escuro no documento + scroll suave (restaurados ao sair da landing)
    const prevBodyBg = document.body.style.background;
    const prevScroll = docEl.style.scrollBehavior;
    document.body.style.background = '#06090F';
    docEl.style.scrollBehavior = 'smooth';

    const progress = root.querySelector<HTMLElement>('.progress');
    const nav = root.querySelector<HTMLElement>('header.nav');

    // ── scroll progress + nav solid ──
    const onScroll = () => {
      const max = docEl.scrollHeight - docEl.clientHeight;
      if (progress) progress.style.width = (max > 0 ? (window.scrollY / max) * 100 : 0) + '%';
      if (nav) nav.classList.toggle('solid', window.scrollY > 60);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });

    // ── generic reveals ──
    const rvIO = new IntersectionObserver(
      (es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); rvIO.unobserve(e.target); } }),
      { threshold: 0.18, rootMargin: '0px 0px -8% 0px' },
    );
    root.querySelectorAll('.rv, .reveal-h').forEach((el) => rvIO.observe(el));

    // ── media reveals (mask wipe + image scale) ──
    const mediaIO = new IntersectionObserver(
      (es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); mediaIO.unobserve(e.target); } }),
      { threshold: 0.25 },
    );
    root.querySelectorAll('[data-reveal-media]').forEach((el) => mediaIO.observe(el));

    // ── parallax (rAF-batched) ──
    const parallaxEls = [...root.querySelectorAll<HTMLElement>('[data-parallax]')].map((el) => ({
      el,
      speed: parseFloat(el.dataset.parallax || '0'),
    }));
    let ticking = false;
    const parallax = () => {
      const vh = window.innerHeight;
      parallaxEls.forEach(({ el, speed }) => {
        const parent = el.parentElement;
        if (!parent) return;
        const rect = parent.getBoundingClientRect();
        if (rect.bottom < -200 || rect.top > vh + 200) return;
        const offset = (rect.top + rect.height / 2 - vh / 2) * -speed;
        el.style.transform = `translate3d(0, ${offset.toFixed(1)}px, 0)`;
      });
      ticking = false;
    };
    const onParallaxScroll = () => { if (!ticking) { requestAnimationFrame(parallax); ticking = true; } };
    window.addEventListener('scroll', onParallaxScroll, { passive: true });
    parallax();

    // ── manifesto: word-by-word highlight tied to scroll ──
    const mtext = root.querySelector<HTMLElement>('.mtext');
    const tall = root.querySelector<HTMLElement>('.manifesto .tall');
    const mws = mtext ? [...mtext.querySelectorAll<HTMLElement>('.mw')] : [];
    const updateManifesto = () => {
      if (!tall || !mws.length) return;
      const rect = tall.getBoundingClientRect();
      const total = rect.height - window.innerHeight;
      let prog = total > 0 ? -rect.top / total : 0;
      prog = Math.max(0, Math.min(1, prog));
      const eased = Math.max(0, Math.min(1, (prog - 0.05) / 0.8));
      const lit = Math.round(eased * mws.length);
      mws.forEach((w, i) => w.classList.toggle('on', i < lit));
    };
    updateManifesto();
    const onManifestoScroll = () => requestAnimationFrame(updateManifesto);
    window.addEventListener('scroll', onManifestoScroll, { passive: true });
    window.addEventListener('resize', updateManifesto);

    // ── magnetic CTA buttons ──
    const magnetic = [...root.querySelectorAll<HTMLElement>('.btn-lime')];
    const onMove = (btn: HTMLElement) => (e: MouseEvent) => {
      const r = btn.getBoundingClientRect();
      const x = (e.clientX - r.left - r.width / 2) * 0.18;
      const y = (e.clientY - r.top - r.height / 2) * 0.3;
      btn.style.transform = `translate(${x}px, ${y - 2}px)`;
    };
    const onLeave = (btn: HTMLElement) => () => { btn.style.transform = ''; };
    const handlers = magnetic.map((btn) => {
      const move = onMove(btn);
      const leave = onLeave(btn);
      btn.addEventListener('mousemove', move);
      btn.addEventListener('mouseleave', leave);
      return { btn, move, leave };
    });

    // ── duplicate marquee content for a seamless loop on wide screens ──
    const track = root.querySelector<HTMLElement>('.marquee-track');
    if (track && track.scrollWidth < window.innerWidth * 2) {
      track.innerHTML += track.innerHTML;
    }

    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('scroll', onParallaxScroll);
      window.removeEventListener('scroll', onManifestoScroll);
      window.removeEventListener('resize', updateManifesto);
      rvIO.disconnect();
      mediaIO.disconnect();
      handlers.forEach(({ btn, move, leave }) => {
        btn.removeEventListener('mousemove', move);
        btn.removeEventListener('mouseleave', leave);
      });
      document.body.style.background = prevBodyBg;
      docEl.style.scrollBehavior = prevScroll;
    };
  }, []);

  return (
    <div className="tenfy-landing" id="top" ref={rootRef}>
      <div className="progress" />

      {/* NAV */}
      <header className="nav">
        <div className="wrap nav-in">
          <a href="#top" className="nav-logo"><img src={LOGO} alt="Tenfy" /></a>
          <nav className="nav-links">
            <a href="#recursos">Recursos</a>
            <a href="#como">Como funciona</a>
            <a href="#app">App</a>
          </nav>
          <div className="nav-cta">
            <Link to="/login" className="login">Entrar</Link>
            <Link to="/register" className="signup">Criar conta grátis</Link>
          </div>
        </div>
      </header>

      {/* HERO */}
      <section className="hero">
        <div className="hero-media" data-parallax="0.25">
          <img src={IMG_SERVE} alt="Tenista sacando sob a luz" />
        </div>
        <div className="hero-in wrap">
          <span className="eyebrow">Tênis · Brasil · Temporada 2026</span>
          <h1>
            <span className="ln"><i>Todos os</i></span>
            <span className="ln"><i>torneios.</i></span>
            <span className="ln"><i className="hl">Um só app.</i></span>
          </h1>
          <div className="hero-row">
            <p>O Tenfy reúne o calendário do tênis brasileiro, identifica as categorias em que você pode competir e o notifica antes do encerramento de cada inscrição.</p>
            <div className="hero-actions">
              <Link to="/register" className="btn btn-lime">
                <span className="t">Criar conta grátis</span>
                <span className="arrow"><Arrow /></span>
              </Link>
              <a href="#como" className="btn btn-ghost">Como funciona</a>
            </div>
          </div>
        </div>
        <div className="scrollcue">Role<span className="bar" /></div>
      </section>

      {/* MARQUEE */}
      <div className="marquee">
        <div className="marquee-track">
          <span>Calendário</span><span className="fill">Elegibilidade</span><span>Alertas</span><span className="fill">Rankings</span><span>Inscritos</span><span className="fill">Categorias</span>
          <span>Calendário</span><span className="fill">Elegibilidade</span><span>Alertas</span><span className="fill">Rankings</span><span>Inscritos</span><span className="fill">Categorias</span>
        </div>
      </div>

      {/* MANIFESTO */}
      <section className="manifesto">
        <div className="tall">
          <div className="sticky">
            <div className="wrap">
              <span className="eyebrow" style={{ marginBottom: 34 }}>Por que o Tenfy</span>
              <p className="mtext">
                {MANIFESTO.split(/\s+/).map((w, i) => {
                  const clean = w.replace(/[.,—]/g, '').toLowerCase();
                  const lime = LIME_WORDS.has(clean);
                  return (
                    <span key={i} className={`mw${lime ? ' lime' : ''}`}>{w} </span>
                  );
                })}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* FEATURE 1 */}
      <section className="sec" id="recursos">
        <div className="wrap split">
          <div className="split-media" data-reveal-media>
            <div className="mask" />
            <img src={IMG_COURT} alt="Quadra de tênis" />
          </div>
          <div className="split-copy">
            <span className="eyebrow">Calendário</span>
            <h2 className="bigh reveal-h"><span className="ln-i">Todo o calendário,</span><br /><span className="ln-i"><span className="hl">sincronizado.</span></span></h2>
            <p className="lead rv">Torneios, categorias e datas de todo o país, permanentemente atualizados. O calendário se mantém por conta própria; a você cabe apenas competir.</p>
            <Link to="/register" className="more rv d1">Explorar o calendário <Arrow size={18} /></Link>
          </div>
        </div>
      </section>

      {/* FEATURE 2 (flip) */}
      <section className="sec" style={{ paddingTop: 0 }}>
        <div className="wrap split flip">
          <div className="split-media" data-reveal-media>
            <div className="mask" />
            <img src={IMG_SERVE} alt="Atleta em treino" />
          </div>
          <div className="split-copy">
            <span className="eyebrow">Elegibilidade</span>
            <h2 className="bigh reveal-h"><span className="ln-i">Saiba onde</span><br /><span className="ln-i">você <span className="hl">pode competir.</span></span></h2>
            <p className="lead rv">Informe seu perfil e o Tenfy o compara com os critérios de cada categoria, exibindo somente as competições adequadas ao seu nível.</p>
            <Link to="/register" className="more rv d1">Conhecer minhas categorias <Arrow size={18} /></Link>
          </div>
        </div>
      </section>

      {/* HOW */}
      <section className="sec" id="como" style={{ paddingTop: 0 }}>
        <div className="wrap">
          <div className="how-head">
            <div>
              <span className="eyebrow sec-eyebrow">Como funciona</span>
              <h2 className="bigh reveal-h"><span className="ln-i">Três passos</span><br /><span className="ln-i">e <span className="hl">pronto.</span></span></h2>
            </div>
            <p className="rv" style={{ maxWidth: 360, color: 'var(--muted)', fontWeight: 300, lineHeight: 1.6, fontSize: 16 }}>Do cadastro ao primeiro alerta em poucos instantes, sem planilhas e sem a necessidade de consultar editais.</p>
          </div>
          <div className="steps">
            <div className="step rv">
              <div className="n">/ 01</div>
              <div className="ic"><svg width="24" height="24" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="2" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg></div>
              <h3>Crie seu perfil</h3>
              <p>Informe sexo, idade e nível de jogo. São os dados necessários para personalizar sua experiência.</p>
              <div className="line" />
            </div>
            <div className="step rv d1">
              <div className="n">/ 02</div>
              <div className="ic"><svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" /></svg></div>
              <h3>Veja onde pode competir</h3>
              <p>O calendário seleciona automaticamente os torneios e categorias compatíveis com o seu perfil.</p>
              <div className="line" />
            </div>
            <div className="step rv d2">
              <div className="n">/ 03</div>
              <div className="ic"><svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" /><path d="M13.7 21a2 2 0 01-3.4 0" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg></div>
              <h3>Receba os alertas</h3>
              <p>Salve as competições de interesse e seja notificado antes de cada prazo de inscrição.</p>
              <div className="line" />
            </div>
          </div>
        </div>
      </section>

      {/* FULL BLEED FEATURE */}
      <section className="bleed">
        <div className="bleed-media" data-parallax="0.18">
          <img src={IMG_COURT} alt="Quadra à noite" />
        </div>
        <div className="bleed-in wrap">
          <span className="eyebrow">Alertas</span>
          <h2 className="bigh reveal-h" style={{ marginTop: 22 }}><span className="ln-i">Não perca</span><br /><span className="ln-i">nenhum <span className="hl">prazo.</span></span></h2>
          <p className="rv" style={{ marginTop: 26, maxWidth: 480, color: 'var(--text)', fontWeight: 300, fontSize: 18, lineHeight: 1.65 }}>Notificações por push e e-mail antes do encerramento de cada inscrição. Alterações de data, categoria ou lista de inscritos são comunicadas imediatamente.</p>
        </div>
      </section>

      {/* CTA */}
      <section className="cta" id="app">
        <div className="cta-media" data-parallax="0.2">
          <img src={IMG_SERVE} alt="Tenista em quadra" />
        </div>
        <div className="cta-in wrap">
          <h2 className="reveal-h"><span className="ln-i">A quadra</span><br /><span className="ln-i"><span className="hl">te espera.</span></span></h2>
          <div className="rv d1">
            <Link to="/register" className="btn btn-lime">
              <span className="t">Criar conta grátis</span>
              <span className="arrow"><Arrow /></span>
            </Link>
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer>
        <div className="wrap">
          <div className="foot-top">
            <div className="foot-brand">
              <img src={LOGO} alt="Tenfy" />
              <p>Seu calendário inteligente de torneios de tênis. Nós organizamos; você compete.</p>
            </div>
            <div className="foot-cols">
              <div className="foot-col">
                <h4>Produto</h4>
                <a href="#recursos">Recursos</a>
                <a href="#como">Como funciona</a>
                <Link to="/register">Criar conta</Link>
              </div>
              <div className="foot-col">
                <h4>App</h4>
                <Link to="/register">iOS</Link>
                <Link to="/register">Android</Link>
                <Link to="/login">Web</Link>
              </div>
              <div className="foot-col">
                <h4>Tenfy</h4>
                <a href="#app">Contato</a>
                <Link to="/politica-privacidade">Privacidade</Link>
                <Link to="/politica-privacidade">Termos</Link>
              </div>
            </div>
          </div>
          <div className="foot-bot">
            <p>© 2026 Tenfy. Todos os direitos reservados.</p>
            <div className="socials">
              <a href="#top" aria-label="Instagram"><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="18" rx="5" stroke="currentColor" strokeWidth="2" /><circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="2" /><circle cx="17.5" cy="6.5" r="1.2" fill="currentColor" /></svg></a>
              <a href="#top" aria-label="TikTok"><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M15 3c.5 3 2.5 4.5 5 4.7v3.2c-1.8.1-3.5-.5-5-1.5V16a6 6 0 11-6-6c.4 0 .7 0 1 .1v3.3A2.7 2.7 0 1015 16V3z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" /></svg></a>
              <a href="#top" aria-label="YouTube"><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><rect x="2" y="5" width="20" height="14" rx="4" stroke="currentColor" strokeWidth="2" /><path d="M10 9l5 3-5 3V9z" fill="currentColor" /></svg></a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};
