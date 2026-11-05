import { LitElement, html } from 'lit';
import '@vaadin/button';
import '@vaadin/combo-box';
import '@vaadin/icon';
import { formatContextTokens } from '../utils/format.js';

const CONTEXT_PRESETS = [2048, 4096, 8192, 16384, 32768, 65536, 131072];

export class LoadModelDialog extends LitElement {
  static properties = {
    opened: { type: Boolean },
    model: { type: Object },
    defaultContextLength: { type: Number },
    selectedModelId: { type: String },
    contextLength: { type: Number },
    evalBatchSize: { type: Number },
    flashAttention: { type: Boolean },
    offloadKvCacheToGpu: { type: Boolean },
    numExperts: { type: Number },
    loading: { type: Boolean },
  };

  createRenderRoot() {
    return this;
  }

  constructor() {
    super();
    this.opened = false;
    this.model = null;
    this.defaultContextLength = 8192;
    this.selectedModelId = '';
    this.contextLength = 8192;
    this.evalBatchSize = 512;
    this.flashAttention = true;
    this.offloadKvCacheToGpu = true;
    this.numExperts = 0;
    this.loading = false;
  }

  get dialogEl() {
    return this.querySelector('dialog#load-model-dialog');
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

  openForModel(model, defaultCtx = 8192) {
    this.model = model;
    this.defaultContextLength = defaultCtx || 8192;
    this.selectedModelId = model.selected_variant || model.key;

    const activeCfg = model.loaded_instances?.[0]?.config || {};
    const maxCtx = model.max_context_length || defaultCtx || 8192;
    this.contextLength =
      activeCfg.context_length || Math.min(this.defaultContextLength, maxCtx);
    this.evalBatchSize = activeCfg.eval_batch_size || 512;
    this.flashAttention =
      activeCfg.flash_attention !== undefined ? Boolean(activeCfg.flash_attention) : true;
    this.offloadKvCacheToGpu =
      activeCfg.offload_kv_cache_to_gpu !== undefined
        ? Boolean(activeCfg.offload_kv_cache_to_gpu)
        : true;
    this.numExperts = activeCfg.num_experts || 0;

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

  get supportsLlamaCppTuning() {
    if (!this.model) return false;
    if (this.model.type === 'embedding') return false;
    return (this.model.format || '').toLowerCase() === 'gguf';
  }

  buildPayload() {
    const payload = {
      model: this.selectedModelId || this.model?.key || '',
      echo_load_config: true,
    };
    if (this.contextLength && this.contextLength > 0) {
      payload.context_length = Number(this.contextLength);
    }
    if (this.supportsLlamaCppTuning) {
      if (this.evalBatchSize && this.evalBatchSize > 0) {
        payload.eval_batch_size = Number(this.evalBatchSize);
      }
      payload.flash_attention = Boolean(this.flashAttention);
      payload.offload_kv_cache_to_gpu = Boolean(this.offloadKvCacheToGpu);
      if (this.numExperts && this.numExperts > 0) {
        payload.num_experts = Number(this.numExperts);
      }
    }
    return payload;
  }

  submitLoad() {
    const payload = this.buildPayload();
    this.dispatchEvent(
      new CustomEvent('submit-load', {
        detail: { payload },
        bubbles: true,
        composed: true,
      })
    );
  }

  render() {
    const m = this.model;
    const maxCtx = m?.max_context_length || 0;
    const variants = m?.variants || [];
    const presets = CONTEXT_PRESETS.filter((v) => !maxCtx || v <= maxCtx);
    if (maxCtx && !presets.includes(maxCtx)) {
      presets.push(maxCtx);
    }

    return html`
      <dialog
        id="load-model-dialog"
        class="app-modal-dialog"
        closedby="any"
        aria-labelledby="load-dialog-title"
      >
        <div class="modal-header" id="load-dialog-title">
          <span>Load ${m ? m.display_name : 'Model'}</span>
          <button type="button" class="icon-btn" @click=${() => this.close()} aria-label="Close">
            <vaadin-icon ligature="close"></vaadin-icon>
          </button>
        </div>

        ${m
          ? html`
              <div class="modal-body">
                <div class="meta-inline">
                  <span class="raw-token">${m.selected_variant || m.key}</span>
                  ${m.format ? html`<span class="raw-token">${m.format.toUpperCase()}</span>` : ''}
                </div>

                ${variants.length > 1
                  ? html`
                      <vaadin-combo-box
                        label="Quantization Variant"
                        .items=${variants}
                        .value=${this.selectedModelId}
                        @value-changed=${(e) => {
                          this.selectedModelId = e.detail.value;
                        }}
                      ></vaadin-combo-box>
                    `
                  : ''}

                <div class="field-group">
                  <div class="field-label-row">
                    <label for="load-context-length-input">
                      Context Length ${maxCtx ? `(max ${formatContextTokens(maxCtx)})` : ''}
                    </label>
                    <div class="preset-chips">
                      ${presets.map(
                        (p) => html`
                          <button
                            type="button"
                            class="chip-btn ${this.contextLength === p ? 'active' : ''}"
                            @click=${() => {
                              this.contextLength = p;
                            }}
                          >
                            ${p === maxCtx ? `Max (${formatContextTokens(p)})` : formatContextTokens(p)}
                          </button>
                        `
                      )}
                    </div>
                  </div>
                  <input
                    id="load-context-length-input"
                    class="text-input mono"
                    type="number"
                    min="512"
                    max="${maxCtx || 1048576}"
                    step="512"
                    .value=${String(this.contextLength)}
                    @input=${(e) => {
                      this.contextLength = Number(e.target.value || 4096);
                    }}
                  />
                </div>

                ${this.supportsLlamaCppTuning
                  ? html`
                      <div class="form-grid">
                        <div class="field-group">
                          <label for="load-batch-size-input">Eval Batch Size</label>
                          <input
                            id="load-batch-size-input"
                            class="text-input mono"
                            type="number"
                            min="32"
                            max="8192"
                            step="64"
                            .value=${String(this.evalBatchSize)}
                            @input=${(e) => {
                              this.evalBatchSize = Number(e.target.value || 512);
                            }}
                          />
                        </div>

                        <div class="field-group">
                          <label for="load-num-experts-input">MoE Experts (0 = Default)</label>
                          <input
                            id="load-num-experts-input"
                            class="text-input mono"
                            type="number"
                            min="0"
                            max="256"
                            step="1"
                            .value=${String(this.numExperts)}
                            @input=${(e) => {
                              this.numExperts = Number(e.target.value || 0);
                            }}
                          />
                        </div>
                      </div>

                      <div class="toggle-row">
                        <label class="compact-toggle">
                          <input
                            id="load-flash-attention-checkbox"
                            type="checkbox"
                            .checked=${this.flashAttention}
                            @change=${(e) => {
                              this.flashAttention = e.target.checked;
                            }}
                          />
                          <span>Flash Attention</span>
                        </label>

                        <label class="compact-toggle">
                          <input
                            id="load-offload-kv-checkbox"
                            type="checkbox"
                            .checked=${this.offloadKvCacheToGpu}
                            @change=${(e) => {
                              this.offloadKvCacheToGpu = e.target.checked;
                            }}
                          />
                          <span>Offload KV Cache to GPU</span>
                        </label>
                      </div>
                    `
                  : ''}

                <div class="modal-footer">
                  <vaadin-button theme="tertiary" @click=${() => this.close()}>
                    Cancel
                  </vaadin-button>
                  <vaadin-button
                    id="confirm-load-model-btn"
                    theme="primary"
                    ?disabled=${this.loading}
                    @click=${() => this.submitLoad()}
                  >
                    ${this.loading ? 'Loading...' : 'Load Model'}
                  </vaadin-button>
                </div>
              </div>
            `
          : ''}
      </dialog>
    `;
  }
}

customElements.define('load-dialog', LoadModelDialog);
