import { LitElement, html } from 'lit';
import '@vaadin/button';
import '@vaadin/icon';

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

  render() {
    const svc = this.service;

    return html`
      <dialog
        id="service-manager-dialog"
        class="app-modal-dialog"
        closedby="any"
        aria-labelledby="service-dialog-title"
      >
        <div class="modal-header" id="service-dialog-title">
          <span>Background Service (${svc?.service_manager || 'launchd / systemd'})</span>
          <button type="button" class="icon-btn" @click=${() => this.close()} aria-label="Close">
            <vaadin-icon ligature="close"></vaadin-icon>
          </button>
        </div>

        ${svc
          ? html`
              <div class="modal-body">
                <div class="meta-inline">
                  <span class="state-badge ${svc.running ? 'state-running' : svc.installed ? 'state-building' : 'state-idle'}">
                    <span class="status-dot ${svc.running ? 'dot-ready' : svc.installed ? 'dot-starting' : 'dot-offline'}"></span>
                    ${svc.running ? 'Running' : svc.installed ? 'Installed (Stopped)' : 'Not Installed'}
                  </span>
                  <span class="raw-token">${svc.service_name}</span>
                  <span class="raw-token">${svc.platform}</span>
                </div>

                <div class="kv-stack">
                  <div class="kv-row">
                    <span class="kv-label">${svc.service_manager === 'hkcu-run' ? 'Registry Key' : 'Unit File'}</span>
                    <span class="raw-token path">${svc.unit_path}</span>
                  </div>
                  <div class="kv-row">
                    <span class="kv-label">Command</span>
                    <code class="code-inline">${svc.exec_start}</code>
                  </div>
                  <div class="kv-row">
                    <span class="kv-label">CLI</span>
                    <code class="code-inline">uv run lms-webui service install --port ${svc.port || 8420}</code>
                  </div>
                </div>

                <div class="modal-footer-split">
                  <div>
                    ${svc.installed
                      ? html`
                          <vaadin-button
                            id="service-uninstall-btn"
                            theme="error"
                            ?disabled=${this.busy}
                            @click=${() => this.emitAction('uninstall')}
                          >
                            Uninstall
                          </vaadin-button>
                        `
                      : ''}
                  </div>
                  <div class="modal-footer-actions">
                    <vaadin-button @click=${() => this.close()}>
                      Close
                    </vaadin-button>
                    ${svc.installed
                      ? html`
                          <vaadin-button
                            id="service-restart-btn"
                            ?disabled=${this.busy}
                            @click=${() => this.emitAction('restart')}
                          >
                            Restart
                          </vaadin-button>
                        `
                      : ''}
                    <vaadin-button
                      id="service-install-btn"
                      theme="primary"
                      ?disabled=${this.busy}
                      @click=${() => this.emitAction('install')}
                    >
                      ${svc.installed ? 'Update Service' : 'Install Service'}
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
