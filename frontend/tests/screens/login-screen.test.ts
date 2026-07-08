// Component test for Changeset C10 — inline register mode toggle on pi-login-screen.

import { describe, it, expect, vi, afterEach } from 'vitest';

vi.mock('../../src/api/auth.js', () => ({
  login: vi.fn(),
  register: vi.fn(),
  guestLogin: vi.fn(),
}));

vi.mock('../../src/api/portfolios.js', () => ({
  listPortfolios: vi.fn(),
}));

import '../../src/screens/login-screen.js';
import { login, register } from '../../src/api/auth.js';
import { currentUser } from '../../src/state/auth-state.js';

const mockLoginResponse = {
  user: {
    id: 'u1', email: 'test@example.com', display_name: null,
    preferred_language: 'es', auth_provider: 'password',
    must_change_password: false, roles: [], permissions: [],
  },
  session: { portfolios_count: 0, notifications_poll_interval_seconds: 30, csrf_token: 'csrf-token' },
};

function mount(): HTMLElement {
  const el = document.createElement('pi-login-screen');
  document.body.appendChild(el);
  return el;
}

function fill(el: HTMLElement, email: string, password: string): void {
  (el.shadowRoot!.getElementById('email') as HTMLInputElement).value = email;
  (el.shadowRoot!.getElementById('password') as HTMLInputElement).value = password;
}

describe('pi-login-screen — register mode toggle (Changeset C10)', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    currentUser.value = null;
    vi.mocked(login).mockReset();
    vi.mocked(register).mockReset();
  });

  it('starts in login mode: no display_name field, toggle link offers to switch to register', async () => {
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    expect(el.shadowRoot!.getElementById('display-name')).toBeNull();
    expect(el.shadowRoot!.getElementById('mode-toggle-link')?.textContent).toContain('Crear una');
  });

  it('clicking the toggle link switches to register mode: display_name field and submit label change', async () => {
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    (el.shadowRoot!.getElementById('mode-toggle-link') as HTMLElement).click();

    expect(el.shadowRoot!.getElementById('display-name')).not.toBeNull();
    expect(el.shadowRoot!.getElementById('submit-btn')?.textContent).toContain('Crear cuenta');
    expect(el.shadowRoot!.getElementById('mode-toggle-link')?.textContent).toContain('Iniciar sesión');
  });

  it('clicking the toggle link again switches back to login mode', async () => {
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    (el.shadowRoot!.getElementById('mode-toggle-link') as HTMLElement).click();
    (el.shadowRoot!.getElementById('mode-toggle-link') as HTMLElement).click();

    expect(el.shadowRoot!.getElementById('display-name')).toBeNull();
    expect(el.shadowRoot!.getElementById('submit-btn')?.textContent).toContain('Entrar');
  });

  it('submitting the login form calls login() with email and password', async () => {
    vi.mocked(login).mockResolvedValueOnce(mockLoginResponse as never);
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    fill(el, 'user@example.com', 'password123');
    (el.shadowRoot!.getElementById('submit-btn') as HTMLElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(login).toHaveBeenCalledWith({ email: 'user@example.com', password: 'password123' });
    expect(register).not.toHaveBeenCalled();
  });

  it('submitting the register form calls register(), omitting display_name when left empty', async () => {
    vi.mocked(register).mockResolvedValueOnce(mockLoginResponse as never);
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    (el.shadowRoot!.getElementById('mode-toggle-link') as HTMLElement).click();
    fill(el, 'new@example.com', 'password123');
    (el.shadowRoot!.getElementById('submit-btn') as HTMLElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(register).toHaveBeenCalledWith('new@example.com', 'password123', undefined);
  });

  it('submitting the register form passes display_name when typed', async () => {
    vi.mocked(register).mockResolvedValueOnce(mockLoginResponse as never);
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    (el.shadowRoot!.getElementById('mode-toggle-link') as HTMLElement).click();
    fill(el, 'new@example.com', 'password123');
    (el.shadowRoot!.getElementById('display-name') as HTMLInputElement).value = 'Juan Pérez';
    (el.shadowRoot!.getElementById('submit-btn') as HTMLElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(register).toHaveBeenCalledWith('new@example.com', 'password123', 'Juan Pérez');
  });

  it('shows inline validation errors and does not call the API for an invalid email or short password', async () => {
    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    fill(el, 'not-an-email', 'short');
    (el.shadowRoot!.getElementById('submit-btn') as HTMLElement).click();
    await new Promise((r) => setTimeout(r, 0));

    expect(el.shadowRoot!.querySelectorAll('.field-error').length).toBe(2);
    expect(login).not.toHaveBeenCalled();
  });

  it('handles 409 on register: shows the email-exists message with an action link that switches to login mode preserving the email', async () => {
    const { ApiError } = await import('../../src/api/types.js');
    vi.mocked(register).mockRejectedValueOnce(new ApiError(409, 'conflict', 'An account with this email already exists.'));

    const el = mount();
    await new Promise((r) => setTimeout(r, 0));

    (el.shadowRoot!.getElementById('mode-toggle-link') as HTMLElement).click();
    fill(el, 'existing@example.com', 'password123');
    (el.shadowRoot!.getElementById('submit-btn') as HTMLElement).click();
    await new Promise((r) => setTimeout(r, 0));

    const switchLink = el.shadowRoot!.getElementById('switch-to-login-link');
    expect(switchLink).not.toBeNull();
    expect(el.shadowRoot!.getElementById('error')?.textContent).toContain('Ya existe una cuenta con este email');

    switchLink!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await new Promise((r) => setTimeout(r, 0));

    expect(el.shadowRoot!.getElementById('display-name')).toBeNull();
    expect((el.shadowRoot!.getElementById('email') as HTMLInputElement).value).toBe('existing@example.com');
  });
});
