import { LitElement, html } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { SignalWatcher } from '@lit-labs/signals';
import '@vaadin/button';
import '@vaadin/icon';
import { api } from '../services/api.js';
import { formatContextTokens, formatDurationSeconds } from '../utils/format.js';

export class LoadedDock extends SignalWatcher(LitElement) {
  static properties = {
    layout: { type: String }, // 'bar' or 'sidebar'
  };

  createRenderRoot() {
    return this;
  }

  constructor() {
    super();
    this.layout = 'bar';
  }

  onUnload(instanceId) {
    api.unloadModel(instanceId);
  }

  onUnloadAll() {
    api.unloadAllModels();
  }

  render() {
    const loaded = api.loadedInstancesComputed.get();
    const busy = api.busyActionSignal.get();

    if (this.layout === 'sidebar') {
      return html`
        <div class="surfaces-sidebar-container">
          <div class="surfaces-sidebar-header">
            <span class="surfaces-sidebar-title">
              Loaded in Memory (${loaded.length})
            </span>
            ${loaded.length > 0
              ? html`
                  <button
                    type="button"
                    class="chip-btn"
                    ?disabled=${busy === 'unload-all'}
                    @click=${() => this.onUnloadAll()}
                    title="Unload all loaded model instances"
                  >
                    Unload All
                  </button>
                `
              : ''}
          </div>

          ${loaded.length === 0
            ? html`
                <div style="font-size: var(--lumo-font-size-xs); color: var(--lumo-tertiary-text-color); padding: var(--lumo-space-s) 0;">
                  No models currently loaded in memory.
                </div>
              `
            : html`
                <div style="display: flex; flex-direction: column; gap: var(--lumo-space-s);">
                  ${repeat(
                    loaded,
                    (inst) => inst.instance_id,
                    (inst) => {
                      const cfg = inst.config || {};
                      const isUnloading = busy === `unload:${inst.instance_id}`;
                      return html`
                        <div class="surface-card" data-instance-id="${inst.instance_id}">
                          <div style="display: flex; align-items: center; justify-content: space-between; gap: var(--lumo-space-xs); margin-bottom: 4px;">
                            <div style="display: flex; align-items: center; gap: 6px; min-width: 0;">
                              <span class="status-dot dot-ready"></span>
                              <span
                                style="font-weight: 600; font-size: var(--lumo-font-size-xs); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;"
                                title="${inst.instance_id}"
                              >
                                ${inst.display_name}
                              </span>
                            </div>
                            <vaadin-button
                              theme="small error tertiary-inline"
                              ?disabled=${isUnloading}
                              @click=${() => this.onUnload(inst.instance_id)}
                              title="Unload ${inst.instance_id}"
                            >
                              ${isUnloading ? '...' : 'Eject'}
                            </vaadin-button>
                          </div>

                          <div style="font-family: var(--lumo-font-family-monospace, monospace); font-size: var(--lumo-font-size-xxs); color: var(--lumo-secondary-text-color); margin-bottom: 4px; word-break: break-all;">
                            ${inst.instance_id}
                          </div>

                          <div style="display: flex; flex-wrap: wrap; gap: 4px;">
                            ${cfg.context_length
                              ? html`<span class="raw-token">ctx ${formatContextTokens(cfg.context_length)}</span>`
                              : ''}
                            ${cfg.flash_attention
                              ? html`<span class="raw-token">FA</span>`
                              : ''}
                            ${cfg.parallel
                              ? html`<span class="raw-token">${cfg.parallel}x par</span>`
                              : ''}
                            ${inst.remaining_ttl_seconds !== null && inst.remaining_ttl_seconds !== undefined
                              ? html`<span class="raw-token" title="Remaining Idle TTL">TTL ${formatDurationSeconds(inst.remaining_ttl_seconds)}</span>`
                              : ''}
                          </div>
                        </div>
                      `;
                    }
                  )}
                </div>
              `}
        </div>
      `;
    }

    // Horizontal bar layout (< 1120px)
    return html`
      <div class="surfaces-dock">
        <span style="font-weight: 600; color: var(--lumo-secondary-text-color); flex-shrink: 0;">
          Loaded (${loaded.length}):
        </span>
        ${loaded.length === 0
          ? html`<span style="color: var(--lumo-tertiary-text-color);">None in memory</span>`
          : html`
              <div style="display: flex; align-items: center; gap: var(--lumo-space-xs); overflow-x: auto; flex: 1;">
                ${repeat(
                  loaded,
                  (inst) => inst.instance_id,
                  (inst) => html`
                    <div
                      style="display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border-radius: var(--lumo-border-radius-m); background: var(--lumo-contrast-5pct); border: 1px solid var(--lumo-contrast-10pct); flex-shrink: 0;"
                    >
                      <span class="status-dot dot-ready"></span>
                      <span style="font-weight: 500;">${inst.display_name}</span>
                      ${inst.config?.context_length
                        ? html`<span class="raw-token">${formatContextTokens(inst.config.context_length)}</span>`
                        : ''}
                      <button
                        type="button"
                        class="icon-btn"
                        style="padding: 2px; color: var(--lumo-error-text-color);"
                        @click=${() => this.onUnload(inst.instance_id)}
                        title="Unload ${inst.instance_id}"
                      >
                        <vaadin-icon ligature="eject" style="width: 14px; height: 14px;"></vaadin-icon>
                      </button>
                    </div>
                  `
                )}
              </div>
              <button
                type="button"
                class="chip-btn"
                @click=${() => this.onUnloadAll()}
              >
                Unload All
              </button>
            `}
      </div>
    `;
  }
}

customElements.define('loaded-dock', LoadedDock);
