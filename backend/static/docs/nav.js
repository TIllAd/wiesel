(() => {
  if (document.querySelector('[data-docs-nav]')) return;
  const nav = document.createElement('nav');
  nav.setAttribute('data-docs-nav', '');
  nav.innerHTML = '<a href="/" target="_top">← Alle Docs</a>';
  const style = document.createElement('style');
  style.textContent = `
    [data-docs-nav] { max-width:1120px; margin:0 auto; padding:18px 28px 0; font-family:Inter, system-ui, -apple-system, Segoe UI, sans-serif; }
    [data-docs-nav] a { color:#94a3b8; text-decoration:none; font-size:13px; }
    [data-docs-nav] a:hover { color:#e5e7eb; }
  `;
  document.head.appendChild(style);
  document.body.prepend(nav);
})();
