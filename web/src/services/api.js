/**
 * Reactive API Client for LM Studio Model Manager WebUI
 * Exposes TC39 Signals (`@lit-labs/signals`) for models, downloads, catalog discovery, and service state.
 */

import { computed, signal } from '@lit-labs/signals';

export class LmsApiClient {
  constructor() {
    this.baseUrl = window.location.origin;

    this.statusSignal = signal({
      connected: false,
      lmstudio_url: 'http://localhost:1234',
      lmstudio_home: '~/.lmstudio',
      downloads_folder: '~/.lmstudio/models',
      default_context_length: 8192,
      auth_configured: false,
      model_count: 0,
      loaded_instance_count: 0,
      service: null,
      error: null,
    });

    this.modelsSignal = signal([]);
    this.modelsLoadingSignal = signal(true);
    this.downloadsSignal = signal([]);
    this.downloadsLoadingSignal = signal(false);

    this.catalogFamiliesSignal = signal([]);
    this.catalogLoadingSignal = signal(false);
    this.hfModelsSignal = signal([]);
    this.hfLoadingSignal = signal(false);

    this.busyActionSignal = signal('');
    this.toastSignal = signal(null);

    this.loadedInstancesComputed = computed(() => {
      const models = this.modelsSignal.get() || [];
      const items = [];
      for (const m of models) {
        for (const inst of m.loaded_instances || []) {
          items.push({
            instance_id: inst.id,
            config: inst.config || {},
            remaining_ttl_seconds: inst.remaining_ttl_seconds ?? null,
            model_key: m.key,
            display_name: m.display_name || m.key,
          });
        }
      }
      return items;
    });

    this.activeDownloadsComputed = computed(() =>
      (this.downloadsSignal.get() || []).filter(
        (j) => j.status === 'downloading' || j.status === 'paused'
      )
    );

    this._toastTimer = null;
  }

  showToast(message, type = 'info', durationMs = 4000) {
    if (this._toastTimer) clearTimeout(this._toastTimer);
    this.toastSignal.set({ message, type });
    if (durationMs > 0) {
      this._toastTimer = setTimeout(() => {
        this.toastSignal.set(null);
      }, durationMs);
    }
  }

  async fetchStatus() {
    try {
      const res = await fetch(`${this.baseUrl}/api/status`);
      if (res.ok) {
        const data = await res.json();
        this.statusSignal.set(data);
        return data;
      }
    } catch (e) {
      this.statusSignal.set({
        ...this.statusSignal.get(),
        connected: false,
        error: String(e.message || e),
      });
    }
    return this.statusSignal.get();
  }

  async fetchModels({ silent = false } = {}) {
    if (!silent) this.modelsLoadingSignal.set(true);
    try {
      const res = await fetch(`${this.baseUrl}/api/models`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `Failed to fetch models (${res.status})`);
      }
      const data = await res.json();
      this.modelsSignal.set(data.models || []);
      return data.models || [];
    } catch (e) {
      if (!silent) {
        this.showToast(e.message || 'Failed to load model list', 'error');
      }
      return [];
    } finally {
      this.modelsLoadingSignal.set(false);
    }
  }

  async loadModel(payload) {
    this.busyActionSignal.set(`load:${payload.model}`);
    try {
      const res = await fetch(`${this.baseUrl}/api/models/load`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `Model load failed (${res.status})`);
      }
      const data = await res.json();
      this.showToast(
        `Loaded ${data.instance_id || payload.model} in ${(data.load_time_seconds ?? 0).toFixed(2)}s`,
        'success'
      );
      await Promise.all([this.fetchModels({ silent: true }), this.fetchStatus()]);
      return data;
    } finally {
      this.busyActionSignal.set('');
    }
  }

  async unloadModel(instanceId) {
    this.busyActionSignal.set(`unload:${instanceId}`);
    try {
      const res = await fetch(`${this.baseUrl}/api/models/unload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instance_id: instanceId }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `Unload failed (${res.status})`);
      }
      const data = await res.json();
      this.showToast(`Unloaded ${instanceId}`, 'success');
      await Promise.all([this.fetchModels({ silent: true }), this.fetchStatus()]);
      return data;
    } finally {
      this.busyActionSignal.set('');
    }
  }

  async unloadAllModels() {
    this.busyActionSignal.set('unload-all');
    try {
      const res = await fetch(`${this.baseUrl}/api/models/unload-all`, {
        method: 'POST',
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `Unload all failed (${res.status})`);
      }
      const data = await res.json();
      this.showToast(`Unloaded ${data.count || 0} model instance(s)`, 'success');
      await Promise.all([this.fetchModels({ silent: true }), this.fetchStatus()]);
      return data;
    } finally {
      this.busyActionSignal.set('');
    }
  }

  async deleteModel({ uid, key, selected_variant, format, size_bytes }) {
    this.busyActionSignal.set(`delete:${uid || key}`);
    try {
      const res = await fetch(`${this.baseUrl}/api/models`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uid, key, selected_variant, format, size_bytes }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `Delete failed (${res.status})`);
      }
      const data = await res.json();
      this.showToast(`Deleted ${selected_variant || key}`, 'success');
      await Promise.all([this.fetchModels({ silent: true }), this.fetchStatus()]);
      return data;
    } finally {
      this.busyActionSignal.set('');
    }
  }

  async fetchDownloads({ silent = false } = {}) {
    if (!silent) this.downloadsLoadingSignal.set(true);
    try {
      const res = await fetch(`${this.baseUrl}/api/models/downloads`);
      if (res.ok) {
        const data = await res.json();
        this.downloadsSignal.set(data.jobs || []);
        return data.jobs || [];
      }
    } catch (e) {
      // ignore transient error
    } finally {
      this.downloadsLoadingSignal.set(false);
    }
    return this.downloadsSignal.get();
  }

  async startDownload({ model, quantization }) {
    this.busyActionSignal.set(`download:${model}`);
    try {
      const res = await fetch(`${this.baseUrl}/api/models/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model, quantization: quantization || null }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `Download failed (${res.status})`);
      }
      const data = await res.json();
      if (data.status === 'already_downloaded') {
        this.showToast(`'${model}' is already downloaded`, 'info');
      } else {
        this.showToast(`Download started (${data.job_id || data.status})`, 'success');
      }
      await Promise.all([this.fetchDownloads({ silent: true }), this.fetchModels({ silent: true })]);
      return data;
    } finally {
      this.busyActionSignal.set('');
    }
  }

  async fetchHfQuantizations(repoOrUrl) {
    const res = await fetch(
      `${this.baseUrl}/api/hf/quantizations?repo=${encodeURIComponent(repoOrUrl)}`
    );
    if (!res.ok) return { is_hf: false, quantizations: [] };
    return await res.json();
  }

  async fetchCatalog(query = '') {
    this.catalogLoadingSignal.set(true);
    try {
      const res = await fetch(
        `${this.baseUrl}/api/catalog?q=${encodeURIComponent(query || '')}`
      );
      if (res.ok) {
        const data = await res.json();
        this.catalogFamiliesSignal.set(data.families || []);
        return data.families || [];
      }
    } catch (e) {
      // ignore offline error
    } finally {
      this.catalogLoadingSignal.set(false);
    }
    return this.catalogFamiliesSignal.get();
  }

  async fetchCatalogFamily(slug) {
    const res = await fetch(`${this.baseUrl}/api/catalog/${encodeURIComponent(slug)}`);
    if (!res.ok) return { slug, variants: [] };
    return await res.json();
  }

  async searchHfModels(query = '', format = 'all') {
    this.hfLoadingSignal.set(true);
    try {
      const res = await fetch(
        `${this.baseUrl}/api/hf/search?q=${encodeURIComponent(query || '')}&format=${encodeURIComponent(format || 'all')}`
      );
      if (res.ok) {
        const data = await res.json();
        this.hfModelsSignal.set(data.models || []);
        return data.models || [];
      }
    } catch (e) {
      // ignore offline error
    } finally {
      this.hfLoadingSignal.set(false);
    }
    return this.hfModelsSignal.get();
  }

  async serviceAction(action, body = {}) {
    const res = await fetch(`${this.baseUrl}/api/service/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Service ${action} failed (${res.status})`);
    }
    const data = await res.json();
    await this.fetchStatus();
    return data;
  }
}

export const api = new LmsApiClient();
