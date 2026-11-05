import { LitElement, html } from 'lit';
import '@vaadin/button';
import '@vaadin/icon';
import { copyToClipboard } from '../utils/clipboard.js';

export class ServiceDialog extends LitElement {
  static properties = {
    opened: { type: Boolean },
    service: { type: Object },
    busy: { type: Boolean },
  };

  createRenderRoot() {
    return this;
  }

  constructor() {
    super();
    this.opened = false;
    this.service = null;
    this.busy = false;
  }

  get dialogEl() {
    return this.querySelector('dialog#service-manager-dialog');
  }

  firstUpdated() {
    const dlg = this.dialogEl;
    if (dlg) {
      dlg.addEventListener('cancel', (e) => {
        e.preventDefault();
        this.close();
      });
      if (!('closedBy' in HTMLDialogElement.prototype)) {
        dlg.addEventListener('click', (event) => {
          if (event.target !== dlg) return;
          const rect = dlg.getBoundingClientRect();
          const isDialogContent =
            rect.top <= event.clientY &&
            event.clientY <= rect.top + rect.height &&
            rect.left <= event.clientX &&
            event.clientX <= rect.left + rect.width;
          if (!isDialogContent) this.close();
        });
      }
    }
  }

  open(serviceInfo) {
    this.service = serviceInfo;
    this.opened = true;
    const dlg = this.dialogEl;
    if (dlg && !dlg.open) {
      try {
        dlg.showModal();
      } catch (e) {}
    }
  }

  close() {
    this.opened = false;
    const dlg = this.dialogEl;
    if (dlg && dlg.open) {
      dlg.close();
    }
  }

  emitAction(action) {
    this.dispatchEvent(
      new CustomEvent('service-action', {
        detail: { action },
        bubbles: true,
        composed: true,
      })
    );
  }

  copyCmd(cmd, e) {
    copyToClipboard(cmd);
    const btn = e.currentTarget;
    const orig = btn.innerText;
    btn.innerText = 'Copied';
    setTimeout(() => {
      btn.innerText = orig;
    }, 1200);
  }

  render() {
    const svc = this.service;
    const cliInstallCmd = `uv run lms-webui service install --port ${svc?.port || 8420}`;

    return html`
      <dialog
        id="service-manager-dialog"
        closedby="any"
        aria-labelledby="service-dialog-title"
        style="
          margin: auto;
          padding: var(--lumo-space-l);
          max-width: 580px;
          width: calc(100vw - 32px);
          box-sizing: border-box;
          border: 1px solid var(--lumo-contrast-20pct);
          border-radius: var(--lumo-border-radius-l);
          background-color: var(--lumo-base-color);
          color: var(--lumo-body-text-color);
          box-shadow: var(--lumo-box-shadow-xl);
        "
      >
        <div
          id="service-dialog-title"
          style="
            font-size: var(--lumo-font-size-l);
            font-weight: 600;
            margin-bottom: var(--lumo-space-s);
            display: flex;
            align-items: center;
            justify-content: space-between;
          "
        >
          <span style="display: inline-flex; align-items: center; gap: var(--lumo-space-s);">
            <vaadin-icon ligature="settings_applications" style="color: var(--lumo-primary-color);"></vaadin-icon>
            <span>Host Background Service (${svc?.service_manager || 'launchd / systemd'})</span>
          </span>
          <button type="button" class="icon-btn" @click=${() => this.close()} aria-label="Close">
            <vaadin-icon ligature="close"></vaadin-icon>
          </button>
        </div>

        ${svc
          ? html`
              <div style="display: flex; flex-direction: column; gap: var(--lumo-space-m); font-size: var(--lumo-font-size-s);">
                <div style="display: flex; align-items: center; gap: var(--lumo-space-s); flex-wrap: wrap;">
                  <span class="state-badge ${svc.running ? 'state-running' : svc.installed ? 'state-building' : 'state-idle'}">
                    <span class="status-dot ${svc.running ? 'dot-ready' : svc.installed ? 'dot-starting' : 'dot-offline'}"></span>
                    ${svc.running ? 'Running' : svc.installed ? 'Installed (Stopped)' : 'Not Installed'}
                  </span>
                  <span class="raw-token">${svc.service_name}</span>
                  <span class="raw-token flag">${svc.platform} • ${svc.service_manager}</span>
                </div>

                <div>
                  <div style="font-size: var(--lumo-font-size-xxs); font-weight: 600; color: var(--lumo-secondary-text-color); text-transform: uppercase; margin-bottom: 4px;">
                    Service Unit Path
                  </div>
                  <div class="raw-token path" style="width: 100%; justify-content: flex-start; box-sizing: border-box; padding: 4px 8px;">
                    ${svc.unit_path}
                  </div>
                </div>

                <div>
                  <div style="font-size: var(--lumo-font-size-xxs); font-weight: 600; color: var(--lumo-secondary-text-color); text-transform: uppercase; margin-bottom: 4px;">
                    ExecStart Command
                  </div>
                  <pre class="command-box">${svc.exec_start}</pre>
                </div>

                <div>
                  <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
                    <span style="font-size: var(--lumo-font-size-xxs); font-weight: 600; color: var(--lumo-secondary-text-color); text-transform: uppercase;">
                      CLI Registration Equivalent
                    </span>
                    <button type="button" class="chip-btn" @click=${(e) => this.copyCmd(cliInstallCmd, e)}>
                      Copy CLI
                    </button>
                  </div>
                  <pre class="command-box">${cliInstallCmd}</pre>
                </div>

                <div style="display: flex; justify-content: space-between; align-items: center; gap: var(--lumo-space-s); flex-wrap: wrap; margin-top: var(--lumo-space-xs);">
                  <div>
                    ${svc.installed
                      ? html`
                          <vaadin-button
                            id="service-uninstall-btn"
                            theme="error tertiary"
                            ?disabled=${this.busy}
                            @click=${() => this.emitAction('uninstall')}
                          >
                            Uninstall Service
                          </vaadin-button>
                        `
                      : ''}
                  </div>
                  <div style="display: flex; gap: var(--lumo-space-s);">
                    <vaadin-button theme="tertiary" @click=${() => this.close()}>
                      Close
                    </vaadin-button>
                    ${svc.installed
                      ? html`
                          <vaadin-button
                            id="service-restart-btn"
                            theme="contrast"
                            ?disabled=${this.busy}
                            @click=${() => this.emitAction('restart')}
                          >
                            Restart Service
                          </vaadin-button>
                        `
                      : ''}
                    <vaadin-button
                      id="service-install-btn"
                      theme="primary"
                      ?disabled=${this.busy}
                      @click=${() => this.emitAction('install')}
                    >
                      ${svc.installed ? 'Update & Restart Service' : 'Install Background Service'}
                    </vaadin-button>
                  </div>
                </div>
              </div>
            `
          : ''}
      </dialog>
    `;
  }
}

customElements.define('service-dialog', ServiceDialog);
