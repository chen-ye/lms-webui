/**
 * Clipboard Monkeypatch & Polyfill for Insecure Origins
 *
 * The asynchronous Clipboard API (navigator.clipboard.writeText) is restricted to
 * secure contexts (HTTPS or localhost). When SimAF Manager is accessed over
 * internal LAN / VPN HTTP origins (e.g., http://*.int.r2air.com or http://10.x.x.x),
 * navigator.clipboard is undefined or throws NotAllowedError.
 *
 * This utility monkeypatches navigator.clipboard.writeText to transparently fall back
 * to document.execCommand('copy') with an offscreen textarea during user gestures.
 */

export function fallbackCopyText(text) {
  return new Promise((resolve) => {
    try {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.top = '0';
      textArea.style.left = '0';
      textArea.style.width = '2em';
      textArea.style.height = '2em';
      textArea.style.padding = '0';
      textArea.style.border = 'none';
      textArea.style.outline = 'none';
      textArea.style.boxShadow = 'none';
      textArea.style.background = 'transparent';
      textArea.style.opacity = '0';
      textArea.style.zIndex = '-1';
      textArea.setAttribute('readonly', '');
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      textArea.setSelectionRange(0, textArea.value.length);
      document.execCommand('copy');
      document.body.removeChild(textArea);
      resolve();
    } catch (err) {
      resolve();
    }
  });
}

export function copyToClipboard(text) {
  if (navigator?.clipboard?.writeText) {
    return navigator.clipboard.writeText(text).catch(() => fallbackCopyText(text));
  }
  return fallbackCopyText(text);
}

(function initClipboardMonkeypatch() {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') return;

  const isSecure = !!window.isSecureContext;
  const hasNative = !!(navigator.clipboard && typeof navigator.clipboard.writeText === 'function');

  if (!isSecure || !hasNative) {
    const customClipboard = {
      writeText: fallbackCopyText,
      readText: () => Promise.resolve(''),
    };

    try {
      if (!navigator.clipboard) {
        Object.defineProperty(navigator, 'clipboard', {
          value: customClipboard,
          writable: true,
          configurable: true,
        });
      } else {
        navigator.clipboard.writeText = fallbackCopyText;
      }
    } catch (e) {
      try {
        navigator.clipboard = customClipboard;
      } catch (err) {
        console.warn('Could not define navigator.clipboard on insecure origin:', err);
      }
    }
  } else {
    // In secure contexts, wrap native writeText with fallback on rejection
    try {
      const nativeWriteText = navigator.clipboard.writeText.bind(navigator.clipboard);
      navigator.clipboard.writeText = function (text) {
        return nativeWriteText(text).catch(() => fallbackCopyText(text));
      };
    } catch (e) {}
  }
})();
