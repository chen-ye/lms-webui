(map => {
  document.head.appendChild(Object.assign(document.createElement("script"), {
    type: "importmap",
    innerHTML: JSON.stringify({
      imports: map.imports,
      scopes: map.scopes
    })
  }));
})
({
  "imports": {
    "@lit-labs/signals": "https://ga.jspm.io/npm:@lit-labs/signals@0.3.0/index.js",
    "@vaadin/accordion": "https://ga.jspm.io/npm:@vaadin/accordion@25.3.2/vaadin-accordion.js",
    "@vaadin/button": "https://ga.jspm.io/npm:@vaadin/button@25.3.2/vaadin-button.js",
    "@vaadin/checkbox": "https://ga.jspm.io/npm:@vaadin/checkbox@25.3.2/vaadin-checkbox.js",
    "@vaadin/combo-box": "https://ga.jspm.io/npm:@vaadin/combo-box@25.3.2/vaadin-combo-box.js",
    "@vaadin/details": "https://ga.jspm.io/npm:@vaadin/details@25.3.2/vaadin-details.js",
    "@vaadin/icon": "https://ga.jspm.io/npm:@vaadin/icon@25.3.2/vaadin-icon.js",
    "@vaadin/number-field": "https://ga.jspm.io/npm:@vaadin/number-field@25.3.2/vaadin-number-field.js",
    "@vaadin/select": "https://ga.jspm.io/npm:@vaadin/select@25.3.2/vaadin-select.js",
    "@vaadin/tabs": "https://ga.jspm.io/npm:@vaadin/tabs@25.3.2/vaadin-tabs.js",
    "@vaadin/text-field": "https://ga.jspm.io/npm:@vaadin/text-field@25.3.2/vaadin-text-field.js",
    "@vaadin/vaadin-lumo-styles": "https://ga.jspm.io/npm:@vaadin/vaadin-lumo-styles@25.3.2/all-imports.js",
    "@vaadin/virtual-list": "https://ga.jspm.io/npm:@vaadin/virtual-list@25.3.2/vaadin-virtual-list.js",
    "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js",
    "lit/": "https://ga.jspm.io/npm:lit@3.3.3/",
    "signal-polyfill": "https://ga.jspm.io/npm:signal-polyfill@0.2.2/dist/index.js"
  },
  "scopes": {
    "https://ga.jspm.io/npm:@vaadin/a11y-base@25.3.2/": {
      "@open-wc/dedupe-mixin": "https://ga.jspm.io/npm:@open-wc/dedupe-mixin@1.4.0/index.js",
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js"
    },
    "https://ga.jspm.io/npm:@vaadin/accordion@25.3.2/": {
      "@vaadin/a11y-base/src/": "https://ga.jspm.io/npm:@vaadin/a11y-base@25.3.2/src/",
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "@vaadin/details/src/": "https://ga.jspm.io/npm:@vaadin/details@25.3.2/src/",
      "@vaadin/vaadin-themable-mixin/": "https://ga.jspm.io/npm:@vaadin/vaadin-themable-mixin@25.3.2/",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js"
    },
    "https://ga.jspm.io/npm:@vaadin/button@25.3.2/": {
      "@vaadin/a11y-base/src/": "https://ga.jspm.io/npm:@vaadin/a11y-base@25.3.2/src/",
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "@vaadin/vaadin-themable-mixin/": "https://ga.jspm.io/npm:@vaadin/vaadin-themable-mixin@25.3.2/",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js"
    },
    "https://ga.jspm.io/npm:@vaadin/checkbox@25.3.2/": {
      "@vaadin/a11y-base/src/": "https://ga.jspm.io/npm:@vaadin/a11y-base@25.3.2/src/",
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "@vaadin/field-base/src/": "https://ga.jspm.io/npm:@vaadin/field-base@25.3.2/src/",
      "@vaadin/vaadin-themable-mixin/": "https://ga.jspm.io/npm:@vaadin/vaadin-themable-mixin@25.3.2/",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js"
    },
    "https://ga.jspm.io/npm:@vaadin/combo-box@25.3.2/": {
      "@vaadin/a11y-base/src/": "https://ga.jspm.io/npm:@vaadin/a11y-base@25.3.2/src/",
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "@vaadin/field-base/src/": "https://ga.jspm.io/npm:@vaadin/field-base@25.3.2/src/",
      "@vaadin/input-container/src/vaadin-input-container.js": "https://ga.jspm.io/npm:@vaadin/input-container@25.3.2/src/vaadin-input-container.js",
      "@vaadin/item/src/styles/vaadin-item-base-styles.js": "https://ga.jspm.io/npm:@vaadin/item@25.3.2/src/styles/vaadin-item-base-styles.js",
      "@vaadin/overlay/src/": "https://ga.jspm.io/npm:@vaadin/overlay@25.3.2/src/",
      "@vaadin/vaadin-themable-mixin/": "https://ga.jspm.io/npm:@vaadin/vaadin-themable-mixin@25.3.2/",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js",
      "lit/directives/if-defined.js": "https://ga.jspm.io/npm:lit@3.3.3/directives/if-defined.js"
    },
    "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/": {
      "@open-wc/dedupe-mixin": "https://ga.jspm.io/npm:@open-wc/dedupe-mixin@1.4.0/index.js",
      "@vaadin/vaadin-usage-statistics/vaadin-usage-statistics.js": "https://ga.jspm.io/npm:@vaadin/vaadin-usage-statistics@2.1.3/vaadin-usage-statistics.js",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js"
    },
    "https://ga.jspm.io/npm:@vaadin/details@25.3.2/": {
      "@vaadin/a11y-base/src/delegate-focus-mixin.js": "https://ga.jspm.io/npm:@vaadin/a11y-base@25.3.2/src/delegate-focus-mixin.js",
      "@vaadin/button/src/vaadin-button-mixin.js": "https://ga.jspm.io/npm:@vaadin/button@25.3.2/src/vaadin-button-mixin.js",
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "@vaadin/vaadin-themable-mixin/": "https://ga.jspm.io/npm:@vaadin/vaadin-themable-mixin@25.3.2/",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js"
    },
    "https://ga.jspm.io/npm:@vaadin/field-base@25.3.2/": {
      "@open-wc/dedupe-mixin": "https://ga.jspm.io/npm:@open-wc/dedupe-mixin@1.4.0/index.js",
      "@vaadin/a11y-base/src/": "https://ga.jspm.io/npm:@vaadin/a11y-base@25.3.2/src/",
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js"
    },
    "https://ga.jspm.io/npm:@vaadin/icon@25.3.2/": {
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "@vaadin/component-base/src/define.js": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/define.js",
      "@vaadin/vaadin-themable-mixin/": "https://ga.jspm.io/npm:@vaadin/vaadin-themable-mixin@25.3.2/",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js",
      "lit/": "https://ga.jspm.io/npm:lit@3.3.3/"
    },
    "https://ga.jspm.io/npm:@vaadin/input-container@25.3.2/": {
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "@vaadin/vaadin-themable-mixin/": "https://ga.jspm.io/npm:@vaadin/vaadin-themable-mixin@25.3.2/",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js"
    },
    "https://ga.jspm.io/npm:@vaadin/item@25.3.2/": {
      "@vaadin/a11y-base/src/": "https://ga.jspm.io/npm:@vaadin/a11y-base@25.3.2/src/",
      "@vaadin/component-base/src/styles/style-props.js": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/styles/style-props.js",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js"
    },
    "https://ga.jspm.io/npm:@vaadin/list-box@25.3.2/": {
      "@vaadin/component-base/src/styles/style-props.js": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/styles/style-props.js",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js"
    },
    "https://ga.jspm.io/npm:@vaadin/number-field@25.3.2/": {
      "@vaadin/a11y-base/src/focus-utils.js": "https://ga.jspm.io/npm:@vaadin/a11y-base@25.3.2/src/focus-utils.js",
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "@vaadin/field-base/src/": "https://ga.jspm.io/npm:@vaadin/field-base@25.3.2/src/",
      "@vaadin/input-container/src/vaadin-input-container.js": "https://ga.jspm.io/npm:@vaadin/input-container@25.3.2/src/vaadin-input-container.js",
      "@vaadin/vaadin-themable-mixin/": "https://ga.jspm.io/npm:@vaadin/vaadin-themable-mixin@25.3.2/",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js",
      "lit/directives/if-defined.js": "https://ga.jspm.io/npm:lit@3.3.3/directives/if-defined.js"
    },
    "https://ga.jspm.io/npm:@vaadin/overlay@25.3.2/": {
      "@vaadin/a11y-base/src/": "https://ga.jspm.io/npm:@vaadin/a11y-base@25.3.2/src/",
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js"
    },
    "https://ga.jspm.io/npm:@vaadin/select@25.3.2/": {
      "@vaadin/a11y-base/src/": "https://ga.jspm.io/npm:@vaadin/a11y-base@25.3.2/src/",
      "@vaadin/button/src/vaadin-button-mixin.js": "https://ga.jspm.io/npm:@vaadin/button@25.3.2/src/vaadin-button-mixin.js",
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "@vaadin/field-base/src/": "https://ga.jspm.io/npm:@vaadin/field-base@25.3.2/src/",
      "@vaadin/input-container/src/vaadin-input-container.js": "https://ga.jspm.io/npm:@vaadin/input-container@25.3.2/src/vaadin-input-container.js",
      "@vaadin/item/src/": "https://ga.jspm.io/npm:@vaadin/item@25.3.2/src/",
      "@vaadin/list-box/src/styles/vaadin-list-box-base-styles.js": "https://ga.jspm.io/npm:@vaadin/list-box@25.3.2/src/styles/vaadin-list-box-base-styles.js",
      "@vaadin/overlay/src/": "https://ga.jspm.io/npm:@vaadin/overlay@25.3.2/src/",
      "@vaadin/vaadin-themable-mixin/": "https://ga.jspm.io/npm:@vaadin/vaadin-themable-mixin@25.3.2/",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js",
      "lit/directives/if-defined.js": "https://ga.jspm.io/npm:lit@3.3.3/directives/if-defined.js"
    },
    "https://ga.jspm.io/npm:@vaadin/tabs@25.3.2/": {
      "@vaadin/a11y-base/src/list-mixin.js": "https://ga.jspm.io/npm:@vaadin/a11y-base@25.3.2/src/list-mixin.js",
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "@vaadin/item/src/vaadin-item-mixin.js": "https://ga.jspm.io/npm:@vaadin/item@25.3.2/src/vaadin-item-mixin.js",
      "@vaadin/vaadin-themable-mixin/": "https://ga.jspm.io/npm:@vaadin/vaadin-themable-mixin@25.3.2/",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js"
    },
    "https://ga.jspm.io/npm:@vaadin/text-field@25.3.2/": {
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "@vaadin/field-base/src/": "https://ga.jspm.io/npm:@vaadin/field-base@25.3.2/src/",
      "@vaadin/input-container/src/vaadin-input-container.js": "https://ga.jspm.io/npm:@vaadin/input-container@25.3.2/src/vaadin-input-container.js",
      "@vaadin/vaadin-themable-mixin/": "https://ga.jspm.io/npm:@vaadin/vaadin-themable-mixin@25.3.2/",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js",
      "lit/directives/if-defined.js": "https://ga.jspm.io/npm:lit@3.3.3/directives/if-defined.js"
    },
    "https://ga.jspm.io/npm:@vaadin/vaadin-lumo-styles@25.3.2/": {
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "@vaadin/icon/vaadin-iconset.js": "https://ga.jspm.io/npm:@vaadin/icon@25.3.2/vaadin-iconset.js",
      "@vaadin/vaadin-themable-mixin/vaadin-themable-mixin.js": "https://ga.jspm.io/npm:@vaadin/vaadin-themable-mixin@25.3.2/vaadin-themable-mixin.js"
    },
    "https://ga.jspm.io/npm:@vaadin/vaadin-themable-mixin@25.3.2/": {
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js"
    },
    "https://ga.jspm.io/npm:@vaadin/vaadin-usage-statistics@2.1.3/": {
      "@vaadin/vaadin-development-mode-detector/vaadin-development-mode-detector.js": "https://ga.jspm.io/npm:@vaadin/vaadin-development-mode-detector@2.0.7/vaadin-development-mode-detector.js"
    },
    "https://ga.jspm.io/npm:@vaadin/virtual-list@25.3.2/": {
      "@vaadin/component-base/src/": "https://ga.jspm.io/npm:@vaadin/component-base@25.3.2/src/",
      "@vaadin/vaadin-themable-mixin/vaadin-themable-mixin.js": "https://ga.jspm.io/npm:@vaadin/vaadin-themable-mixin@25.3.2/vaadin-themable-mixin.js",
      "lit": "https://ga.jspm.io/npm:lit@3.3.3/index.js"
    },
    "https://ga.jspm.io/npm:lit-element@4.2.2/": {
      "@lit/reactive-element": "https://ga.jspm.io/npm:@lit/reactive-element@2.1.2/development/reactive-element.js",
      "lit-html": "https://ga.jspm.io/npm:lit-html@3.3.3/development/lit-html.js"
    },
    "https://ga.jspm.io/npm:lit@3.3.3/": {
      "@lit/reactive-element": "https://ga.jspm.io/npm:@lit/reactive-element@2.1.2/development/reactive-element.js",
      "lit-element/lit-element.js": "https://ga.jspm.io/npm:lit-element@4.2.2/development/lit-element.js",
      "lit-html": "https://ga.jspm.io/npm:lit-html@3.3.3/development/lit-html.js",
      "lit-html/": "https://ga.jspm.io/npm:lit-html@3.3.3/development/"
    }
  }
});
