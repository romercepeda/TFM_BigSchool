// Marketing landing page — Changeset C11 §4. Renders at the root URL (/),
// public, no auth required. Eural brand identity, isolated design tokens.

import { BaseComponent } from '../components/common/base-component.js';
import { t } from '../i18n/i18n.js';
import { navigate } from '../router/router.js';
import landingTokens from '../styles/landing-tokens.css?inline';

const ICON_CHART = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19h16"/><path d="M4 19V5"/><path d="M8 15l3-4 3 2 4-6"/></svg>`;
const ICON_FILE = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M6 21h12a1 1 0 0 0 1-1V7l-4-4H7a1 1 0 0 0-1 1v4"/><path d="M9 17v-2"/><path d="M12 17v-4"/><path d="M15 17v-1"/></svg>`;
const ICON_BELL = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M10 19a2 2 0 0 0 4 0"/><path d="M4 17h16v-1a2 2 0 0 1-2-2v-4a6 6 0 0 0-12 0v4a2 2 0 0 1-2 2v1z"/></svg>`;
const ICON_SHIELD = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z"/><rect x="9.5" y="11" width="5" height="4" rx="0.5"/><path d="M12 11V9.5"/></svg>`;
const ICON_MENU = `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"><path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/></svg>`;

export class LandingPage extends BaseComponent {
  private _mobileMenuOpen = false;

  protected render(): string {
    return `
      <style>
        ${landingTokens}

        :host {
          display: block;
          font-family: var(--landing-font-body);
          background: var(--landing-bg);
          color: var(--landing-text-primary);
        }
        button { font-family: inherit; cursor: pointer; }

        .header {
          position: sticky; top: 0; z-index: 10;
          display: flex; align-items: center; justify-content: space-between;
          padding: 14px 32px;
          background: var(--landing-bg);
          border-bottom: 0.5px solid rgba(200, 200, 206, 0.3);
        }
        .brand { display: flex; align-items: center; gap: 10px; }
        .brand img { height: 32px; display: block; }
        .brand span { letter-spacing: 0.14em; font-weight: 600; font-size: 14px; }
        .nav { display: flex; align-items: center; gap: 28px; }
        .nav-links { display: flex; gap: 22px; list-style: none; margin: 0; padding: 0; }
        .nav-links button { background: none; border: none; padding: 0; color: var(--landing-text-secondary); font-size: 14px; }
        .nav-links button:hover { color: var(--landing-text-primary); }
        .cta-group { display: flex; gap: 12px; }

        .btn {
          border-radius: 6px; padding: 9px 18px; font-size: 14px; font-weight: 500;
          border: 1px solid transparent; white-space: nowrap;
        }
        .btn-outline-gold { border-color: var(--landing-gold); color: var(--landing-gold); background: transparent; }
        .btn-outline-gold:hover { background: rgba(201, 169, 97, 0.1); }
        .btn-filled-gold { background: var(--landing-gold); color: var(--landing-bg); }
        .btn-filled-gold:hover { filter: brightness(1.08); }
        .btn-outline-silver { border-color: var(--landing-silver); color: var(--landing-text-primary); background: transparent; }
        .btn-outline-silver:hover { background: rgba(200, 200, 206, 0.08); }

        .hamburger { display: none; background: none; border: none; color: var(--landing-text-primary); }
        .mobile-menu { display: none; }
        .mobile-menu.open {
          display: flex; flex-direction: column; gap: 14px;
          position: absolute; top: 100%; left: 0; right: 0;
          background: var(--landing-bg); padding: 18px 32px;
          border-bottom: 0.5px solid rgba(200, 200, 206, 0.3);
        }
        .mobile-menu button {
          background: none; border: none; text-align: left; padding: 0;
          color: var(--landing-text-secondary); font-size: 14px;
        }

        .hero { position: relative; padding: 96px 32px 64px; text-align: center; overflow: hidden; }
        .hero-frame { position: absolute; left: 50%; transform: translateX(-50%); width: 260px; opacity: 0.5; pointer-events: none; }
        .hero-frame.top { top: 12px; }
        .hero-frame.bottom { bottom: 12px; transform: translateX(-50%) rotate(180deg); }
        .badge {
          display: inline-block; border: 1px solid var(--landing-gold); color: var(--landing-gold);
          font-size: 11px; letter-spacing: 0.2em; text-transform: uppercase;
          padding: 6px 14px; border-radius: 999px; margin-bottom: 28px;
        }
        .hero-title {
          font-family: var(--landing-font-display); font-weight: 500; font-size: 52px;
          margin: 0 0 16px; line-height: 1.1;
        }
        .hero-subtitle { max-width: 520px; margin: 0 auto 32px; color: var(--landing-text-secondary); font-size: 18px; line-height: 1.6; }
        .hero-ctas { display: flex; justify-content: center; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
        .trust { color: var(--landing-text-muted); font-size: 13px; }

        .features { background: var(--landing-bg-alt); padding: 80px 32px; text-align: center; }
        .eyebrow { color: var(--landing-gold); letter-spacing: 0.2em; font-size: 12px; text-transform: uppercase; margin-bottom: 12px; }
        .section-title { font-family: var(--landing-font-display); font-weight: 500; font-size: 32px; margin: 0 0 48px; }
        .feature-grid {
          display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px;
          max-width: 840px; margin: 0 auto; text-align: left;
        }
        .feature-card {
          background: var(--landing-bg); border: 0.5px solid rgba(200, 200, 206, 0.12);
          border-radius: 8px; padding: 28px;
        }
        .feature-icon { color: var(--landing-gold); margin-bottom: 14px; }
        .feature-card h3 { font-weight: 500; color: var(--landing-text-primary); margin: 0 0 8px; font-size: 16px; }
        .feature-card p { color: var(--landing-text-secondary); font-size: 13px; line-height: 1.5; margin: 0; }

        .cta-section { padding: 80px 32px; text-align: center; }
        .cta-section h2 { font-family: var(--landing-font-display); font-weight: 500; font-size: 30px; margin: 0 0 12px; }
        .cta-section p { color: var(--landing-text-secondary); margin: 0 0 28px; }

        .footer { background: var(--landing-bg-deep); padding: 56px 32px 24px; }
        .footer-top {
          display: flex; justify-content: space-between; gap: 48px; flex-wrap: wrap;
          max-width: 1040px; margin: 0 auto 40px;
        }
        .footer-brand .brand-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
        .footer-brand img { height: 24px; display: block; }
        .footer-brand p { color: var(--landing-text-muted); font-size: 13px; max-width: 280px; margin: 0; }
        .footer-columns { display: flex; gap: 64px; }
        .footer-col h4 { color: var(--landing-gold); letter-spacing: 0.2em; font-size: 11px; text-transform: uppercase; margin: 0 0 14px; }
        .footer-col a, .footer-col button {
          display: block; background: none; border: none; padding: 0; text-align: left;
          color: var(--landing-text-secondary); text-decoration: none; font-size: 14px; margin-bottom: 10px;
        }
        .footer-col a:hover, .footer-col button:hover { color: var(--landing-text-primary); }
        .copyright {
          text-align: center; color: var(--landing-text-muted); font-size: 12px;
          border-top: 0.5px solid rgba(200, 200, 206, 0.12); padding-top: 20px;
          max-width: 1040px; margin: 0 auto;
        }

        @media (max-width: 640px) {
          .nav-links, .cta-group { display: none; }
          .hamburger { display: block; }
          .hero-title { font-size: 38px; }
          .feature-grid { grid-template-columns: 1fr; }
          .footer-top { flex-direction: column; }
          .footer-columns { gap: 32px; }
        }
      </style>

      <header class="header">
        <div class="brand">
          <img src="/assets/eural-logo.png" alt="Eural" />
          <span>EURAL</span>
        </div>
        <nav class="nav">
          <ul class="nav-links">
            <li><button id="nav-features">${t('landing.header.nav.features')}</button></li>
            <li><button id="nav-product">${t('landing.header.nav.product')}</button></li>
          </ul>
          <div class="cta-group">
            <button class="btn btn-outline-gold" id="header-login-btn">${t('landing.header.cta.login')}</button>
            <button class="btn btn-filled-gold" id="header-register-btn">${t('landing.header.cta.register')}</button>
          </div>
        </nav>
        <button class="hamburger" id="hamburger-btn" aria-label="${t('landing.header.nav.features')}">${ICON_MENU}</button>
        <div class="mobile-menu${this._mobileMenuOpen ? ' open' : ''}" id="mobile-menu">
          <button id="mobile-nav-features">${t('landing.header.nav.features')}</button>
          <button id="mobile-nav-product">${t('landing.header.nav.product')}</button>
          <button id="mobile-login-btn">${t('landing.header.cta.login')}</button>
          <button id="mobile-register-btn">${t('landing.header.cta.register')}</button>
        </div>
      </header>

      <section class="hero" id="product">
        <svg class="hero-frame top" viewBox="0 0 200 90" aria-hidden="true">
          <polyline points="100,6 190,84 10,84" fill="none" stroke="#c8c8ce" stroke-width="1" />
        </svg>
        <div class="badge">${t('landing.hero.badge')}</div>
        <h1 class="hero-title">${t('landing.hero.title')}</h1>
        <p class="hero-subtitle">${t('landing.hero.subtitle')}</p>
        <div class="hero-ctas">
          <button class="btn btn-filled-gold" id="hero-register-btn">${t('landing.hero.cta.primary')}</button>
          <button class="btn btn-outline-silver" id="hero-login-btn">${t('landing.hero.cta.secondary')}</button>
        </div>
        <p class="trust">${t('landing.hero.trust')}</p>
        <svg class="hero-frame bottom" viewBox="0 0 200 90" aria-hidden="true">
          <polyline points="100,6 190,84 10,84" fill="none" stroke="#c8c8ce" stroke-width="1" />
        </svg>
      </section>

      <section class="features" id="features">
        <div class="eyebrow">${t('landing.features.eyebrow')}</div>
        <h2 class="section-title">${t('landing.features.title')}</h2>
        <div class="feature-grid">
          <div class="feature-card">
            <div class="feature-icon">${ICON_CHART}</div>
            <h3>${t('landing.features.technical.title')}</h3>
            <p>${t('landing.features.technical.body')}</p>
          </div>
          <div class="feature-card">
            <div class="feature-icon">${ICON_FILE}</div>
            <h3>${t('landing.features.ai.title')}</h3>
            <p>${t('landing.features.ai.body')}</p>
          </div>
          <div class="feature-card">
            <div class="feature-icon">${ICON_BELL}</div>
            <h3>${t('landing.features.alerts.title')}</h3>
            <p>${t('landing.features.alerts.body')}</p>
          </div>
          <div class="feature-card">
            <div class="feature-icon">${ICON_SHIELD}</div>
            <h3>${t('landing.features.privacy.title')}</h3>
            <p>${t('landing.features.privacy.body')}</p>
          </div>
        </div>
      </section>

      <section class="cta-section">
        <h2>${t('landing.cta.title')}</h2>
        <p>${t('landing.cta.subtitle')}</p>
        <button class="btn btn-filled-gold" id="cta-register-btn">${t('landing.cta.button')}</button>
      </section>

      <footer class="footer">
        <div id="privacy"></div>
        <div class="footer-top">
          <div class="footer-brand">
            <div class="brand-row">
              <img src="/assets/eural-logo.png" alt="Eural" />
              <span>EURAL</span>
            </div>
            <p>${t('landing.footer.company.tagline')}</p>
          </div>
          <div class="footer-columns">
            <div class="footer-col">
              <h4>${t('landing.footer.column.product')}</h4>
              <button id="footer-features-link">${t('landing.header.nav.features')}</button>
              <button id="footer-login-link">${t('landing.header.cta.login')}</button>
              <button id="footer-register-link">${t('landing.header.cta.register')}</button>
            </div>
            <div class="footer-col">
              <h4>${t('landing.footer.column.company')}</h4>
              <a href="mailto:contacto@euralsoft.com">${t('landing.footer.link.contact')}</a>
              <button id="footer-privacy-link">${t('landing.footer.link.privacy')}</button>
            </div>
          </div>
        </div>
        <div class="copyright">${t('landing.footer.copyright')}</div>
      </footer>
    `;
  }

  protected afterRender(): void {
    const goLogin = (): void => navigate('/app/login');
    const goRegister = (): void => navigate('/app/register');
    const scrollTo = (id: string): void => this.shadow.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
    const closeMobileMenu = (): void => {
      this._mobileMenuOpen = false;
      this.shadow.getElementById('mobile-menu')?.classList.remove('open');
    };

    this.shadow.getElementById('header-login-btn')?.addEventListener('click', goLogin);
    this.shadow.getElementById('header-register-btn')?.addEventListener('click', goRegister);
    this.shadow.getElementById('hero-login-btn')?.addEventListener('click', goLogin);
    this.shadow.getElementById('hero-register-btn')?.addEventListener('click', goRegister);
    this.shadow.getElementById('cta-register-btn')?.addEventListener('click', goRegister);
    this.shadow.getElementById('footer-login-link')?.addEventListener('click', goLogin);
    this.shadow.getElementById('footer-register-link')?.addEventListener('click', goRegister);

    this.shadow.getElementById('nav-features')?.addEventListener('click', () => scrollTo('features'));
    this.shadow.getElementById('nav-product')?.addEventListener('click', () => scrollTo('product'));
    this.shadow.getElementById('footer-features-link')?.addEventListener('click', () => scrollTo('features'));
    this.shadow.getElementById('footer-privacy-link')?.addEventListener('click', () => scrollTo('privacy'));

    this.shadow.getElementById('hamburger-btn')?.addEventListener('click', () => {
      this._mobileMenuOpen = !this._mobileMenuOpen;
      this.shadow.getElementById('mobile-menu')?.classList.toggle('open', this._mobileMenuOpen);
    });
    this.shadow.getElementById('mobile-nav-features')?.addEventListener('click', () => { scrollTo('features'); closeMobileMenu(); });
    this.shadow.getElementById('mobile-nav-product')?.addEventListener('click', () => { scrollTo('product'); closeMobileMenu(); });
    this.shadow.getElementById('mobile-login-btn')?.addEventListener('click', goLogin);
    this.shadow.getElementById('mobile-register-btn')?.addEventListener('click', goRegister);
  }
}

customElements.define('pi-landing-page', LandingPage);
