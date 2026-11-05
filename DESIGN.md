---
name: LM Studio Model Manager
description: Stateless control-plane WebUI for LM Studio's REST API (/api/v1) — model inventory, load/unload tuning, download manager, and symmetrical host deletion.
colors:
  base-bg: "#1f1f22"
  chrome-bg: "#18181b"
  surface-1: "#27272b"
  contrast-5: "rgba(243, 245, 247, 0.045)"
  contrast-10: "rgba(243, 245, 247, 0.08)"
  contrast-20: "rgba(243, 245, 247, 0.16)"
  contrast-30: "rgba(243, 245, 247, 0.24)"
  primary: "#615fff"
  primary-text: "#a3b3ff"
  body-text: "rgba(243, 245, 247, 0.94)"
  secondary-text: "rgba(243, 245, 247, 0.67)"
  tertiary-text: "rgba(243, 245, 247, 0.48)"
  success: "#00bc7d"
  error: "#fb2c36"
  warning: "#fe9a00"
typography:
  font-family: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
  font-family-monospace: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"
  font-size-xs: "11.5px"
  font-size-s: "13px"
  font-size-m: "14px"
---

# Design System

## Overview
`lmstudio-webui` is modeled on `ezsim_2000/web`: a zero-build frontend using **Lit 3**, **TC39 Signals (`@lit-labs/signals`)**, **Vaadin 25 Web Components** over a JSPM importmap, **Vaadin Lumo Dark Mode** design tokens (`lumo/lumo.css`), and **Material Symbols Outlined** (`<vaadin-icon ligature="...">`).

## Architectural Rules

### Do
- Serve ES modules directly without a bundler via `web/importmap.js`.
- Render icons exclusively via `<vaadin-icon ligature="...">` using Material Symbols Outlined.
- Style model keys, quantizations, CLI/API parameters, and resolved filesystem paths with `.raw-token`, `.raw-token.flag`, and `.raw-token.path`.
- Use `<confirm-dialog>` (native `<dialog closedby="any">` with backdrop light-dismiss fallback) to display exact resolved disk paths before model deletion.
- Keep the backend completely stateless: read `~/.lmstudio/settings.json`, `~/.lmstudio/.internal/model-index-cache.json`, `~/.lmstudio/.internal/download-jobs-info.json`, and `~/.lmstudio/.internal/lm-link-resume-cache.json` directly.

### Don't
- Do not apply `* { margin: 0; padding: 0; }`, which breaks Vaadin light-DOM metrics.
- Do not use emojis or hardcoded inline `<svg>` paths for icons.
- Do not include chat/inference playgrounds or hardware VRAM polling.
