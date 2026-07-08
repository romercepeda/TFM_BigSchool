// Component test for Changeset C11 — pi-landing-page CTA navigation.
// Spec 00c: every CTA on the marketing landing must route to the app's
// existing login/register entry points under /app/*.

import { describe, it, expect, vi, afterEach } from 'vitest';

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }));

vi.mock('../../src/router/router.js', () => ({
  navigate: navigateMock,
}));

import '../../src/screens/landing-page.js';

function mount(): HTMLElement {
  const el = document.createElement('pi-landing-page');
  document.body.appendChild(el);
  return el;
}

describe('pi-landing-page — CTA navigation (Changeset C11)', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    navigateMock.mockReset();
  });

  it('header CTAs navigate to /app/login and /app/register', async () => {
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    (el.shadowRoot!.getElementById('header-login-btn') as HTMLElement).click();
    expect(navigateMock).toHaveBeenCalledWith('/app/login');

    (el.shadowRoot!.getElementById('header-register-btn') as HTMLElement).click();
    expect(navigateMock).toHaveBeenCalledWith('/app/register');
  });

  it('hero CTAs navigate to /app/register (primary) and /app/login (secondary)', async () => {
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    (el.shadowRoot!.getElementById('hero-register-btn') as HTMLElement).click();
    expect(navigateMock).toHaveBeenCalledWith('/app/register');

    (el.shadowRoot!.getElementById('hero-login-btn') as HTMLElement).click();
    expect(navigateMock).toHaveBeenCalledWith('/app/login');
  });

  it('bottom CTA section button navigates to /app/register', async () => {
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    (el.shadowRoot!.getElementById('cta-register-btn') as HTMLElement).click();
    expect(navigateMock).toHaveBeenCalledWith('/app/register');
  });

  it('footer PRODUCTO column links navigate to /app/login and /app/register', async () => {
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    (el.shadowRoot!.getElementById('footer-login-link') as HTMLElement).click();
    expect(navigateMock).toHaveBeenCalledWith('/app/login');

    (el.shadowRoot!.getElementById('footer-register-link') as HTMLElement).click();
    expect(navigateMock).toHaveBeenCalledWith('/app/register');
  });

  it('mobile menu login/register buttons navigate to /app/login and /app/register', async () => {
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    (el.shadowRoot!.getElementById('mobile-login-btn') as HTMLElement).click();
    expect(navigateMock).toHaveBeenCalledWith('/app/login');

    (el.shadowRoot!.getElementById('mobile-register-btn') as HTMLElement).click();
    expect(navigateMock).toHaveBeenCalledWith('/app/register');
  });

  it('hamburger button toggles the mobile menu open state', async () => {
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    const menu = el.shadowRoot!.getElementById('mobile-menu') as HTMLElement;
    expect(menu.classList.contains('open')).toBe(false);

    (el.shadowRoot!.getElementById('hamburger-btn') as HTMLElement).click();
    expect(el.shadowRoot!.getElementById('mobile-menu')!.classList.contains('open')).toBe(true);
  });
});
