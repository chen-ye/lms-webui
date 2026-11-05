import './utils/clipboard.js';
import { LitElement, html } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { SignalWatcher } from '@lit-labs/signals';
import '@vaadin/button';
import '@vaadin/icon';
import './components/confirm-dialog.js';
import './components/load-dialog.js';
import './components/segmented-control.js';
import './components/service-dialog.js';
import { api } from './services/api.js';
import {
  formatBytes,
  formatContextTokens,
  formatDurationSeconds,
  formatIsoShort,
  formatSpeed,
} from './utils/format.js';

const VIEW_OPTIONS = [
  { value: 'inventory', label: 'Installed' },
  { value: 'downloads', label: 'Discover & Download' },
];

const FILTER_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'loaded', label: 'Loaded' },
  { value: 'host', label: 'On Host' },
  { value: 'remote', label: 'LM Link' },
  { value: 'embedding', label: 'Embeddings' },
];

const DISCOVER_SOURCE_OPTIONS = [
  { value: 'catalog', label: 'LM Studio Catalog' },
  { value: 'hf', label: 'Hugging Face' },
];

const HF_FORMAT_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'gguf', label: 'GGUF' },
  { value: 'mlx', label: 'MLX' },
];

export class LmsManagerApp extends SignalWatcher(LitElement) {
  static properties = {
    activeView: { type: String },
    activeFilter: { type: String },
    searchQuery: { type: String },
    pendingDeleteModel: { type: Object },
    downloadInput: { type: String },
    downloadQuant: { type: String },
    hfQuantOptions: { type: Array },
    hfLookupLoading: { type: Boolean },
    discoverSource: { type: String },
    discoverQuery: { type: String },
    hfFormatFilter: { type: String },
    expandedCatalogSlug: { type: String },
    catalogVariantsMap: { type: Object },
    catalogVariantsLoading: { type: String },
    expandedHfRepo: { type: String },
    hfRepoQuantsMap: { type: Object },
    hfRepoQuantsLoading: { type: String },
    serviceBusy: { type: Boolean },
  };

  createRenderRoot() {
    return this;
  }

  constructor() {
    super();
    this.activeView = 'inventory';
    this.activeFilter = 'all';
    this.searchQuery = '';
    this.pendingDeleteModel = null;

    this.downloadInput = '';
    this.downloadQuant = '';
    this.hfQuantOptions = [];
    this.hfLookupLoading = false;

    this.discoverSource = 'catalog';
    this.discoverQuery = '';
    this.hfFormatFilter = 'all';
    this.expandedCatalogSlug = '';
    this.catalogVariantsMap = {};
    this.catalogVariantsLoading = '';
    this.expandedHfRepo = '';
    this.hfRepoQuantsMap = {};
    this.hfRepoQuantsLoading = '';

    this.serviceBusy = false;
    this._hfTimer = null;
    this._discoverTimer = null;
    this._pollTimer = null;
  }

  async connectedCallback() {
    super.connectedCallback();
    await Promise.all([
      api.fetchStatus(),
      api.fetchModels(),
      api.fetchDownloads(),
      api.fetchCatalog(''),
    ]);

    this._pollTimer = setInterval(() => {
      const activeDl = api.activeDownloadsComputed.get();
      if (activeDl.length > 0) {
        api.fetchDownloads({ silent: true });
      }
    }, 2500);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._pollTimer) clearInterval(this._pollTimer);
  }

  async refreshAll() {
    await Promise.all([
      api.fetchStatus(),
      api.fetchModels(),
      api.fetchDownloads(),
    ]);
  }

  switchView(nextView) {
    this.activeView = nextView;
    if (nextView === 'downloads') {
      if (this.discoverSource === 'catalog' && api.catalogFamiliesSignal.get().length === 0) {
        api.fetchCatalog(this.discoverQuery);
      } else if (this.discoverSource === 'hf' && api.hfModelsSignal.get().length === 0) {
        api.searchHfModels(this.discoverQuery, this.hfFormatFilter);
      }
    }
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
      return;
    }

    this._hfTimer = setTimeout(async () => {
      this.hfLookupLoading = true;
      try {
        const data = await api.fetchHfQuantizations(trimmed);
        this.hfQuantOptions = data.quantizations || [];
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
    }, 300);
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

  async quickDownload(model, quantization = null) {
    try {
      await api.startDownload({ model, quantization });
    } catch (err) {
      api.showToast(err.message || 'Download request failed', 'error');
    }
  }

  onDiscoverSourceChange(source) {
    this.discoverSource = source;
    if (source === 'catalog') {
      api.fetchCatalog(this.discoverQuery);
    } else {
      api.searchHfModels(this.discoverQuery, this.hfFormatFilter);
    }
  }

  onDiscoverQueryInput(val) {
    this.discoverQuery = val;
    if (this._discoverTimer) clearTimeout(this._discoverTimer);
    this._discoverTimer = setTimeout(() => {
      if (this.discoverSource === 'catalog') {
        api.fetchCatalog(this.discoverQuery);
      } else {
        api.searchHfModels(this.discoverQuery, this.hfFormatFilter);
      }
    }, 300);
  }

  onHfFormatChange(fmt) {
    this.hfFormatFilter = fmt;
    api.searchHfModels(this.discoverQuery, fmt);
  }

  async toggleCatalogFamily(slug) {
    if (this.expandedCatalogSlug === slug) {
      this.expandedCatalogSlug = '';
      return;
    }
    this.expandedCatalogSlug = slug;
    if (!this.catalogVariantsMap[slug]) {
      this.catalogVariantsLoading = slug;
      try {
        const data = await api.fetchCatalogFamily(slug);
        this.catalogVariantsMap = {
          ...this.catalogVariantsMap,
          [slug]: data.variants || [],
        };
      } finally {
        this.catalogVariantsLoading = '';
      }
    }
  }

  async toggleHfRepoQuants(repoId) {
    if (this.expandedHfRepo === repoId) {
      this.expandedHfRepo = '';
      return;
    }
    this.expandedHfRepo = repoId;
    if (!this.hfRepoQuantsMap[repoId]) {
      this.hfRepoQuantsLoading = repoId;
      try {
        const data = await api.fetchHfQuantizations(repoId);
        this.hfRepoQuantsMap = {
          ...this.hfRepoQuantsMap,
          [repoId]: data.quantizations || [],
        };
      } finally {
        this.hfRepoQuantsLoading = '';
      }
    }
  }

  getFilteredModels(models) {
    const q = (this.searchQuery || '').trim().toLowerCase();
    const filtered = (models || []).filter((m) => {
      if (this.activeFilter === 'loaded' && !m.is_loaded) return false;
      if (this.activeFilter === 'host' && m.origin !== 'local' && m.origin !== 'hub') return false;
      if (this.activeFilter === 'remote' && m.origin !== 'remote') return false;
      if (this.activeFilter === 'embedding' && m.type !== 'embedding') return false;

      if (q) {
        const hay = [
          m.display_name,
          m.key,
          m.publisher,
          m.architecture,
          m.format,
          m.quantization?.name,
          m.device_name,
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    // Keep loaded models at the top of the list so no separate sidebar is needed
    return [...filtered].sort((a, b) => Number(b.is_loaded) - Number(a.is_loaded));
  }

  renderOriginBadge(m) {
    if (m.origin === 'local') {
      return html`<span class="state-badge state-running">Local</span>`;
    }
    if (m.origin === 'hub') {
      return html`<span class="state-badge state-running">Hub</span>`;
    }
    if (m.origin === 'bundled') {
      return html`<span class="state-badge state-idle">Bundled</span>`;
    }
    const peerLabel = m.device_name ? `LM Link · ${m.device_name}` : 'LM Link';
    return html`<span class="state-badge state-idle">${peerLabel}</span>`;
  }

  renderModelRow(m, busy) {
    const quantName = m.quantization?.name;
    const caps = m.capabilities || {};
    const isBusyLoad = busy === `load:${m.selected_variant || m.key}` || busy === `load:${m.key}`;
    const isBusyDelete = busy === `delete:${m.uid}`;
    const capLabels = [
      caps.vision ? 'Vision' : null,
      caps.trained_for_tool_use ? 'Tools' : null,
      caps.reasoning ? 'Reasoning' : null,
    ].filter(Boolean);

    return html`
      <div
        class="model-card ${m.is_loaded ? 'is-loaded' : ''}"
        data-model-uid="${m.uid}"
        data-model-key="${m.key}"
      >
        <div class="row-main">
          <div class="row-title-line">
            <span
              class="status-dot ${m.is_loaded ? 'dot-ready' : 'dot-offline'}"
              title="${m.is_loaded ? 'Loaded in memory' : 'Not loaded'}"
            ></span>
            <h3 class="row-title">${m.display_name}</h3>
            ${this.renderOriginBadge(m)}
            ${m.format
              ? html`<span class="raw-token">${m.format.toUpperCase()}${quantName ? ` · ${quantName}` : ''}</span>`
              : quantName
              ? html`<span class="raw-token">${quantName}</span>`
              : ''}
            ${m.params_string ? html`<span class="raw-token">${m.params_string}</span>` : ''}
            <span class="raw-token">${formatBytes(m.size_bytes)}</span>

            ${(m.loaded_instances || []).map((inst) => {
              const cfg = inst.config || {};
              return html`
                <span class="state-badge state-running">
                  Loaded
                  ${cfg.context_length ? `· ${formatContextTokens(cfg.context_length)} ctx` : ''}
                  ${cfg.flash_attention ? '· FA' : ''}
                  ${inst.remaining_ttl_seconds !== undefined && inst.remaining_ttl_seconds !== null
                    ? `· TTL ${formatDurationSeconds(inst.remaining_ttl_seconds)}`
                    : ''}
                </span>
              `;
            })}
          </div>

          <div class="row-meta-line">
            <span class="raw-token">${m.selected_variant || m.key}</span>
            ${m.type !== 'llm' ? html`<span>${m.type}</span>` : ''}
            ${m.max_context_length ? html`<span>${formatContextTokens(m.max_context_length)} max ctx</span>` : ''}
            ${capLabels.length > 0 ? html`<span>${capLabels.join(' · ')}</span>` : ''}

            ${m.catalog_url
              ? html`
                  <a href="${m.catalog_url}" target="_blank" rel="noreferrer" class="ext-link">
                    <span>Catalog</span>
                    <vaadin-icon ligature="open_in_new"></vaadin-icon>
                  </a>
                `
              : ''}
            ${m.hf_url
              ? html`
                  <a href="${m.hf_url}" target="_blank" rel="noreferrer" class="ext-link">
                    <span>Hugging Face</span>
                    <vaadin-icon ligature="open_in_new"></vaadin-icon>
                  </a>
                `
              : ''}
          </div>
        </div>

        <div class="row-actions">
          ${m.loaded_instances?.map(
            (inst) => html`
              <vaadin-button
                theme="small error tertiary"
                ?disabled=${busy === `unload:${inst.id}`}
                @click=${() => api.unloadModel(inst.id)}
                title="Unload ${inst.id}"
              >
                Unload
              </vaadin-button>
            `
          )}

          <vaadin-button
            theme="small ${m.is_loaded ? 'tertiary' : 'primary'}"
            data-action="open-load"
            ?disabled=${isBusyLoad}
            @click=${() => this.openLoadDialog(m)}
          >
            ${m.is_loaded ? 'Reload...' : 'Load...'}
          </vaadin-button>

          <button
            type="button"
            class="icon-btn"
            data-action="delete-model"
            ?disabled=${!m.deletable || isBusyDelete}
            title="${m.deletable
              ? `Delete from disk (${m.disk_paths?.concrete_dir || ''})`
              : m.origin === 'bundled'
              ? 'Bundled model cannot be deleted'
              : 'Remote LM Link model lives on another host'}"
            aria-label="Delete ${m.display_name}"
            @click=${() => this.promptDeleteModel(m)}
          >
            <vaadin-icon ligature="delete" style="width: 18px; height: 18px;"></vaadin-icon>
          </button>
        </div>
      </div>
    `;
  }

  renderInventoryView(models, isLoading, busy) {
    const filtered = this.getFilteredModels(models);
    const loadedInstances = api.loadedInstancesComputed.get();

    return html`
      <div class="main-scroll-container">
        <div class="content-max-width">
          <div class="toolbar-row">
            <div class="toolbar-left">
              <input
                id="model-search-input"
                class="text-input"
                type="search"
                placeholder="Filter installed models..."
                .value=${this.searchQuery}
                @input=${(e) => {
                  this.searchQuery = e.target.value;
                }}
                style="width: 240px;"
              />

              <segmented-control
                id="filter-control"
                .options=${FILTER_OPTIONS}
                .value=${this.activeFilter}
                @change=${(e) => {
                  this.activeFilter = e.detail.value;
                }}
              ></segmented-control>
            </div>

            <div class="toolbar-right">
              ${loadedInstances.length > 0
                ? html`
                    <vaadin-button
                      theme="small contrast tertiary"
                      ?disabled=${busy === 'unload-all'}
                      @click=${() => api.unloadAllModels()}
                    >
                      Unload All (${loadedInstances.length})
                    </vaadin-button>
                  `
                : ''}
            </div>
          </div>

          ${isLoading
            ? html`
                <div class="list-surface" style="padding: var(--lumo-space-xl); text-align: center;">
                  <div class="lumo-inline-loading">
                    <span class="lumo-loader-spinner"></span>
                    <span>Loading models...</span>
                  </div>
                </div>
              `
            : filtered.length === 0
            ? html`
                <div class="list-surface" style="padding: var(--lumo-space-xl); text-align: center; color: var(--lumo-secondary-text-color);">
                  No models match the current filter.
                </div>
              `
            : html`
                <div class="list-surface">
                  ${repeat(
                    filtered,
                    (m) => m.uid,
                    (m) => this.renderModelRow(m, busy)
                  )}
                </div>
              `}
        </div>
      </div>
    `;
  }

  renderCatalogBrowser(installedKeys, busy) {
    const families = api.catalogFamiliesSignal.get() || [];
    const loading = api.catalogLoadingSignal.get();

    if (loading && families.length === 0) {
      return html`
        <div class="list-surface" style="padding: var(--lumo-space-xl); text-align: center;">
          <div class="lumo-inline-loading">
            <span class="lumo-loader-spinner"></span>
            <span>Loading LM Studio Model Catalog...</span>
          </div>
        </div>
      `;
    }

    if (families.length === 0) {
      return html`
        <div class="list-surface" style="padding: var(--lumo-space-xl); text-align: center; color: var(--lumo-secondary-text-color);">
          No matching model families found in the LM Studio Catalog.
        </div>
      `;
    }

    return html`
      <div class="list-surface">
        ${families.map((fam) => {
          const isExpanded = this.expandedCatalogSlug === fam.slug;
          const variants = this.catalogVariantsMap[fam.slug] || [];
          const isVarLoading = this.catalogVariantsLoading === fam.slug;

          return html`
            <div class="list-row" data-catalog-slug="${fam.slug}">
              <div class="row-main">
                <div class="row-title-line">
                  <h3 class="row-title">${fam.name}</h3>
                  ${(fam.params || []).map((p) => html`<span class="raw-token">${p}</span>`)}
                  ${(fam.capabilities || []).map(
                    (c) => html`<span class="state-badge state-idle">${c}</span>`
                  )}
                  <a href="${fam.url}" target="_blank" rel="noreferrer" class="ext-link">
                    <span>lmstudio.ai</span>
                    <vaadin-icon ligature="open_in_new"></vaadin-icon>
                  </a>
                </div>
                ${fam.description
                  ? html`<div class="row-meta-line">${fam.description}</div>`
                  : ''}
              </div>

              <div class="row-actions">
                <vaadin-button
                  theme="small ${isExpanded ? 'contrast' : 'tertiary'}"
                  @click=${() => this.toggleCatalogFamily(fam.slug)}
                >
                  ${isExpanded ? 'Hide Variants' : 'Choose Size...'}
                </vaadin-button>
              </div>
            </div>

            ${isExpanded
              ? html`
                  <div class="row-variants-drawer">
                    ${isVarLoading
                      ? html`
                          <div class="lumo-inline-loading">
                            <span class="lumo-loader-spinner"></span>
                            <span>Loading downloadable variants...</span>
                          </div>
                        `
                      : variants.length === 0
                      ? html`
                          <div class="variant-item-row">
                            <span style="color: var(--lumo-secondary-text-color);">
                              Visit <a href="${fam.url}" target="_blank" rel="noreferrer" class="ext-link">${fam.url}</a> for model identifiers.
                            </span>
                          </div>
                        `
                      : variants.map((v) => {
                          const isInstalled = installedKeys.has(v.model_id.toLowerCase());
                          const isDownloading = busy === `download:${v.model_id}`;
                          return html`
                            <div class="variant-item-row">
                              <div class="row-title-line">
                                <span class="raw-token">${v.model_id}</span>
                                ${v.size ? html`<span style="color: var(--lumo-secondary-text-color);">${v.size}</span>` : ''}
                                <a href="${v.url}" target="_blank" rel="noreferrer" class="ext-link">
                                  <span>Details</span>
                                  <vaadin-icon ligature="open_in_new"></vaadin-icon>
                                </a>
                              </div>
                              <div>
                                ${isInstalled
                                  ? html`<span class="state-badge state-running">Installed</span>`
                                  : html`
                                      <vaadin-button
                                        theme="small primary"
                                        ?disabled=${isDownloading}
                                        @click=${() => this.quickDownload(v.model_id)}
                                      >
                                        ${isDownloading ? 'Starting...' : 'Download'}
                                      </vaadin-button>
                                    `}
                              </div>
                            </div>
                          `;
                        })}
                  </div>
                `
              : ''}
          `;
        })}
      </div>
    `;
  }

  renderHfBrowser(busy) {
    const hfModels = api.hfModelsSignal.get() || [];
    const loading = api.hfLoadingSignal.get();

    if (loading && hfModels.length === 0) {
      return html`
        <div class="list-surface" style="padding: var(--lumo-space-xl); text-align: center;">
          <div class="lumo-inline-loading">
            <span class="lumo-loader-spinner"></span>
            <span>Searching Hugging Face models...</span>
          </div>
        </div>
      `;
    }

    if (hfModels.length === 0) {
      return html`
        <div class="list-surface" style="padding: var(--lumo-space-xl); text-align: center; color: var(--lumo-secondary-text-color);">
          No Hugging Face models found for this query.
        </div>
      `;
    }

    return html`
      <div class="list-surface">
        ${hfModels.map((repo) => {
          const isExpanded = this.expandedHfRepo === repo.id;
          const quants = this.hfRepoQuantsMap[repo.id] || [];
          const isQuantsLoading = this.hfRepoQuantsLoading === repo.id;
          const isMlx = repo.format === 'mlx';
          const isDownloading = busy === `download:${repo.url}`;

          return html`
            <div class="list-row" data-hf-repo="${repo.id}">
              <div class="row-main">
                <div class="row-title-line">
                  <h3 class="row-title">${repo.id}</h3>
                  <span class="raw-token">${repo.format.toUpperCase()}</span>
                  ${repo.vision ? html`<span class="state-badge state-idle">Vision</span>` : ''}
                  <a href="${repo.url}" target="_blank" rel="noreferrer" class="ext-link">
                    <span>Hugging Face</span>
                    <vaadin-icon ligature="open_in_new"></vaadin-icon>
                  </a>
                </div>
                <div class="row-meta-line">
                  <span>${repo.downloads.toLocaleString()} downloads</span>
                  <span>${repo.likes.toLocaleString()} likes</span>
                </div>
              </div>

              <div class="row-actions">
                ${isMlx
                  ? html`
                      <vaadin-button
                        theme="small primary"
                        ?disabled=${isDownloading}
                        @click=${() => this.quickDownload(repo.url)}
                      >
                        ${isDownloading ? 'Starting...' : 'Download MLX'}
                      </vaadin-button>
                    `
                  : html`
                      <vaadin-button
                        theme="small ${isExpanded ? 'contrast' : 'tertiary'}"
                        @click=${() => this.toggleHfRepoQuants(repo.id)}
                      >
                        ${isExpanded ? 'Hide Quants' : 'Pick Quant...'}
                      </vaadin-button>
                    `}
              </div>
            </div>

            ${isExpanded
              ? html`
                  <div class="row-variants-drawer">
                    ${isQuantsLoading
                      ? html`
                          <div class="lumo-inline-loading">
                            <span class="lumo-loader-spinner"></span>
                            <span>Inspecting GGUF quantizations on Hugging Face...</span>
                          </div>
                        `
                      : quants.length === 0
                      ? html`
                          <div class="variant-item-row">
                            <span style="color: var(--lumo-secondary-text-color);">
                              No individual .gguf quantizations detected; download repository directly:
                            </span>
                            <vaadin-button
                              theme="small primary"
                              @click=${() => this.quickDownload(repo.url)}
                            >
                              Download Repo
                            </vaadin-button>
                          </div>
                        `
                      : quants.map((q) => {
                          const dlBusy = busy === `download:${repo.url}`;
                          return html`
                            <div class="variant-item-row">
                              <div class="row-title-line">
                                <span class="raw-token quant">${q.quantization}</span>
                                <span class="raw-token">${q.filename}</span>
                                ${q.size_bytes
                                  ? html`<span style="color: var(--lumo-secondary-text-color);">${formatBytes(q.size_bytes)}</span>`
                                  : ''}
                              </div>
                              <vaadin-button
                                theme="small primary"
                                ?disabled=${dlBusy}
                                @click=${() => this.quickDownload(repo.url, q.quantization)}
                              >
                                Download ${q.quantization}
                              </vaadin-button>
                            </div>
                          `;
                        })}
                  </div>
                `
              : ''}
          `;
        })}
      </div>
    `;
  }

  renderDownloadsView(models, downloads, busy) {
    const installedKeys = new Set(
      (models || []).flatMap((m) => [
        (m.key || '').toLowerCase(),
        (m.selected_variant || '').toLowerCase(),
      ])
    );

    return html`
      <div class="main-scroll-container">
        <div class="content-max-width">
          <form class="pull-bar" @submit=${(e) => this.submitDownload(e)}>
            <div class="pull-field-main">
              <label for="download-model-input">
                Pull by LM Studio Catalog ID or Hugging Face URL
              </label>
              <input
                id="download-model-input"
                class="text-input mono"
                type="text"
                placeholder="e.g. google/gemma-4-12b or https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF"
                .value=${this.downloadInput}
                @input=${(e) => this.onDownloadInputChange(e.target.value)}
              />
            </div>

            <div class="pull-field-quant">
              <label for="download-quant-input">
                Quantization ${this.hfLookupLoading ? '(loading...)' : '(optional)'}
              </label>
              ${this.hfQuantOptions.length > 0
                ? html`
                    <select
                      id="download-quant-select"
                      class="text-input mono"
                      .value=${this.downloadQuant}
                      @change=${(e) => {
                        this.downloadQuant = e.target.value;
                      }}
                    >
                      <option value="">(Default)</option>
                      ${this.hfQuantOptions.map(
                        (q) => html`
                          <option value="${q.quantization}" ?selected=${this.downloadQuant === q.quantization}>
                            ${q.quantization} ${q.size_bytes ? `(${formatBytes(q.size_bytes)})` : ''}
                          </option>
                        `
                      )}
                    </select>
                  `
                : html`
                    <input
                      id="download-quant-input"
                      class="text-input mono"
                      type="text"
                      placeholder="e.g. Q4_K_M"
                      .value=${this.downloadQuant}
                      @input=${(e) => {
                        this.downloadQuant = e.target.value;
                      }}
                    />
                  `}
            </div>

            <vaadin-button
              id="start-download-btn"
              theme="primary"
              ?disabled=${!this.downloadInput.trim() || busy.startsWith('download:')}
              @click=${(e) => this.submitDownload(e)}
            >
              Download
            </vaadin-button>
          </form>

          ${downloads.length > 0
            ? html`
                <div>
                  <div class="section-header">
                    <h2 class="section-title">Download Jobs (${downloads.length})</h2>
                  </div>
                  <div class="list-surface">
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
                          <div class="list-row" data-job-id="${j.job_id}" style="flex-direction: column; align-items: stretch; gap: 4px;">
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: var(--lumo-space-s); flex-wrap: wrap;">
                              <div class="row-title-line">
                                <span style="font-weight: 600;">${j.model_id}</span>
                                <span class="state-badge ${badgeClass}">${j.status}</span>
                                <span class="raw-token">${j.job_id}</span>
                              </div>
                              <div class="row-meta-line">
                                ${j.bytes_per_second ? html`<span>${formatSpeed(j.bytes_per_second)}</span>` : ''}
                                ${j.total_size_bytes
                                  ? html`<span>${formatBytes(j.downloaded_bytes || 0)} / ${formatBytes(j.total_size_bytes)} (${j.progress_pct}%)</span>`
                                  : ''}
                                ${j.completed_at
                                  ? html`<span>${formatIsoShort(j.completed_at)}</span>`
                                  : j.started_at
                                  ? html`<span>${formatIsoShort(j.started_at)}</span>`
                                  : ''}
                              </div>
                            </div>

                            ${isActive || !isDone
                              ? html`
                                  <div class="download-progress-track">
                                    <div
                                      class="download-progress-fill ${isDone ? 'completed' : isFail ? 'failed' : ''}"
                                      style="width: ${j.progress_pct || 0}%;"
                                    ></div>
                                  </div>
                                `
                              : ''}
                          </div>
                        `;
                      }
                    )}
                  </div>
                </div>
              `
            : ''}

          <div>
            <div class="toolbar-row" style="margin-bottom: var(--lumo-space-s);">
              <div class="toolbar-left">
                <segmented-control
                  id="discover-source-control"
                  .options=${DISCOVER_SOURCE_OPTIONS}
                  .value=${this.discoverSource}
                  @change=${(e) => this.onDiscoverSourceChange(e.detail.value)}
                ></segmented-control>

                <input
                  id="discover-search-input"
                  class="text-input"
                  type="search"
                  placeholder="${this.discoverSource === 'catalog'
                    ? 'Search LM Studio catalog...'
                    : 'Search Hugging Face models...'}"
                  .value=${this.discoverQuery}
                  @input=${(e) => this.onDiscoverQueryInput(e.target.value)}
                  style="width: 240px;"
                />

                ${this.discoverSource === 'hf'
                  ? html`
                      <segmented-control
                        id="hf-format-control"
                        .options=${HF_FORMAT_OPTIONS}
                        .value=${this.hfFormatFilter}
                        @change=${(e) => this.onHfFormatChange(e.detail.value)}
                      ></segmented-control>
                    `
                  : ''}
              </div>

              <div class="toolbar-right">
                ${this.discoverSource === 'catalog'
                  ? html`
                      <a href="https://lmstudio.ai/models" target="_blank" rel="noreferrer" class="ext-link">
                        <span>Open lmstudio.ai/models</span>
                        <vaadin-icon ligature="open_in_new"></vaadin-icon>
                      </a>
                    `
                  : html`
                      <a
                        href="https://huggingface.co/models?other=lmstudio"
                        target="_blank"
                        rel="noreferrer"
                        class="ext-link"
                      >
                        <span>Open Hugging Face</span>
                        <vaadin-icon ligature="open_in_new"></vaadin-icon>
                      </a>
                    `}
              </div>
            </div>

            ${this.discoverSource === 'catalog'
              ? this.renderCatalogBrowser(installedKeys, busy)
              : this.renderHfBrowser(busy)}
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
    const svc = status?.service;

    const viewOptionsWithCounts = VIEW_OPTIONS.map((v) =>
      v.value === 'inventory'
        ? { ...v, label: `Installed (${models.length})` }
        : {
            ...v,
            label:
              activeDownloads.length > 0
                ? `Discover & Download (${activeDownloads.length} active)`
                : 'Discover & Download',
          }
    );

    return html`
      <div class="app-root-container">
        <header class="app-header">
          <div class="header-left">
            <h1 class="brand-title">LM Studio Models</h1>

            <span
              class="state-badge ${status.connected ? 'state-running' : 'state-failed'}"
              title="${status.error || status.lmstudio_url}"
            >
              <span class="status-dot ${status.connected ? 'dot-ready' : 'dot-offline'}"></span>
              <span>${status.connected ? status.lmstudio_url.replace(/^https?:\/\//, '') : 'Offline'}</span>
            </span>

            <a href="https://lmstudio.ai/models" target="_blank" rel="noreferrer" class="ext-link">
              <span>Model Catalog</span>
              <vaadin-icon ligature="open_in_new"></vaadin-icon>
            </a>

            <a href="https://huggingface.co/models?other=lmstudio" target="_blank" rel="noreferrer" class="ext-link">
              <span>Hugging Face</span>
              <vaadin-icon ligature="open_in_new"></vaadin-icon>
            </a>
          </div>

          <div class="header-right">
            <segmented-control
              id="view-switcher-control"
              .options=${viewOptionsWithCounts}
              .value=${this.activeView}
              @change=${(e) => this.switchView(e.detail.value)}
            ></segmented-control>

            ${svc
              ? html`
                  <button
                    id="open-service-dialog-btn"
                    type="button"
                    class="chip-btn"
                    @click=${() => this.openServiceDialog()}
                    title="Background service (${svc.service_manager})"
                  >
                    <span
                      class="status-dot ${svc.running ? 'dot-ready' : svc.installed ? 'dot-starting' : 'dot-offline'}"
                    ></span>
                    <span>Service</span>
                  </button>
                `
              : ''}

            <button
              id="refresh-models-btn"
              type="button"
              class="icon-btn"
              @click=${() => this.refreshAll()}
              title="Refresh"
              aria-label="Refresh"
            >
              <vaadin-icon ligature="refresh" style="width: 18px; height: 18px;"></vaadin-icon>
            </button>
          </div>
        </header>

        ${this.activeView === 'downloads'
          ? this.renderDownloadsView(models, downloads, busy)
          : this.renderInventoryView(models, modelsLoading, busy)}

        <load-dialog
          @submit-load=${(e) => this.handleLoadSubmit(e)}
        ></load-dialog>

        <service-dialog
          .busy=${this.serviceBusy}
          @service-action=${(e) => this.handleServiceAction(e)}
        ></service-dialog>

        <confirm-dialog
          id="delete-model-dialog"
          header="Delete Local Model"
          .message=${this.pendingDeleteModel
            ? `Unload (if active) and delete '${this.pendingDeleteModel.display_name}' (${formatBytes(
                this.pendingDeleteModel.size_bytes
              )}) from disk?`
            : ''}
          .paths=${this.pendingDeleteModel?.disk_paths?.delete_targets || []}
          confirmText="Delete Model"
          confirmTheme="primary error"
          @confirm=${() => this.confirmDeleteModel()}
          @cancel=${() => {
            this.pendingDeleteModel = null;
          }}
        ></confirm-dialog>

        ${toast
          ? html`
              <div class="toast-banner toast-${toast.type}" role="status">
                <span>${toast.message}</span>
              </div>
            `
          : ''}
      </div>
    `;
  }
}

customElements.define('lms-manager-app', LmsManagerApp);
