import './utils/clipboard.js';
import { LitElement, html } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { SignalWatcher } from '@lit-labs/signals';
import '@vaadin/button';
import '@vaadin/combo-box';
import '@vaadin/icon';
import './components/confirm-dialog.js';
import './components/load-dialog.js';
import './components/loaded-dock.js';
import './components/segmented-control.js';
import './components/service-dialog.js';
import { api } from './services/api.js';
import { copyToClipboard } from './utils/clipboard.js';
import {
  formatBytes,
  formatContextTokens,
  formatDurationSeconds,
  formatIsoShort,
  formatSpeed,
} from './utils/format.js';

const VIEW_OPTIONS = [
  { value: 'inventory', label: 'Models Inventory' },
  { value: 'downloads', label: 'Downloads' },
];

const TYPE_OPTIONS = [
  { value: 'all', label: 'All Types' },
  { value: 'llm', label: 'LLM' },
  { value: 'embedding', label: 'Embedding' },
  { value: 'decision', label: 'Decision' },
];

const ORIGIN_OPTIONS = [
  { value: 'all', label: 'All Origins' },
  { value: 'local_all', label: 'On Host (Local + Hub)' },
  { value: 'remote', label: 'LM Link Peers' },
  { value: 'bundled', label: 'Bundled' },
];

export class LmsManagerApp extends SignalWatcher(LitElement) {
  static properties = {
    activeView: { type: String },
    typeFilter: { type: String },
    originFilter: { type: String },
    loadedOnly: { type: Boolean },
    searchQuery: { type: String },
    pendingDeleteModel: { type: Object },
    downloadInput: { type: String },
    downloadQuant: { type: String },
    hfQuantOptions: { type: Array },
    hfLookupLoading: { type: Boolean },
    hfLookupRepo: { type: String },
    serviceBusy: { type: Boolean },
  };

  createRenderRoot() {
    return this; // Light DOM
  }

  constructor() {
    super();
    this.activeView = 'inventory';
    this.typeFilter = 'all';
    this.originFilter = 'all';
    this.loadedOnly = false;
    this.searchQuery = '';
    this.pendingDeleteModel = null;
    this.downloadInput = '';
    this.downloadQuant = '';
    this.hfQuantOptions = [];
    this.hfLookupLoading = false;
    this.hfLookupRepo = '';
    this.serviceBusy = false;
    this._hfTimer = null;
    this._pollTimer = null;
  }

  async connectedCallback() {
    super.connectedCallback();
    this._onKeydown = this.handleGlobalKeydown.bind(this);
    window.addEventListener('keydown', this._onKeydown);

    await Promise.all([
      api.fetchStatus(),
      api.fetchModels(),
      api.fetchDownloads(),
    ]);

    this._pollTimer = setInterval(() => {
      const activeDl = api.activeDownloadsComputed.get();
      if (activeDl.length > 0 || this.activeView === 'downloads') {
        api.fetchDownloads({ silent: true });
      }
    }, 2500);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._onKeydown) window.removeEventListener('keydown', this._onKeydown);
    if (this._pollTimer) clearInterval(this._pollTimer);
  }

  handleGlobalKeydown(e) {
    const path = e.composedPath();
    const isInput = path.some((el) => {
      if (!el.tagName) return false;
      const t = el.tagName.toLowerCase();
      return (
        t === 'input' ||
        t === 'textarea' ||
        t === 'select' ||
        t === 'vaadin-combo-box' ||
        t === 'vaadin-text-field' ||
        t === 'vaadin-number-field' ||
        t === 'dialog'
      );
    });
    if (isInput || e.metaKey || e.ctrlKey || e.altKey) return;

    if (e.key === '/') {
      e.preventDefault();
      this.activeView = 'inventory';
      requestAnimationFrame(() => {
        this.querySelector('#model-search-input')?.focus();
      });
    } else if (e.key === 'r' || e.key === 'R') {
      e.preventDefault();
      this.refreshAll();
    } else if (e.key === 'd' || e.key === 'D') {
      e.preventDefault();
      this.activeView = 'downloads';
      requestAnimationFrame(() => {
        this.querySelector('#download-model-input')?.focus();
      });
    }
  }

  async refreshAll() {
    await Promise.all([
      api.fetchStatus(),
      api.fetchModels(),
      api.fetchDownloads(),
    ]);
  }

  openLoadDialog(model) {
    const dlg = this.querySelector('load-dialog');
    const defaultCtx = api.statusSignal.get()?.default_context_length || 8192;
    if (dlg) {
      dlg.openForModel(model, defaultCtx);
    }
  }

  async handleLoadSubmit(e) {
    const { payload } = e.detail;
    const dlg = this.querySelector('load-dialog');
    if (dlg) dlg.loading = true;
    try {
      await api.loadModel(payload);
      if (dlg) dlg.close();
    } catch (err) {
      api.showToast(err.message || 'Load failed', 'error');
    } finally {
      if (dlg) dlg.loading = false;
    }
  }

  promptDeleteModel(model) {
    this.pendingDeleteModel = model;
    const dlg = this.querySelector('confirm-dialog#delete-model-dialog');
    if (dlg) {
      dlg.open();
    }
  }

  async confirmDeleteModel() {
    const m = this.pendingDeleteModel;
    if (!m) return;
    this.pendingDeleteModel = null;
    try {
      await api.deleteModel({
        uid: m.uid,
        key: m.key,
        selected_variant: m.selected_variant,
        format: m.format,
        size_bytes: m.size_bytes,
      });
    } catch (err) {
      api.showToast(err.message || 'Failed to delete model', 'error');
    }
  }

  openServiceDialog() {
    const svc = api.statusSignal.get()?.service;
    const dlg = this.querySelector('service-dialog');
    if (dlg && svc) {
      dlg.open(svc);
    }
  }

  async handleServiceAction(e) {
    const { action } = e.detail;
    this.serviceBusy = true;
    try {
      await api.serviceAction(action);
      const nextSvc = api.statusSignal.get()?.service;
      const dlg = this.querySelector('service-dialog');
      if (dlg && nextSvc) {
        dlg.service = nextSvc;
      }
      api.showToast(`Service ${action} succeeded`, 'success');
    } catch (err) {
      api.showToast(err.message || `Service ${action} failed`, 'error');
    } finally {
      this.serviceBusy = false;
    }
  }

  onDownloadInputChange(val) {
    this.downloadInput = val;
    if (this._hfTimer) clearTimeout(this._hfTimer);
    const trimmed = (val || '').trim();
    const looksLikeRepo =
      trimmed.startsWith('http://') ||
      trimmed.startsWith('https://') ||
      (trimmed.split('/').length === 2 && !trimmed.startsWith('/'));

    if (!looksLikeRepo) {
      this.hfQuantOptions = [];
      this.hfLookupRepo = '';
      return;
    }

    this._hfTimer = setTimeout(async () => {
      this.hfLookupLoading = true;
      try {
        const data = await api.fetchHfQuantizations(trimmed);
        this.hfQuantOptions = data.quantizations || [];
        this.hfLookupRepo = data.repo_id || '';
        if (this.hfQuantOptions.length > 0 && !this.downloadQuant) {
          const preferred =
            this.hfQuantOptions.find((q) => q.quantization === 'Q4_K_M') ||
            this.hfQuantOptions.find((q) => q.quantization === 'Q8_0') ||
            this.hfQuantOptions[0];
          if (preferred) {
            this.downloadQuant = preferred.quantization;
          }
        }
      } finally {
        this.hfLookupLoading = false;
      }
    }, 350);
  }

  async submitDownload(e) {
    if (e) e.preventDefault();
    const model = (this.downloadInput || '').trim();
    if (!model) return;
    try {
      await api.startDownload({
        model,
        quantization: (this.downloadQuant || '').trim() || null,
      });
    } catch (err) {
      api.showToast(err.message || 'Download request failed', 'error');
    }
  }

  copyText(text, e) {
    e.preventDefault();
    e.stopPropagation();
    copyToClipboard(text);
    const btn = e.currentTarget;
    const orig = btn.innerText;
    btn.innerText = 'Copied';
    setTimeout(() => {
      btn.innerText = orig;
    }, 1000);
  }

  getFilteredModels(models) {
    const q = (this.searchQuery || '').trim().toLowerCase();
    return (models || []).filter((m) => {
      if (this.typeFilter !== 'all' && m.type !== this.typeFilter) return false;
      if (this.originFilter === 'local_all' && m.origin !== 'local' && m.origin !== 'hub') {
        return false;
      } else if (
        this.originFilter !== 'all' &&
        this.originFilter !== 'local_all' &&
        m.origin !== this.originFilter
      ) {
        return false;
      }
      if (this.loadedOnly && !m.is_loaded) return false;
      if (q) {
        const hay = [
          m.display_name,
          m.key,
          m.publisher,
          m.architecture,
          m.format,
          m.quantization?.name,
          m.device_name,
          m.disk_paths?.concrete_dir,
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  renderOriginBadge(m) {
    if (m.origin === 'local') {
      return html`<span class="state-badge state-running" title="Local model in ~/.lmstudio/models">Local</span>`;
    }
    if (m.origin === 'hub') {
      return html`<span class="state-badge state-hub" title="LM Studio Hub Catalog model">Hub Catalog</span>`;
    }
    if (m.origin === 'bundled') {
      return html`<span class="state-badge state-idle" title="Bundled with LM Studio">Bundled</span>`;
    }
    const peerLabel = m.device_name ? `LM Link • ${m.device_name}` : 'LM Link Peer';
    return html`<span class="state-badge state-remote" title="Hosted on remote LM Link peer">${peerLabel}</span>`;
  }

  renderModelCard(m, busy) {
    const quantName = m.quantization?.name;
    const bits = m.quantization?.bits_per_weight;
    const caps = m.capabilities || {};
    const primaryDiskPath = m.disk_paths?.concrete_dir;
    const hubManifestPath = m.disk_paths?.hub_manifest_dir;
    const isBusyLoad = busy === `load:${m.selected_variant || m.key}` || busy === `load:${m.key}`;
    const isBusyDelete = busy === `delete:${m.uid}`;

    return html`
      <div class="model-card ${m.is_loaded ? 'is-loaded' : ''}" data-model-uid="${m.uid}" data-model-key="${m.key}">
        <div class="model-card-header">
          <div class="model-card-title-group">
            <div class="model-card-title-row">
              <h3 class="model-card-title">${m.display_name}</h3>
              ${this.renderOriginBadge(m)}
              <span class="state-badge state-idle">${m.type}</span>
              ${m.format ? html`<span class="raw-token flag">${m.format.toUpperCase()}</span>` : ''}
              ${quantName
                ? html`<span class="raw-token quant">${quantName}${bits ? ` (${bits}b)` : ''}</span>`
                : ''}
              ${m.params_string ? html`<span class="raw-token">${m.params_string}</span>` : ''}
              <span class="raw-token">${formatBytes(m.size_bytes)}</span>
            </div>

            <div class="model-meta-row">
              <span class="raw-token">${m.selected_variant || m.key}</span>
              ${m.architecture ? html`<span>arch: <strong>${m.architecture}</strong></span>` : ''}
              ${m.max_context_length
                ? html`<span>max ctx: <strong>${formatContextTokens(m.max_context_length)}</strong></span>`
                : ''}
              ${caps.vision ? html`<span class="raw-token branch">Vision</span>` : ''}
              ${caps.trained_for_tool_use ? html`<span class="raw-token branch">Tools</span>` : ''}
              ${caps.reasoning ? html`<span class="raw-token branch">Reasoning</span>` : ''}
              ${(m.variants || []).length > 1
                ? html`<span class="raw-token">${m.variants.length} variants</span>`
                : ''}
            </div>
          </div>

          <div class="model-card-actions">
            ${m.loaded_instances?.map(
              (inst) => html`
                <vaadin-button
                  theme="small error"
                  ?disabled=${busy === `unload:${inst.id}`}
                  @click=${() => api.unloadModel(inst.id)}
                  title="Unload instance ${inst.id}"
                >
                  <vaadin-icon ligature="eject" slot="prefix"></vaadin-icon>
                  Unload
                </vaadin-button>
              `
            )}

            <vaadin-button
              theme="small primary"
              data-action="open-load"
              ?disabled=${isBusyLoad}
              @click=${() => this.openLoadDialog(m)}
            >
              <vaadin-icon ligature="play_arrow" slot="prefix"></vaadin-icon>
              ${m.is_loaded ? 'Load Instance...' : 'Load...'}
            </vaadin-button>

            <vaadin-button
              theme="small error tertiary"
              data-action="delete-model"
              ?disabled=${!m.deletable || isBusyDelete}
              title="${m.deletable
                ? 'Unload and delete model files from local disk'
                : m.origin === 'bundled'
                ? 'Bundled models cannot be deleted'
                : 'Remote LM Link models live on another host'}"
              @click=${() => this.promptDeleteModel(m)}
            >
              <vaadin-icon ligature="delete"></vaadin-icon>
            </vaadin-button>
          </div>
        </div>

        ${(m.loaded_instances || []).length > 0
          ? html`
              <div style="display: flex; flex-wrap: wrap; gap: 6px; padding-top: 2px;">
                ${m.loaded_instances.map((inst) => {
                  const cfg = inst.config || {};
                  return html`
                    <div
                      style="display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px; border-radius: var(--lumo-border-radius-s); background: var(--lumo-success-color-10pct); border: 1px solid var(--lumo-success-color-50pct); font-size: var(--lumo-font-size-xxs);"
                    >
                      <span class="status-dot dot-ready"></span>
                      <span style="font-family: var(--lumo-font-family-monospace, monospace); font-weight: 600;">
                        Loaded: ${inst.id}
                      </span>
                      ${cfg.context_length
                        ? html`<span class="raw-token">ctx ${formatContextTokens(cfg.context_length)}</span>`
                        : ''}
                      ${cfg.eval_batch_size
                        ? html`<span class="raw-token">batch ${cfg.eval_batch_size}</span>`
                        : ''}
                      ${cfg.flash_attention ? html`<span class="raw-token">flash_attn</span>` : ''}
                      ${cfg.offload_kv_cache_to_gpu ? html`<span class="raw-token">kv_gpu</span>` : ''}
                      ${inst.remaining_ttl_seconds !== undefined && inst.remaining_ttl_seconds !== null
                        ? html`<span class="raw-token">TTL ${formatDurationSeconds(inst.remaining_ttl_seconds)}</span>`
                        : ''}
                    </div>
                  `;
                })}
              </div>
            `
          : ''}

        ${primaryDiskPath
          ? html`
              <div class="model-path-row">
                <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap; min-width: 0;">
                  <span>Disk:</span>
                  <span class="raw-token path">${primaryDiskPath}</span>
                  ${hubManifestPath && hubManifestPath !== primaryDiskPath
                    ? html`
                        <span>+ Hub Manifest:</span>
                        <span class="raw-token path">${hubManifestPath}</span>
                      `
                    : ''}
                </div>
                <button
                  type="button"
                  class="chip-btn"
                  @click=${(e) => this.copyText(primaryDiskPath, e)}
                  title="Copy model directory path"
                >
                  Copy Path
                </button>
              </div>
            `
          : ''}
      </div>
    `;
  }

  renderInventoryView(models, isLoading, busy) {
    const filtered = this.getFilteredModels(models);

    return html`
      <div class="filter-toolbar">
        <div class="filter-toolbar-left">
          <segmented-control
            id="type-filter-control"
            .options=${TYPE_OPTIONS}
            .value=${this.typeFilter}
            @change=${(e) => {
              this.typeFilter = e.detail.value;
            }}
          ></segmented-control>

          <segmented-control
            id="origin-filter-control"
            .options=${ORIGIN_OPTIONS}
            .value=${this.originFilter}
            @change=${(e) => {
              this.originFilter = e.detail.value;
            }}
          ></segmented-control>

          <label class="compact-toggle">
            <input
              id="loaded-only-checkbox"
              type="checkbox"
              .checked=${this.loadedOnly}
              @change=${(e) => {
                this.loadedOnly = e.target.checked;
              }}
            />
            <span>Loaded only</span>
          </label>
        </div>

        <div class="filter-toolbar-right">
          <div style="position: relative; display: inline-flex; align-items: center;">
            <input
              id="model-search-input"
              type="search"
              placeholder="Filter models, quants, peers, paths... (/)"
              .value=${this.searchQuery}
              @input=${(e) => {
                this.searchQuery = e.target.value;
              }}
              style="
                width: 260px;
                height: 30px;
                padding: 0 10px;
                border-radius: var(--lumo-border-radius-m);
                border: 1px solid var(--lumo-contrast-20pct);
                background: var(--lumo-contrast-5pct);
                color: var(--lumo-body-text-color);
                font-size: var(--lumo-font-size-xs);
                box-sizing: border-box;
              "
            />
          </div>
          <span style="font-size: var(--lumo-font-size-xs); color: var(--lumo-secondary-text-color);">
            Showing <strong>${filtered.length}</strong> of ${models.length}
          </span>
        </div>
      </div>

      <div class="main-scroll-container">
        <div class="content-max-width">
          ${isLoading
            ? html`
                <div class="panel-card" style="display: flex; align-items: center; justify-content: center; padding: var(--lumo-space-xl);">
                  <div class="lumo-inline-loading">
                    <span class="lumo-loader-spinner"></span>
                    <span>Loading models from LM Studio REST API...</span>
                  </div>
                </div>
              `
            : filtered.length === 0
            ? html`
                <div class="panel-card" style="text-align: center; color: var(--lumo-secondary-text-color); padding: var(--lumo-space-xl);">
                  No models match the active filters.
                </div>
              `
            : html`
                <div class="models-grid">
                  ${repeat(
                    filtered,
                    (m) => m.uid,
                    (m) => this.renderModelCard(m, busy)
                  )}
                </div>
              `}
        </div>
      </div>
    `;
  }

  renderDownloadsView(status, downloads, busy) {
    const lmUrl = status?.lmstudio_url || 'http://localhost:1234';
    const dlPayload = {
      model: (this.downloadInput || '<catalog-id-or-hf-url>').trim(),
      ...(this.downloadQuant ? { quantization: this.downloadQuant } : {}),
    };
    const curlPreview = `curl ${lmUrl}/api/v1/models/download \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify(dlPayload)}'`;

    return html`
      <div class="main-scroll-container">
        <div class="content-max-width">
          <div class="panel-card">
            <div class="panel-header">
              <h2 class="panel-title">Pull Model via LM Studio REST API</h2>
              <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                <span style="font-size: var(--lumo-font-size-xxs); color: var(--lumo-secondary-text-color); align-self: center;">
                  Examples:
                </span>
                ${[
                  { label: 'ibm/granite-4-micro', model: 'ibm/granite-4-micro', quant: '' },
                  { label: 'openai/gpt-oss-20b', model: 'openai/gpt-oss-20b', quant: '' },
                  {
                    label: 'HF: Qwen2.5-7B-Instruct-GGUF',
                    model: 'https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF',
                    quant: 'Q4_K_M',
                  },
                ].map(
                  (ex) => html`
                    <button
                      type="button"
                      class="chip-btn"
                      @click=${() => {
                        this.downloadQuant = ex.quant;
                        this.onDownloadInputChange(ex.model);
                      }}
                    >
                      ${ex.label}
                    </button>
                  `
                )}
              </div>
            </div>

            <form @submit=${(e) => this.submitDownload(e)} style="display: flex; flex-direction: column; gap: var(--lumo-space-m);">
              <div class="form-grid">
                <div style="grid-column: span 2;">
                  <label
                    for="download-model-input"
                    style="display: block; font-size: var(--lumo-font-size-xs); font-weight: 600; color: var(--lumo-secondary-text-color); margin-bottom: 4px;"
                  >
                    LM Studio Catalog Identifier or Hugging Face Repository URL
                  </label>
                  <input
                    id="download-model-input"
                    type="text"
                    placeholder="e.g. ibm/granite-4-micro or https://huggingface.co/lmstudio-community/..."
                    .value=${this.downloadInput}
                    @input=${(e) => this.onDownloadInputChange(e.target.value)}
                    style="
                      width: 100%;
                      box-sizing: border-box;
                      padding: 8px 10px;
                      border-radius: var(--lumo-border-radius-m);
                      border: 1px solid var(--lumo-contrast-20pct);
                      background: var(--lumo-base-color);
                      color: var(--lumo-body-text-color);
                      font-family: var(--lumo-font-family-monospace, monospace);
                      font-size: var(--lumo-font-size-s);
                    "
                  />
                </div>

                <div>
                  <label
                    for="download-quant-input"
                    style="display: flex; align-items: center; justify-content: space-between; font-size: var(--lumo-font-size-xs); font-weight: 600; color: var(--lumo-secondary-text-color); margin-bottom: 4px;"
                  >
                    <span>Quantization (Optional for HF)</span>
                    ${this.hfLookupLoading
                      ? html`<span class="lumo-loader-spinner" style="width: 10px; height: 10px;"></span>`
                      : ''}
                  </label>
                  ${this.hfQuantOptions.length > 0
                    ? html`
                        <select
                          id="download-quant-select"
                          .value=${this.downloadQuant}
                          @change=${(e) => {
                            this.downloadQuant = e.target.value;
                          }}
                          style="
                            width: 100%;
                            box-sizing: border-box;
                            padding: 8px 10px;
                            border-radius: var(--lumo-border-radius-m);
                            border: 1px solid var(--lumo-contrast-20pct);
                            background: var(--lumo-base-color);
                            color: var(--lumo-body-text-color);
                            font-family: var(--lumo-font-family-monospace, monospace);
                            font-size: var(--lumo-font-size-s);
                          "
                        >
                          <option value="">(Default / None)</option>
                          ${this.hfQuantOptions.map(
                            (q) => html`
                              <option value="${q.quantization}" ?selected=${this.downloadQuant === q.quantization}>
                                ${q.quantization} — ${q.size_bytes ? formatBytes(q.size_bytes) : q.filename}
                              </option>
                            `
                          )}
                        </select>
                      `
                    : html`
                        <input
                          id="download-quant-input"
                          type="text"
                          placeholder="e.g. Q4_K_M, Q8_0"
                          .value=${this.downloadQuant}
                          @input=${(e) => {
                            this.downloadQuant = e.target.value;
                          }}
                          style="
                            width: 100%;
                            box-sizing: border-box;
                            padding: 8px 10px;
                            border-radius: var(--lumo-border-radius-m);
                            border: 1px solid var(--lumo-contrast-20pct);
                            background: var(--lumo-base-color);
                            color: var(--lumo-body-text-color);
                            font-family: var(--lumo-font-family-monospace, monospace);
                            font-size: var(--lumo-font-size-s);
                          "
                        />
                      `}
                </div>
              </div>

              <div>
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
                  <span style="font-size: var(--lumo-font-size-xxs); font-weight: 600; color: var(--lumo-secondary-text-color); text-transform: uppercase;">
                    REST API Request Preview
                  </span>
                  <button type="button" class="chip-btn" @click=${(e) => this.copyText(curlPreview, e)}>
                    Copy curl
                  </button>
                </div>
                <pre class="command-box">${curlPreview}</pre>
              </div>

              <div style="display: flex; justify-content: flex-end;">
                <vaadin-button
                  id="start-download-btn"
                  theme="primary"
                  ?disabled=${!this.downloadInput.trim() || busy === 'download'}
                  @click=${(e) => this.submitDownload(e)}
                >
                  <vaadin-icon ligature="download" slot="prefix"></vaadin-icon>
                  ${busy === 'download' ? 'Starting Download...' : 'Download Model'}
                </vaadin-button>
              </div>
            </form>
          </div>

          <div class="panel-card">
            <div class="panel-header">
              <h2 class="panel-title">
                Model Download Jobs (${downloads.length})
              </h2>
              <span style="font-size: var(--lumo-font-size-xxs); color: var(--lumo-secondary-text-color);">
                Source: <span class="raw-token path">~/.lmstudio/.internal/download-jobs-info.json</span> + <span class="raw-token flag">/api/v1/models/download/status/:job_id</span>
              </span>
            </div>

            ${downloads.length === 0
              ? html`
                  <div style="color: var(--lumo-secondary-text-color); font-size: var(--lumo-font-size-s); padding: var(--lumo-space-m) 0;">
                    No model download jobs found in LM Studio history.
                  </div>
                `
              : html`
                  <div style="display: flex; flex-direction: column; gap: var(--lumo-space-s);">
                    ${repeat(
                      downloads,
                      (j) => j.job_id,
                      (j) => {
                        const isDone = j.status === 'completed';
                        const isFail = j.status === 'failed';
                        const isActive = j.status === 'downloading' || j.status === 'paused';
                        const badgeClass = isDone
                          ? 'state-running'
                          : isFail
                          ? 'state-failed'
                          : isActive
                          ? 'state-building'
                          : 'state-idle';

                        return html`
                          <div class="surface-card" data-job-id="${j.job_id}">
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: var(--lumo-space-s); flex-wrap: wrap; margin-bottom: 6px;">
                              <div style="display: flex; align-items: center; gap: var(--lumo-space-s); flex-wrap: wrap;">
                                <span style="font-weight: 600; font-size: var(--lumo-font-size-s);">${j.model_id}</span>
                                <span class="state-badge ${badgeClass}">${j.status}</span>
                                <span class="raw-token">${j.job_id}</span>
                              </div>
                              <div style="display: flex; align-items: center; gap: var(--lumo-space-s); font-size: var(--lumo-font-size-xs); color: var(--lumo-secondary-text-color); font-family: var(--lumo-font-family-monospace, monospace);">
                                ${j.bytes_per_second
                                  ? html`<span>${formatSpeed(j.bytes_per_second)}</span>`
                                  : ''}
                                ${j.total_size_bytes
                                  ? html`<span>${formatBytes(j.downloaded_bytes || 0)} / ${formatBytes(j.total_size_bytes)} (${j.progress_pct}%)</span>`
                                  : ''}
                              </div>
                            </div>

                            <div class="download-progress-track">
                              <div
                                class="download-progress-fill ${isDone ? 'completed' : isFail ? 'failed' : ''}"
                                style="width: ${j.progress_pct || 0}%;"
                              ></div>
                            </div>

                            <div style="display: flex; align-items: center; justify-content: space-between; gap: var(--lumo-space-s); flex-wrap: wrap; margin-top: 6px; font-size: var(--lumo-font-size-xxs); color: var(--lumo-tertiary-text-color);">
                              <div>
                                ${j.target_path
                                  ? html`Target: <span class="raw-token path">${j.target_path}</span>`
                                  : ''}
                                ${j.error_message
                                  ? html`<span style="color: var(--lumo-error-text-color); margin-left: 6px;">Error: ${j.error_message}</span>`
                                  : ''}
                              </div>
                              <div>
                                ${j.completed_at
                                  ? html`Completed ${formatIsoShort(j.completed_at)}`
                                  : j.started_at
                                  ? html`Started ${formatIsoShort(j.started_at)}`
                                  : ''}
                              </div>
                            </div>
                          </div>
                        `;
                      }
                    )}
                  </div>
                `}
          </div>
        </div>
      </div>
    `;
  }

  render() {
    const status = api.statusSignal.get();
    const models = api.modelsSignal.get() || [];
    const modelsLoading = api.modelsLoadingSignal.get();
    const downloads = api.downloadsSignal.get() || [];
    const activeDownloads = api.activeDownloadsComputed.get();
    const busy = api.busyActionSignal.get();
    const toast = api.toastSignal.get();

    const localModels = models.filter((m) => m.origin === 'local' || m.origin === 'hub');
    const localBytes = localModels.reduce((acc, m) => acc + (m.size_bytes || 0), 0);
    const svc = status?.service;

    const viewOptionsWithCounts = VIEW_OPTIONS.map((v) =>
      v.value === 'inventory'
        ? { ...v, label: `Inventory (${models.length})` }
        : {
            ...v,
            label:
              activeDownloads.length > 0
                ? `Downloads (${activeDownloads.length} active)`
                : `Downloads (${downloads.length})`,
          }
    );

    return html`
      <div class="app-root-container">
        <header class="app-header">
          <div class="header-left">
            <h1 class="brand-title">
              <vaadin-icon ligature="hub" style="color: var(--lumo-primary-color); width: 20px; height: 20px;"></vaadin-icon>
              <span>LM Studio Manager</span>
            </h1>
            <span class="breadcrumb-sep">/</span>

            <span
              class="state-badge ${status.connected ? 'state-running' : 'state-failed'}"
              title="${status.error || status.lmstudio_url}"
            >
              <span class="status-dot ${status.connected ? 'dot-ready' : 'dot-offline'}"></span>
              <span>${status.connected ? status.lmstudio_url : 'LM Studio Offline'}</span>
            </span>

            <span class="raw-token" title="Local models disk footprint in ${status.downloads_folder}">
              ${localModels.length} local • ${formatBytes(localBytes)}
            </span>

            ${svc
              ? html`
                  <button
                    id="open-service-dialog-btn"
                    type="button"
                    class="chip-btn"
                    @click=${() => this.openServiceDialog()}
                    title="Manage background host service (${svc.service_manager})"
                  >
                    <span
                      class="status-dot ${svc.running ? 'dot-ready' : svc.installed ? 'dot-starting' : 'dot-offline'}"
                      style="margin-right: 5px;"
                    ></span>
                    <span>Service: ${svc.service_manager}</span>
                  </button>
                `
              : ''}
          </div>

          <div class="header-right">
            <segmented-control
              id="view-switcher-control"
              .options=${viewOptionsWithCounts}
              .value=${this.activeView}
              @change=${(e) => {
                this.activeView = e.detail.value;
              }}
            ></segmented-control>

            <vaadin-button
              id="pull-model-header-btn"
              theme="small ${this.activeView === 'downloads' ? 'contrast' : ''}"
              @click=${() => {
                this.activeView = 'downloads';
                requestAnimationFrame(() => {
                  this.querySelector('#download-model-input')?.focus();
                });
              }}
            >
              <vaadin-icon ligature="download" slot="prefix"></vaadin-icon>
              <span>Pull Model</span>
              <kbd class="btn-kbd">D</kbd>
            </vaadin-button>

            <vaadin-button
              id="refresh-models-btn"
              theme="small"
              @click=${() => this.refreshAll()}
              title="Refresh models & downloads (R)"
            >
              <vaadin-icon ligature="refresh" slot="prefix"></vaadin-icon>
              <span>Refresh</span>
              <kbd class="btn-kbd">R</kbd>
            </vaadin-button>
          </div>
        </header>

        <div class="surfaces-subheader-wrapper">
          <loaded-dock layout="bar"></loaded-dock>
        </div>

        <div class="workspace-viewport">
          <main class="content-primary">
            ${this.activeView === 'downloads'
              ? this.renderDownloadsView(status, downloads, busy)
              : this.renderInventoryView(models, modelsLoading, busy)}
          </main>

          <aside class="surfaces-sidebar-wrapper">
            <loaded-dock layout="sidebar"></loaded-dock>
          </aside>
        </div>

        <footer class="app-footer">
          <div>
            Downloads Dir: <span class="raw-token path">${status.downloads_folder}</span>
            &bull; Default Context: <span class="raw-token">${formatContextTokens(status.default_context_length)}</span>
          </div>
          <div>
            Shortcuts: <kbd>/</kbd> Search &bull; <kbd>D</kbd> Pull Model &bull; <kbd>R</kbd> Refresh
          </div>
        </footer>

        <load-dialog
          .lmstudioUrl=${status.lmstudio_url || 'http://localhost:1234'}
          @submit-load=${(e) => this.handleLoadSubmit(e)}
        ></load-dialog>

        <service-dialog
          .busy=${this.serviceBusy}
          @service-action=${(e) => this.handleServiceAction(e)}
        ></service-dialog>

        <confirm-dialog
          id="delete-model-dialog"
          header="Delete Local Model from Disk"
          .message=${this.pendingDeleteModel
            ? `Are you sure you want to unload (if active) and permanently delete '${
                this.pendingDeleteModel.display_name
              }' (${formatBytes(this.pendingDeleteModel.size_bytes)}) from this host?`
            : ''}
          .paths=${this.pendingDeleteModel?.disk_paths?.delete_targets || []}
          confirmText="Delete Model"
          confirmTheme="primary error"
          @confirm=${() => this.confirmDeleteModel()}
          @cancel=${() => {
            this.pendingDeleteModel = null;
          }}
        >
          <vaadin-icon
            slot="icon"
            ligature="warning"
            style="color: var(--lumo-error-color);"
          ></vaadin-icon>
        </confirm-dialog>

        ${toast
          ? html`
              <div class="toast-banner toast-${toast.type}" role="status">
                <vaadin-icon
                  ligature="${toast.type === 'error' ? 'error' : toast.type === 'success' ? 'check_circle' : 'info'}"
                ></vaadin-icon>
                <span>${toast.message}</span>
              </div>
            `
          : ''}
      </div>
    `;
  }
}

customElements.define('lms-manager-app', LmsManagerApp);
