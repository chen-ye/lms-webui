import { LitElement, html, css } from 'lit';
import '@vaadin/button';

export class ConfirmDialog extends LitElement {
  static properties = {
    opened: { type: Boolean, reflect: true },
    header: { type: String },
    message: { type: String },
    command: { type: String },
    paths: { type: Array },
    confirmText: { type: String },
    confirmTheme: { type: String },
    cancelText: { type: String },
  };

  static styles = css`
    :host {
      display: contents;
    }

    dialog {
      margin: auto;
      padding: var(--lumo-space-l);
      max-width: 520px;
      width: calc(100vw - 32px);
      box-sizing: border-box;
      border: 1px solid var(--lumo-contrast-20pct);
      border-radius: var(--lumo-border-radius-l);
      background-color: var(--lumo-base-color);
      color: var(--lumo-body-text-color);
      font-family: var(--lumo-font-family);
      box-shadow: var(--lumo-box-shadow-xl);
    }

    dialog::backdrop {
      background-color: var(--lumo-shade-60pct);
      backdrop-filter: blur(2px);
      -webkit-backdrop-filter: blur(2px);
    }

    .dialog-header {
      font-size: var(--lumo-font-size-l);
      font-weight: 600;
      color: var(--lumo-header-text-color, var(--lumo-body-text-color));
      margin-bottom: var(--lumo-space-s);
      display: flex;
      align-items: center;
      gap: var(--lumo-space-s);
    }

    .dialog-body {
      font-size: var(--lumo-font-size-m);
      color: var(--lumo-secondary-text-color);
      line-height: var(--lumo-line-height-m);
      margin-bottom: var(--lumo-space-l);
      display: flex;
      flex-direction: column;
      gap: var(--lumo-space-s);
    }

    .command-preview {
      padding: 6px 8px;
      border-radius: var(--lumo-border-radius-s);
      background: var(--lumo-contrast-10pct);
      border: 1px solid var(--lumo-contrast-20pct);
      font-size: var(--lumo-font-size-xs);
      font-family: var(--lumo-font-family-monospace, monospace);
      color: var(--lumo-secondary-text-color);
      word-break: break-all;
    }

    .paths-list {
      margin: 0;
      padding: 0;
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .dialog-footer {
      display: flex;
      justify-content: flex-end;
      gap: var(--lumo-space-s);
    }
  `;

  constructor() {
    super();
    this.opened = false;
    this.header = 'Confirm Action';
    this.message = '';
    this.command = '';
    this.paths = [];
    this.confirmText = 'Confirm';
    this.confirmTheme = 'primary error';
    this.cancelText = 'Cancel';
  }

  get dialogEl() {
    return this.renderRoot?.querySelector('dialog');
  }

  firstUpdated() {
    const dlg = this.dialogEl;
    if (dlg) {
      dlg.addEventListener('cancel', (e) => {
        e.preventDefault();
        this.onCancel();
      });
      dlg.addEventListener('close', () => {
        if (this.opened) {
          this.opened = false;
          this.dispatchEvent(new CustomEvent('cancel', { bubbles: true, composed: true }));
        }
      });

      // Fallback for browsers without declarative <dialog closedby="any"> support
      if (!('closedBy' in HTMLDialogElement.prototype)) {
        dlg.addEventListener('click', (event) => {
          if (event.target !== dlg) return;
          const rect = dlg.getBoundingClientRect();
          const isDialogContent =
            rect.top <= event.clientY &&
            event.clientY <= rect.top + rect.height &&
            rect.left <= event.clientX &&
            event.clientX <= rect.left + rect.width;
          if (isDialogContent) return;
          this.onCancel();
        });
      }
    }
  }

  updated(changedProps) {
    if (changedProps.has('opened')) {
      const dlg = this.dialogEl;
      if (this.opened) {
        if (dlg && !dlg.open) {
          try {
            dlg.showModal();
          } catch (e) {}
        }
      } else if (dlg && dlg.open) {
        dlg.close();
      }
    }
  }

  open() {
    this.opened = true;
    const dlg = this.dialogEl;
    if (dlg && !dlg.open) {
      try {
        dlg.showModal();
      } catch (e) {}
    }
    requestAnimationFrame(() => {
      const confirmBtn = this.renderRoot?.querySelector('[data-role="confirm"]');
      if (confirmBtn) confirmBtn.focus();
    });
  }

  close() {
    this.opened = false;
    const dlg = this.dialogEl;
    if (dlg && dlg.open) {
      dlg.close();
    }
  }

  onConfirm() {
    this.close();
    this.dispatchEvent(new CustomEvent('confirm', { bubbles: true, composed: true }));
  }

  onCancel() {
    this.close();
    this.dispatchEvent(new CustomEvent('cancel', { bubbles: true, composed: true }));
  }

  handleKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const active = this.shadowRoot?.activeElement || document.activeElement;
      if (active?.getAttribute?.('data-role') === 'cancel') {
        return;
      }
      e.preventDefault();
      e.stopPropagation();
      this.onConfirm();
    }
  }

  render() {
    return html`
      <dialog
        closedby="any"
        aria-labelledby="confirm-dialog-title"
        @keydown=${(e) => this.handleKeydown(e)}
      >
        <div class="dialog-header" id="confirm-dialog-title">
          <slot name="icon"></slot>
          <span>${this.header}</span>
        </div>
        <div class="dialog-body">
          ${this.message ? html`<div>${this.message}</div>` : ''}
          ${this.command ? html`<div class="command-preview">${this.command}</div>` : ''}
          ${(this.paths || []).length > 0
            ? html`
                <ul class="paths-list">
                  ${this.paths.map((p) => html`<li class="command-preview">${p}</li>`)}
                </ul>
              `
            : ''}
          <slot name="content"></slot>
        </div>
        <div class="dialog-footer">
          <vaadin-button
            data-role="cancel"
            @click=${() => this.onCancel()}
          >
            ${this.cancelText}
          </vaadin-button>
          <vaadin-button
            data-role="confirm"
            theme="${this.confirmTheme}"
            @click=${() => this.onConfirm()}
          >
            ${this.confirmText}
          </vaadin-button>
        </div>
      </dialog>
    `;
  }
}

customElements.define('confirm-dialog', ConfirmDialog);
