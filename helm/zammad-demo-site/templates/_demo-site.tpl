{{- define "zammad-demo-site.demoSiteIndex" -}}
{{- $u := .zammadUrl -}}
{{- $product := "IT Self-Service" -}}
{{- $hero := "Sign in to Zammad" -}}
{{- $sub := "Use the demo accounts below with the live Zammad UI." -}}
{{- if .Values.demoSite -}}
{{-   $product = default $product .Values.demoSite.productName -}}
{{-   $hero = default $hero .Values.demoSite.heroTitle -}}
{{-   $sub = default $sub .Values.demoSite.heroSubtitle -}}
{{- end -}}
{{- $categories := .Values.demoSite.categories | default list -}}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ $product }} - Zammad demo site</title>
  <style>
    :root {
      --accent: #047857;
      --accent-hover: #059669;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --hairline: #f1f5f9;
      --radius: 12px;
    }
    * { box-sizing: border-box; }
    html { font-size: clamp(15px, 0.35vw + 14px, 17px); }
    html, body { height: 100%; margin: 0; }
    body {
      font-family: ui-sans-serif, system-ui, sans-serif;
      color: #0f172a;
      background: #fff;
      line-height: 1.5;
    }
    .page {
      max-width: min(90rem, calc(100% - 1.5rem));
      margin: 0 auto;
      padding: 1rem clamp(0.75rem, 2vw, 1.5rem) 1.5rem;
    }
    .dashboard-split {
      display: grid;
      grid-template-columns: 1fr;
      gap: 1rem;
    }
    @media (min-width: 960px) {
      .dashboard-split {
        grid-template-columns: minmax(17rem, 28vw) minmax(0, 2.5fr);
        gap: 1.5rem;
        align-items: center;
        min-height: calc(100svh - 5rem);
      }
      .dashboard-hero {
        justify-self: center;
        width: 100%;
        max-width: 22rem;
      }
      .dashboard-accounts {
        justify-self: center;
        width: 100%;
        max-width: min(52rem, 100%);
      }
      .footer-links { text-align: left; }
    }
    .page-header { text-align: center; }
    .page-header .brand {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 0.5rem;
      font-weight: 600;
      font-size: 1rem;
    }
    .page-header .brand span.icon {
      width: 2.4rem;
      height: 2.4rem;
      border-radius: 12px;
      background: linear-gradient(135deg, #dc2626, #b91c1c);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: #fff;
    }
    .page-header h1 { font-size: 1.35rem; margin: 0 0 0.35rem; font-weight: 650; line-height: 1.25; }
    .page-header .lead { margin: 0 auto; color: var(--text-muted); max-width: 38ch; font-size: 0.9375rem; line-height: 1.45; }
    a.btn-hero-open,
    a.btn-modal-open-zammad {
      padding: 0.55rem 1rem;
      font-size: 1rem;
      font-weight: 700;
      color: #fff !important;
      background: var(--accent);
      border-radius: 10px;
      text-decoration: none;
    }
    a.btn-hero-open:hover,
    a.btn-modal-open-zammad:hover { background: var(--accent-hover); }
    a.btn-hero-open {
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0.75rem auto 0;
      width: 100%;
    }
    .card {
      background: #fafafa;
      border-radius: var(--radius);
      border: 1px solid var(--border);
      padding: 1rem 1.1rem;
      margin-bottom: 0.65rem;
    }
    .card .hint { margin: 0 0 0.5rem; font-size: 0.875rem; color: var(--text-muted); }
    .card > h2 { margin: 0 0 0.35rem; font-size: 1.1rem; }
    .persona-demo-label {
      font-size: 0.75rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      color: var(--text-muted);
      margin: 0.25rem 0 0.5rem;
    }
    .persona-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 0.65rem;
    }
    @media (max-width: 720px) { .persona-grid { grid-template-columns: repeat(2, 1fr); } }
    @media (max-width: 420px) { .persona-grid { grid-template-columns: 1fr; } }
    .persona-group {
      display: flex;
      flex-direction: column;
      gap: 0.45rem;
      padding: 0.5rem;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: #fff;
      min-width: 0;
    }
    .persona-group-heading {
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--text-muted);
      margin: 0;
      padding-bottom: 0.35rem;
      border-bottom: 1px solid var(--hairline);
    }
    .persona-group-tiles {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
    }
    .persona {
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      padding: 0.5rem;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: #fafafa;
      cursor: pointer;
      flex: 1 1 auto;
      min-width: 4rem;
    }
    .persona:hover { border-color: var(--accent); background: #f0f7ff; }
    .persona.is-busy { opacity: 0.75; pointer-events: none; }
    .persona .circle {
      width: 2.45rem;
      height: 2.45rem;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.15rem;
      margin-bottom: 0.25rem;
    }
    .persona .name { font-size: 0.8125rem; font-weight: 600; color: #334155; }
    .persona .role { font-size: 0.75rem; color: var(--text-muted); margin-top: 0.1rem; }
    section.block { margin-bottom: 1.25rem; scroll-margin-top: 0.5rem; }
    section.block h3 { font-size: 1rem; margin: 0 0 0.5rem; color: #1e293b; }
    .table-wrap { overflow-x: auto; margin: 0; }
    table.accounts {
      width: 100%;
      table-layout: fixed;
      border-collapse: collapse;
      font-size: 0.8125rem;
      min-width: 28rem;
    }
    table.accounts col:nth-child(1) { width: 20%; }
    table.accounts col:nth-child(2) { width: 38%; }
    table.accounts col:nth-child(3) { width: 22%; }
    table.accounts col:nth-child(4) { width: 20%; }
    table.accounts th, table.accounts td {
      text-align: left;
      padding: 0.5rem 0.4rem;
      border-bottom: 1px solid var(--hairline);
      vertical-align: middle;
    }
    table.accounts thead th {
      color: var(--text-muted);
      font-weight: 600;
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      border-bottom: 2px solid var(--border);
    }
    table.accounts thead th:last-child {
      text-align: center;
    }
    table.accounts td.actions {
      text-align: center;
      justify-content: center;
    }
    table.accounts td.actions .btn { white-space: nowrap; }
    code.cred {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.8rem;
      word-break: break-all;
    }
    .actions { display: flex; flex-wrap: wrap; gap: 0.35rem; }
    button.btn, a.btn {
      font-size: 0.8125rem;
      padding: 0.35rem 0.55rem;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: #fff;
      cursor: pointer;
      color: #334155;
      font-family: inherit;
    }
    button.modal-close,
    button.btn-view-all,
    nav.categories button.category-chip {
      cursor: pointer;
      font-family: inherit;
    }
    button.btn.primary, a.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
    button.btn.primary:hover, a.btn.primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
    button.btn:focus-visible, a.btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
    table.accounts td.actions button.btn.is-copied {
      background: #ecfdf5;
      border-color: #34d399;
      color: var(--accent);
      font-weight: 600;
    }
    .toast {
      position: fixed;
      bottom: 1rem;
      left: 50%;
      transform: translateX(-50%) translateY(120%);
      background: #0f172a;
      color: #f8fafc;
      padding: 0.5rem 0.9rem;
      border-radius: 10px;
      font-size: 0.875rem;
      opacity: 0;
      transition: transform 0.2s, opacity 0.2s;
      z-index: 300;
      max-width: 90vw;
    }
    .toast.show { transform: translateX(-50%) translateY(0); opacity: 1; }
    body.modal-open { overflow: hidden; }
    button.btn-view-all {
      width: 100%;
      margin-bottom: 0.5rem;
      padding: 0.45rem 0.85rem;
      border-radius: 10px;
      font-size: 0.875rem;
      font-weight: 600;
      background: #fff;
      border: 1px solid #cbd5e1;
      color: #475569;
    }
    button.btn-view-all:hover,
    nav.categories button.category-chip:hover {
      border-color: var(--accent);
      color: var(--accent);
    }
    nav.categories { display: flex; flex-wrap: wrap; gap: 0.45rem; }
    nav.categories button.category-chip {
      font-size: 0.68rem;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: #475569;
      padding: 0.35rem 0.55rem;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: #fff;
    }
    .modal-overlay {
      position: fixed;
      inset: 0;
      z-index: 250;
      background: rgba(15, 23, 42, 0.45);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1rem;
      opacity: 0;
      visibility: hidden;
      transition: opacity 0.15s, visibility 0.15s;
    }
    .modal-overlay.is-open { opacity: 1; visibility: visible; }
    .modal-dialog {
      background: #fff;
      border-radius: 12px;
      width: min(720px, 100%);
      max-height: min(88vh, 900px);
      display: flex;
      flex-direction: column;
      border: 1px solid var(--border);
      box-shadow: 0 16px 40px rgba(15, 23, 42, 0.2);
    }
    .modal-header,
    .modal-footer {
      flex-shrink: 0;
      padding: 0.85rem 1rem;
    }
    .modal-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid var(--border);
    }
    .modal-header h2 { margin: 0; font-size: 1.05rem; font-weight: 650; }
    button.modal-close {
      border: none;
      background: #f1f5f9;
      width: 2.1rem;
      height: 2.1rem;
      border-radius: 8px;
      font-size: 1.2rem;
      color: #475569;
    }
    .modal-nav {
      flex-shrink: 0;
      padding: 0.65rem 0.85rem;
      border-bottom: 1px solid var(--border);
      background: #f8fafc;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }
    .modal-nav .categories {
      margin: 0;
      flex-wrap: nowrap;
      min-width: min-content;
      align-items: center;
    }
    .modal-body {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      padding: 0.85rem 1rem 1.1rem;
    }
    .modal-footer {
      border-top: 1px solid var(--border);
      background: #f8fafc;
      text-align: center;
    }
    .modal-footer-hint { margin: 0 0 0.5rem; font-size: 0.8rem; color: var(--text-muted); }
    a.btn-modal-open-zammad {
      display: inline-flex;
      justify-content: center;
      width: 100%;
      max-width: 18rem;
      margin: 0 auto;
    }
    .footer-links { font-size: 0.875rem; color: var(--text-muted); margin-top: 0.75rem; text-align: center; }
    .footer-links a { color: var(--accent); }
  </style>
</head>
<body>
  <div class="page">
    <div class="dashboard-split">
      <aside class="dashboard-hero">
        <header class="page-header">
          <div class="brand"><span class="icon" aria-hidden="true">⌂</span> {{ $product }}</div>
          <h1>{{ $hero }}</h1>
          <p class="lead">{{ $sub }}</p>
          <a class="btn-hero-open" href="{{ $u }}/" target="_blank" rel="noopener">Open Zammad</a>
        </header>
      </aside>

      <section class="dashboard-accounts" aria-label="Demo accounts">
        <div class="card">
          <h2>Demo accounts</h2>
          <p class="hint">Tap a persona to sign in.</p>
          <button type="button" class="btn-view-all" id="btn-open-accounts-modal">View all accounts &amp; passwords</button>
          <p class="persona-demo-label">Persona quick pick</p>
          <div class="persona-grid">
{{- range $categories }}
{{- $c := . }}
{{- $show := false }}
{{- range $c.rows }}{{- if .persona }}{{- $show = true }}{{- end }}{{- end }}
{{- if $show }}
            <div class="persona-group">
              <div class="persona-group-heading">{{ $c.navLabel }}</div>
              <div class="persona-group-tiles">
{{- range $c.rows }}
{{- if .persona }}
                <button type="button" class="persona js-persona-signin" data-email="{{ .email }}" data-password="{{ .password }}" data-section="{{ $c.id }}" aria-label="{{ .persona.shortName }} - {{ .persona.roleShort }} - {{ .email }}">
                  <span class="circle" style="background: {{ .persona.bg }}">{{ .persona.icon }}</span>
                  <span class="name">{{ .persona.shortName }}</span>
                  <span class="role">{{ .persona.roleShort }}</span>
                </button>
{{- end }}
{{- end }}
              </div>
            </div>
{{- end }}
{{- end }}
          </div>
        </div>
      </section>
    </div>

    <p class="footer-links">
      <a href="chat-embed.html">Chat widget snippet page</a>
      ·
      <a href="{{ $u }}/" target="_blank" rel="noopener">Zammad home</a>
    </p>
  </div>

  <div class="modal-overlay" id="accounts-modal" aria-hidden="true">
    <div class="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="accounts-modal-title">
      <div class="modal-header">
        <h2 id="accounts-modal-title">All demo accounts</h2>
        <button type="button" class="modal-close" id="btn-close-accounts-modal" aria-label="Close">&times;</button>
      </div>
      <div class="modal-nav">
        <nav class="categories" aria-label="Jump to category">
{{- range $categories }}
          <button type="button" class="category-chip js-modal-scroll" data-target="{{ .id }}">{{ .navLabel }}</button>
{{- end }}
        </nav>
      </div>
      <div class="modal-body">
{{- range $categories }}
        <section class="block" id="{{ .id }}">
          <h3>{{ .sectionTitle }}</h3>
          <div class="table-wrap"><table class="accounts">
            <colgroup><col><col><col><col></colgroup>
            <thead><tr><th>Role</th><th>Email</th><th>Password</th><th>Copy</th></tr></thead>
            <tbody>
{{- range .rows }}
              <tr>
                <td>{{ .role }}</td>
                <td><code class="cred">{{ .email }}</code></td>
                <td><code class="cred">{{ .password }}</code></td>
                <td class="actions"><button type="button" class="btn js-copy-email" data-email="{{ .email }}">Copy email</button><button type="button" class="btn js-copy-password" data-password="{{ .password }}">Copy password</button></td>
              </tr>
{{- end }}
            </tbody>
          </table></div>
        </section>
{{- end }}
      </div>
      <div class="modal-footer">
        <p class="modal-footer-hint">Copy credentials above, or use persona quick pick on the main page for same-host sign-in.</p>
        <a class="btn-modal-open-zammad" href="{{ $u }}/" target="_blank" rel="noopener">Open Zammad</a>
      </div>
    </div>
  </div>

  <div class="toast" id="toast" role="status" aria-live="polite"></div>

  <script>
  (function() {
    var ZAMMAD_BASE = {{ $u | trimSuffix "/" | quote }};

    function showToast(msg) {
      var el = document.getElementById('toast');
      el.textContent = msg;
      el.classList.add('show');
      clearTimeout(showToast._t);
      showToast._t = setTimeout(function() { el.classList.remove('show'); }, 3800);
    }

    function copyText(text) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text);
      }
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); } finally { document.body.removeChild(ta); }
      return Promise.resolve();
    }

    function sameOriginAsZammad() {
      try {
        return new URL(ZAMMAD_BASE + '/').origin === window.location.origin;
      } catch (e) {
        return false;
      }
    }

    function signInToZammad(username, password) {
      var base = ZAMMAD_BASE + '/';
      var json = { 'Content-Type': 'application/json', Accept: 'application/json' };
      var signshow = new URL('api/v1/signshow', base);
      var signin = new URL('api/v1/signin', base);
      return fetch(signshow.toString(), {
        method: 'POST',
        credentials: 'include',
        headers: json,
        body: '{}'
      }).then(function(res) {
        var csrf = res.headers.get('csrf-token') || res.headers.get('CSRF-TOKEN');
        if (!csrf) {
          throw new Error('Could not read CSRF token. Is this demo site served on the same host as Zammad?');
        }
        return fetch(signin.toString(), {
          method: 'POST',
          credentials: 'include',
          headers: Object.assign({ 'X-CSRF-Token': csrf }, json),
          body: JSON.stringify({ username: username, password: password })
        });
      }).then(function(res) {
        if (res.status === 201) return;
        return res.text().then(function(t) {
          var j;
          try { j = t ? JSON.parse(t) : {}; } catch (e) { j = {}; }
          if (res.status === 422 && j && j.two_factor_required) {
            throw new Error('This account requires two-factor authentication. Use View all accounts to sign in manually.');
          }
          var msg = (j && (j.message || j.error || j.exception)) || t || res.statusText;
          throw new Error((msg && String(msg).trim()) || ('Sign-in failed (' + res.status + ')'));
        });
      });
    }

    var modal = document.getElementById('accounts-modal');

    function scrollAccountsBlock(id) {
      var el = id && document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function flashCopyButton(btn, kind) {
      btn.classList.remove('is-copied');
      void btn.offsetWidth;
      btn.classList.add('is-copied');
      var orig = btn.textContent;
      btn.textContent = kind === 'email' ? '✓ Email copied' : '✓ Password copied';
      clearTimeout(btn._copyFlash);
      btn._copyFlash = setTimeout(function() {
        btn.classList.remove('is-copied');
        btn.textContent = orig;
      }, 950);
    }

    function openAccountsModal(scrollToId) {
      if (!modal) return;
      modal.classList.add('is-open');
      modal.setAttribute('aria-hidden', 'false');
      document.body.classList.add('modal-open');
      if (!scrollToId) return;
      setTimeout(function() { scrollAccountsBlock(scrollToId); }, 0);
    }

    function closeAccountsModal() {
      if (!modal) return;
      modal.classList.remove('is-open');
      modal.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('modal-open');
    }

    function handleCredCopy(ev, root, sel, attr, kind, ok, err) {
      var btn = root.closest(sel);
      if (!btn) return false;
      ev.preventDefault();
      copyText(btn.getAttribute(attr) || '').then(function() {
        flashCopyButton(btn, kind);
        showToast(ok);
      }).catch(function() { showToast(err); });
      return true;
    }

    document.addEventListener('click', function(ev) {
      var t = ev.target;
      var root = t && t.nodeType === 1 ? t : t.parentElement;
      if (!root || !root.closest) return;

      if (root.closest('#btn-open-accounts-modal')) {
        openAccountsModal();
        return;
      }
      if (root.closest('#btn-close-accounts-modal')) {
        closeAccountsModal();
        return;
      }

      var chip = root.closest('.js-modal-scroll');
      if (chip) {
        scrollAccountsBlock(chip.getAttribute('data-target'));
        return;
      }

      if (handleCredCopy(ev, root, '.js-copy-email', 'data-email', 'email', 'Email copied', 'Could not copy email')) return;
      if (handleCredCopy(ev, root, '.js-copy-password', 'data-password', 'password', 'Password copied', 'Could not copy password')) return;

      var personaBtn = root.closest('.js-persona-signin');
      if (personaBtn) {
        var email = personaBtn.getAttribute('data-email') || '';
        var password = personaBtn.getAttribute('data-password') || '';
        var sectionId = personaBtn.getAttribute('data-section') || '';
        if (!sameOriginAsZammad()) {
          openAccountsModal(sectionId);
          showToast('One-click sign-in requires this demo site to be served on the same host as Zammad.');
          return;
        }
        personaBtn.classList.add('is-busy');
        personaBtn.setAttribute('aria-busy', 'true');
        signInToZammad(email, password).then(function() {
          window.open(ZAMMAD_BASE + '/#/', '_blank', 'noopener,noreferrer');
          showToast('Opened Zammad in a new tab.');
        }).catch(function(err) {
          openAccountsModal(sectionId);
          showToast((err && err.message) ? err.message : 'Sign-in failed. Use View all accounts to copy credentials.');
        }).finally(function() {
          personaBtn.classList.remove('is-busy');
          personaBtn.removeAttribute('aria-busy');
        });
      }
    });

    if (modal) {
      modal.addEventListener('click', function(e) {
        if (e.target === modal) closeAccountsModal();
      });
    }

    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && modal && modal.classList.contains('is-open')) {
        closeAccountsModal();
      }
    });
  })();
  </script>
</body>
</html>
{{- end }}
