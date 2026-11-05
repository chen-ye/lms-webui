import { LitElement, html } from 'lit';
import '@vaadin/button';
import '@vaadin/checkbox';
import '@vaadin/combo-box';
import '@vaadin/icon';
import '@vaadin/number-field';
import { copyToClipboard } from '../utils/clipboard.js';
import { formatContextTokens } from '../utils/format.js';

const CONTEXT_PRESETS = [2048, 4096, 8192, 16384, 32768, 65536, 131072];

export class LoadModelDialog extends LitElement {
  static properties = {
    opened: { type: Boolean },
    model: { type: Object },
    defaultContextLength: { type: Number },
    lmstudioUrl: { type: String },
    selectedModelId: { type: String },
    contextLength: { type: Number },
    evalBatchSize: { type: Number },
    flashAttention: { type: Boolean },
    offloadKvCacheToGpu: { type: Boolean },
    numExperts: { type: Number },
    loading: { type: Boolean },
  };

  createRenderRoot() {
    return this; // Light DOM to use Vaadin Lumo tokens directly
  }

  constructor() {
    super();
    this.opened = false;
    this.model = null;
    this.defaultContextLength = 8192;
    this.lmstudioUrl = 'http://localhost:1234';
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

  buildCurlPreview() {
    const payload = this.buildPayload();
    return `curl ${this.lmstudioUrl}/api/v1/models/load \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify(payload, null, 2)}'`;
  }

  copyCurl(e) {
    const text = this.buildCurlPreview();
    copyToClipboard(text);
    const btn = e.currentTarget;
    const orig = btn.innerText;
    btn.innerText = 'Copied';
    setTimeout(() => {
      btn.innerText = orig;
    }, 1200);
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
        closedby="any"
        aria-labelledby="load-dialog-title"
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
          id="load-dialog-title"
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
            <vaadin-icon ligature="memory" style="color: var(--lumo-primary-color);"></vaadin-icon>
            <span>Load Model into Memory</span>
          </span>
          <button type="button" class="icon-btn" @click=${() => this.close()} aria-label="Close">
            <vaadin-icon ligature="close"></vaadin-icon>
          </button>
        </div>

        ${m
          ? html`
              <div style="display: flex; flex-direction: column; gap: var(--lumo-space-m);">
                <div style="display: flex; align-items: center; gap: var(--lumo-space-xs); flex-wrap: wrap;">
                  <span style="font-weight: 600;">${m.display_name}</span>
                  <span class="raw-token">${m.key}</span>
                  ${m.format ? html`<span class="state-badge state-idle">${m.format}</span>` : ''}
                </div>

                ${variants.length > 1
                  ? html`
                      <vaadin-combo-box
                        label="Model Variant"
                        .items=${variants}
                        .value=${this.selectedModelId}
                        @value-changed=${(e) => {
                          this.selectedModelId = e.detail.value;
                        }}
                      ></vaadin-combo-box>
                    `
                  : ''}

                <div>
                  <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
                    <label
                      style="font-size: var(--lumo-font-size-xs); font-weight: 600; color: var(--lumo-secondary-text-color);"
                    >
                      Context Length (tokens)
                      ${maxCtx ? html`<span style="font-weight: 400;"> (Max: ${formatContextTokens(maxCtx)})</span>` : ''}
                    </label>
                    <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                      ${presets.map(
                        (p) => html`
                          <button
                            type="button"
                            class="chip-btn ${this.contextLength === p ? 'active' : ''}"
                            @click=${() => {
                              this.contextLength = p;
                            }}
                          >
                            ${ p === maxCtx ? `Max (${formatContextTokens(p)})` : formatContextTokens(p) }
                          </button>
                        `
                      )}
                    </div>
                  </div>
                  <input
                    id="load-context-length-input"
                    type="number"
                    min="512"
                    max="${maxCtx || 1048576}"
                    step="512"
                    .value=${String(this.contextLength)}
                    @input=${(e) => {
                      this.contextLength = Number(e.target.value || 4096);
                    }}
                    style="
                      width: 100%;
                      box-sizing: border-box;
                      padding: 6px 10px;
                      border-radius: var(--lumo-border-radius-m);
                      border: 1px solid var(--lumo-contrast-20pct);
                      background: var(--lumo-contrast-5pct);
                      color: var(--lumo-body-text-color);
                      font-family: var(--lumo-font-family-monospace, monospace);
                      font-size: var(--lumo-font-size-s);
                    "
                  />
                </div>

                ${this.supportsLlamaCppTuning
                  ? html`
                      <div class="form-grid">
                        <div>
                          <label
                            style="display: block; font-size: var(--lumo-font-size-xs); font-weight: 600; color: var(--lumo-secondary-text-color); margin-bottom: 4px;"
                          >
                            Eval Batch Size
                          </label>
                          <input
                            id="load-batch-size-input"
                            type="number"
                            min="32"
                            max="8192"
                            step="64"
                            .value=${String(this.evalBatchSize)}
                            @input=${(e) => {
                              this.evalBatchSize = Number(e.target.value || 512);
                            }}
                            style="
                              width: 100%;
                              box-sizing: border-box;
                              padding: 6px 10px;
                              border-radius: var(--lumo-border-radius-m);
                              border: 1px solid var(--lumo-contrast-20pct);
                              background: var(--lumo-contrast-5pct);
                              color: var(--lumo-body-text-color);
                              font-family: var(--lumo-font-family-monospace, monospace);
                              font-size: var(--lumo-font-size-s);
                            "
                          />
                        </div>

                        <div>
                          <label
                            style="display: block; font-size: var(--lumo-font-size-xs); font-weight: 600; color: var(--lumo-secondary-text-color); margin-bottom: 4px;"
                          >
                            MoE Experts (0 = Default)
                          </label>
                          <input
                            id="load-num-experts-input"
                            type="number"
                            min="0"
                            max="256"
                            step="1"
                            .value=${String(this.numExperts)}
                            @input=${(e) => {
                              this.numExperts = Number(e.target.value || 0);
                            }}
                            style="
                              width: 100%;
                              box-sizing: border-box;
                              padding: 6px 10px;
                              border-radius: var(--lumo-border-radius-m);
                              border: 1px solid var(--lumo-contrast-20pct);
                              background: var(--lumo-contrast-5pct);
                              color: var(--lumo-body-text-color);
                              font-family: var(--lumo-font-family-monospace, monospace);
                              font-size: var(--lumo-font-size-s);
                            "
                          />
                        </div>
                      </div>

                      <div style="display: flex; gap: var(--lumo-space-m); flex-wrap: wrap;">
                        <label class="compact-toggle">
                          <input
                            id="load-flash-attention-checkbox"
                            type="checkbox"
                            .checked=${this.flashAttention}
                            @change=${(e) => {
                              this.flashAttention = e.target.checked;
                            }}
                          />
                          <span>Flash Attention (<span class="raw-token flag">flash_attention</span>)</span>
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
                          <span>Offload KV Cache to GPU (<span class="raw-token flag">offload_kv_cache_to_gpu</span>)</span>
                        </label>
                      </div>
                    `
                  : html`
                      <div style="font-size: var(--lumo-font-size-xs); color: var(--lumo-secondary-text-color);">
                        Additional engine parameters (<span class="raw-token flag">flash_attention</span>,
                        <span class="raw-token flag">eval_batch_size</span>,
                        <span class="raw-token flag">offload_kv_cache_to_gpu</span>) apply only to GGUF/llama.cpp LLMs.
                      </div>
                    `}

                <div>
                  <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
                    <span style="font-size: var(--lumo-font-size-xxs); font-weight: 600; color: var(--lumo-secondary-text-color); text-transform: uppercase;">
                      REST API Request Preview
                    </span>
                    <button type="button" class="chip-btn" @click=${(e) => this.copyCurl(e)}>
                      Copy curl
                    </button>
                  </div>
                  <pre class="command-box">${this.buildCurlPreview()}</pre>
                </div>

                <div style="display: flex; justify-content: flex-end; gap: var(--lumo-space-s); margin-top: var(--lumo-space-xs);">
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
