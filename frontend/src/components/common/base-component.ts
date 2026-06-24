// BaseComponent — Spec D10 §4.1.
// Wires Web Components + @preact/signals-core so render() re-runs automatically
// whenever any signal accessed inside it changes.

import { effect } from '@preact/signals-core';

export abstract class BaseComponent extends HTMLElement {
  protected shadow: ShadowRoot;
  private _disposeEffect: (() => void) | null = null;

  constructor() {
    super();
    this.shadow = this.attachShadow({ mode: 'open' });
  }

  connectedCallback(): void {
    this._disposeEffect = effect(() => {
      this.shadow.innerHTML = this.render();
      this.afterRender();
    });
  }

  disconnectedCallback(): void {
    this._disposeEffect?.();
    this._disposeEffect = null;
  }

  protected abstract render(): string;

  // Override to attach event listeners after each render.
  // eslint-disable-next-line @typescript-eslint/no-empty-function
  protected afterRender(): void {}
}
