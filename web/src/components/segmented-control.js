import { LitElement, css, html } from 'lit';

export class SegmentedControl extends LitElement {
  static properties = {
    options: { type: Array },
    value: { type: String },
    theme: { type: String },
    disabled: { type: Boolean },
  };

  static styles = css`
    :host {
      display: inline-flex;
      vertical-align: middle;
    }

    .segmented-control {
      display: inline-flex;
      align-items: center;
      background-color: var(--lumo-contrast-5pct);
      border: 1px solid var(--lumo-contrast-10pct);
      border-radius: var(--lumo-border-radius-m);
      padding: 2px;
      gap: 2px;
      user-select: none;
      box-sizing: border-box;
      vertical-align: middle;
      height: var(--lumo-size-s, 30px);
      min-height: var(--lumo-size-s, 30px);
    }

    .segmented-item {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: transparent;
      border: none;
      border-radius: var(--lumo-border-radius-s);
      color: var(--lumo-secondary-text-color);
      font-family: var(--lumo-font-family);
      font-size: var(--lumo-font-size-xs);
      font-weight: 500;
      line-height: 24px;
      padding: 0 10px;
      height: 24px;
      cursor: pointer;
      white-space: nowrap;
      letter-spacing: 0.02em;
      transition: color 0.12s ease, background-color 0.12s ease, box-shadow 0.12s ease;
      position: relative;
      box-sizing: border-box;
    }

    .segmented-item:hover:not(.selected):not(:disabled) {
      color: var(--lumo-body-text-color);
      background-color: var(--lumo-contrast-5pct);
    }

    .segmented-item.selected {
      background-color: var(--lumo-contrast-20pct);
      color: var(--lumo-body-text-color);
      font-weight: 600;
      box-shadow: var(--lumo-box-shadow-xs);
    }

    .segmented-item:focus-visible {
      outline: 2px solid var(--lumo-primary-color);
      outline-offset: 1px;
    }

    .segmented-item:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  `;

  constructor() {
    super();
    this.options = [];
    this.value = '';
    this.theme = 'small';
    this.disabled = false;
  }

  selectOption(val) {
    if (this.disabled || val === this.value) return;
    this.value = val;
    this.dispatchEvent(
      new CustomEvent('change', {
        detail: { value: val },
        bubbles: true,
        composed: true,
      })
    );
    this.dispatchEvent(
      new CustomEvent('value-changed', {
        detail: { value: val },
        bubbles: true,
        composed: true,
      })
    );
  }

  handleKeyDown(e, currentIndex) {
    if (this.disabled) return;
    let nextIndex = -1;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      nextIndex = (currentIndex + 1) % this.options.length;
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      nextIndex = (currentIndex - 1 + this.options.length) % this.options.length;
    }
    if (nextIndex >= 0 && this.options[nextIndex]) {
      this.selectOption(this.options[nextIndex].value);
      const btns = this.renderRoot.querySelectorAll('.segmented-item');
      btns[nextIndex]?.focus();
    }
  }

  render() {
    return html`
      <div
        class="segmented-control ${this.theme ? `theme-${this.theme}` : ''}"
        role="radiogroup"
        aria-disabled="${this.disabled}"
      >
        ${(this.options || []).map((opt, idx) => {
          const isSelected = opt.value === this.value;
          return html`
            <button
              type="button"
              role="radio"
              class="segmented-item ${isSelected ? 'selected' : ''}"
              aria-checked="${isSelected}"
              title="${opt.title || opt.label}"
              ?disabled=${this.disabled}
              @click=${() => this.selectOption(opt.value)}
              @keydown=${(e) => this.handleKeyDown(e, idx)}
            >
              ${opt.label}
            </button>
          `;
        })}
      </div>
    `;
  }
}

customElements.define('segmented-control', SegmentedControl);
