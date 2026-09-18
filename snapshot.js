// Freebuff Browser Control — page-injection JavaScript layer.
//
// Each export is a self-contained arrow function body executed by Playwright's
// page.evaluate(). The file is valid JS (check with: node --check snapshot.js);
// daemon.py extracts the template literals at load time — so keep each snippet
// a single `const NAME = \`...\`;` with no backticks or ${} inside the body.

const SNAPSHOT = `
() => {
  const out = [];
  const INTERACTIVE = new Set(['A','BUTTON','INPUT','TEXTAREA','SELECT','SUMMARY','OPTION','LABEL']);
  const TEXTY = new Set(['H1','H2','H3','H4','H5','H6','P','LI','TH','TD','FIGCAPTION','BLOCKQUOTE','CODE','PRE']);
  const RoleOf = (el) => {
    const r = (el.getAttribute('role') || '').toLowerCase();
    if (r) return r;
    const t = el.tagName;
    if (t === 'A') return el.getAttribute('href') ? 'link' : 'text';
    if (t === 'BUTTON') return 'button';
    if (t === 'INPUT') {
      const ty = (el.getAttribute('type') || 'text').toLowerCase();
      if (ty === 'checkbox') return 'checkbox';
      if (ty === 'radio') return 'radio';
      if (ty === 'submit') return 'button';
      if (ty === 'button') return 'button';
      if (['text','email','password','search','tel','url','number','date'].includes(ty)) return 'textbox';
      return 'textbox';
    }
    if (t === 'TEXTAREA') return 'textbox';
    if (t === 'SELECT') return 'combobox';
    if (t === 'SUMMARY') return 'button';
    if (t === 'LABEL') return 'label';
    if (/^H[1-6]$/.test(t)) return 'heading';
    return 'text';
  };
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) return false;
    const st = getComputedStyle(el);
    return st.visibility !== 'hidden' && st.display !== 'none' && st.opacity !== '0';
  };
  const label = (el) => {
    let s = el.getAttribute('aria-label') || '';
    if (!s && el.tagName === 'INPUT') {
      s = el.getAttribute('placeholder') || el.value || el.getAttribute('title') || '';
      if (!s) {
        const l = el.labels && el.labels[0];
        if (l) s = l.innerText;
      }
      if (el.tagName === 'INPUT' && (el.getAttribute('type')||'text') === 'password' && !s) s = 'password field';
    }
    if (!s && el.tagName === 'TEXTAREA') s = el.getAttribute('placeholder') || el.value || '';
    if (!s) s = (el.innerText || '').replace(/\\s+/g, ' ').trim();
    if (!s) s = el.getAttribute('title') || el.getAttribute('alt') || el.getAttribute('name') || '';
    return s.replace(/\\s+/g, ' ').trim().slice(0, 140);
  };
  let uid = 0;
  const walk = (root) => {
    for (const el of root.querySelectorAll('*')) {
      if (el.closest('svg,script,style,noscript,template')) continue;
      if (el.parentElement && INTERACTIVE.has(el.parentElement.tagName)
          && el.tagName !== 'OPTION' && !el.hasAttribute('role')
          && !['INPUT','TEXTAREA','SELECT'].includes(el.tagName)) continue;
      const t = el.tagName;
      const interactive = INTERACTIVE.has(t) || (el.getAttribute('role')||'') !== '' || el.hasAttribute('onclick') || el.isContentEditable;
      const texty = TEXTY.has(t);
      if (!interactive && !texty) continue;
      if (!visible(el)) continue;
      if (texty && !interactive) {
        // skip text blocks fully covered by richer children
        if (el.querySelector('h1,h2,h3,h4,h5,h6,p,li,a,button,input,textarea,select')) continue;
      }
      uid += 1;
      const id = 'e' + uid;
      try { el.setAttribute('data-fb-uid', id); } catch (e) {}
      const item = {
        uid: id, tag: t.toLowerCase(), role: RoleOf(el), name: label(el),
        interactive: !!interactive,
      };
      if (el.tagName === 'A' && el.getAttribute('href')) item.href = el.href;
      if (t === 'INPUT' || t === 'TEXTAREA') {
        if (el.value) item.value = el.value.slice(0, 80);
        const ty = el.getAttribute('type');
        if (ty && ty !== 'text') item.type = ty;
        if (el.required) item.required = true;
      }
      if (el.isContentEditable) item.editable = true;
      if (t === 'INPUT' && ((el.getAttribute('type')||'') === 'checkbox' || (el.getAttribute('type')||'') === 'radio'))
        item.checked = el.checked;
      if (t === 'SELECT') item.value = el.value;
      if (/^H[1-6]$/.test(t)) item.level = parseInt(t[1]);
      if (el.disabled) item.disabled = true;
      out.push(item);
      if (out.length > 400) break;
    }
  };
  walk(document.body || document);
  return out;
}
`;

const PAGE_TEXT = `
() => {
  const clone = document.body ? document.body.cloneNode(true) : null;
  if (!clone) return '';
  for (const s of clone.querySelectorAll('script,style,noscript,template,svg')) s.remove();
  return (clone.innerText || '').replace(/\\n{3,}/g, '\\n\\n').trim();
}
`;

const DESCRIBE = `
(el) => {
  let n = el.getAttribute('aria-label') || el.innerText || el.getAttribute('placeholder') || el.value || '';
  return { tag: el.tagName.toLowerCase(), name: n.replace(/\\s+/g,' ').trim().slice(0,60) };
}
`;
