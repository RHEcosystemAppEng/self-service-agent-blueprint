{{- define "zammad-embed.demoPortalIndex" -}}
{{- $u := .zammadUrl -}}
{{- $product := "IT Self-Service" -}}
{{- $hero := "Sign in to Zammad" -}}
{{- $sub := "Use the demo accounts below with the live Zammad UI." -}}
{{- if .Values.demoPortal -}}
{{-   $product = default $product .Values.demoPortal.productName -}}
{{-   $hero = default $hero .Values.demoPortal.heroTitle -}}
{{-   $sub = default $sub .Values.demoPortal.heroSubtitle -}}
{{- end -}}
{{- $categories := .Values.demoPortal.categories | default list -}}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ $product }} - Zammad demo login</title>
  <style>
    :root {
      --accent: #047857;
      --accent-hover: #059669;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --radius: 12px;
    }
    * { box-sizing: border-box; }
    html { font-size: clamp(16px, 1.15vw + 14px, 21px); }
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
        grid-template-columns: minmax(14rem, 20vw) minmax(0, 2.5fr);
        gap: 1.5rem;
        align-items: start;
      }
      .dashboard-hero { position: sticky; top: 0.75rem; }
      .page-header { text-align: left; }
      .footer-links { text-align: left; }
    }
    .page-header { text-align: center; }
    .page-header .brand {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 0.5rem;
      font-weight: 600;
      font-size: 1.12rem;
    }
    .page-header .brand span.icon {
      width: 2.75rem;
      height: 2.75rem;
      border-radius: 12px;
      background: linear-gradient(135deg, #dc2626, #b91c1c);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: #fff;
    }
    .page-header h1 { font-size: 1.65rem; margin: 0 0 0.35rem; font-weight: 650; }
    .page-header .lead { margin: 0 auto; color: var(--text-muted); max-width: 42ch; font-size: 1.02rem; }
    a.btn-hero-open {
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0.75rem auto 0;
      padding: 0.72rem 1.35rem;
      font-size: 1.06rem;
      font-weight: 700;
      color: #fff !important;
      background: var(--accent);
      border-radius: 12px;
      text-decoration: none;
      width: 100%;
    }
    a.btn-hero-open:hover { background: var(--accent-hover); }
    .card {
      background: #fafafa;
      border-radius: var(--radius);
      border: 1px solid var(--border);
      padding: 1.1rem 1.2rem;
      margin-bottom: 0.65rem;
    }
    .card .hint { margin: 0 0 0.5rem; font-size: 0.96rem; color: var(--text-muted); }
    .card > h2 { margin: 0 0 0.35rem; font-size: 1.22rem; }
    .persona-demo-label {
      font-size: 0.82rem;
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
      border-radius: 12px;
      background: #fff;
      min-width: 0;
    }
    .persona-group-heading {
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--text-muted);
      margin: 0;
      padding-bottom: 0.35rem;
      border-bottom: 1px solid #f1f5f9;
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
      width: 2.85rem;
      height: 2.85rem;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.38rem;
      margin-bottom: 0.25rem;
    }
    .persona .name { font-size: 0.88rem; font-weight: 600; color: #334155; }
    .persona .role { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.1rem; }
    section.block { margin-bottom: 1.25rem; scroll-margin-top: 0.5rem; }
    section.block h3 { font-size: 1.1rem; margin: 0 0 0.5rem; color: #1e293b; }
    .table-wrap { overflow-x: auto; margin: 0; }
    table.accounts {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.94rem;
      min-width: 30rem;
    }
    table.accounts th, table.accounts td {
      text-align: left;
      padding: 0.5rem 0.55rem 0.5rem 0;
      border-bottom: 1px solid #f1f5f9;
      vertical-align: middle;
    }
    table.accounts thead th {
      color: var(--text-muted);
      font-weight: 600;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      border-bottom: 2px solid #e2e8f0;
    }
    table.accounts td.actions { padding-left: 0.35rem; }
    table.accounts td.actions .btn { white-space: nowrap; }
    code.cred {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.91rem;
      word-break: break-all;
    }
    .actions { display: flex; flex-wrap: wrap; gap: 0.35rem; }
    button.btn, a.btn {
      font-size: 0.91rem;
      padding: 0.4rem 0.62rem;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: #fff;
      cursor: pointer;
      color: #334155;
      font-family: inherit;
    }
    button.btn.primary, a.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
    button.btn.primary:hover, a.btn.primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
    button.btn:focus-visible, a.btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
    table.accounts td.actions button.btn.is-copied {
      background: #ecfdf5;
      border-color: #34d399;
      color: #047857;
      font-weight: 600;
    }
    .toast {
      position: fixed;
      bottom: 1rem;
      left: 50%;
      transform: translateX(-50%) translateY(120%);
      background: #0f172a;
      color: #f8fafc;
      padding: 0.58rem 1.05rem;
      border-radius: 10px;
      font-size: 0.95rem;
      opacity: 0;
      transition: transform 0.2s, opacity 0.2s;
      z-index: 300;
      max-width: 90vw;
    }
    .toast.show { transform: translateX(-50%) translateY(0); opacity: 1; }
    body.modal-open { overflow: hidden; }
    .modal-open-actions { margin-bottom: 0.5rem; }
    button.btn-view-all {
      width: 100%;
      padding: 0.55rem 0.95rem;
      border-radius: 10px;
      font-size: 0.98rem;
      font-weight: 600;
      background: #fff;
      border: 1px solid #cbd5e1;
      color: #475569;
      cursor: pointer;
      font-family: inherit;
    }
    button.btn-view-all:hover { border-color: var(--accent); color: var(--accent); }
    nav.categories { display: flex; flex-wrap: wrap; gap: 0.45rem; }
    nav.categories button.category-chip {
      font-size: 0.76rem;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: #475569;
      padding: 0.35rem 0.55rem;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: #fff;
      cursor: pointer;
      font-family: inherit;
    }
    nav.categories button.category-chip:hover { border-color: var(--accent); color: var(--accent); }
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
    .modal-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.85rem 1rem;
      border-bottom: 1px solid var(--border);
    }
    .modal-header h2 { margin: 0; font-size: 1.14rem; font-weight: 650; }
    button.modal-close {
      border: none;
      background: #f1f5f9;
      width: 2.35rem;
      height: 2.35rem;
      border-radius: 8px;
      font-size: 1.35rem;
      cursor: pointer;
      color: #475569;
      font-family: inherit;
    }
    .modal-nav {
      padding: 0.5rem 0.85rem;
      border-bottom: 1px solid var(--border);
      background: #f8fafc;
      overflow-x: auto;
    }
    .modal-nav .categories { margin: 0; flex-wrap: nowrap; min-width: min-content; }
    .modal-body {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      padding: 0.85rem 1rem 1.1rem;
    }
    .modal-footer {
      padding: 0.85rem 1rem;
      border-top: 1px solid var(--border);
      background: #f8fafc;
      text-align: center;
    }
    .modal-footer-hint { margin: 0 0 0.5rem; font-size: 0.86rem; color: #64748b; }
    a.btn-modal-open-zammad {
      display: inline-flex;
      justify-content: center;
      width: 100%;
      max-width: 18rem;
      margin: 0 auto;
      padding: 0.65rem 1.1rem;
      font-size: 1.06rem;
      font-weight: 700;
      border-radius: 10px;
      text-decoration: none;
      background: var(--accent);
      color: #fff !important;
    }
    a.btn-modal-open-zammad:hover { background: var(--accent-hover); }
    .footer-links { font-size: 0.93rem; color: var(--text-muted); margin-top: 0.75rem; text-align: center; }
    .footer-links a { color: var(--accent); }
  </style>
</head>
<body>
  <div class="page page-dashboard">
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
          <div class="modal-open-actions">
            <button type="button" class="btn-view-all" id="btn-open-accounts-modal">View all accounts &amp; passwords</button>
          </div>
          <p class="persona-demo-label">Persona quick pick</p>
          <div class="persona-grid" id="persona-grid">
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
      <a href="chat-embed.html">Chat widget embed snippet</a>
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
      <div class="modal-body" id="accounts-modal-body">
{{- range $categories }}
        <section class="block" id="{{ .id }}">
          <h3>{{ .sectionTitle }}</h3>
          <div class="table-wrap"><table class="accounts">
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

    function zammadApiOrigin() {
      try { return new URL(ZAMMAD_BASE + '/').origin; } catch (e) { return ''; }
    }

    function sameOriginAsZammad() {
      var o = zammadApiOrigin();
      return !!o && o === window.location.origin;
    }

    function signInToZammad(username, password) {
      var base = ZAMMAD_BASE + '/';
      var signshow = new URL('api/v1/signshow', base);
      var signin = new URL('api/v1/signin', base);
      return fetch(signshow.toString(), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: '{}'
      }).then(function(res) {
        var csrf = res.headers.get('csrf-token') || res.headers.get('CSRF-TOKEN');
        if (!csrf) {
          throw new Error('Could not read CSRF token. Is the demo served on the same host as Zammad?');
        }
        return fetch(signin.toString(), {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
            'X-CSRF-Token': csrf
          },
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
    var modalBody = document.getElementById('accounts-modal-body');

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
      setTimeout(function() {
        var el = document.getElementById(scrollToId);
        if (el && modalBody) {
          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }, 0);
    }

    function closeAccountsModal() {
      if (!modal) return;
      modal.classList.remove('is-open');
      modal.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('modal-open');
    }

    function clickRoot(ev) {
      return ev.target instanceof Element ? ev.target : ev.target.parentElement;
    }

    document.addEventListener('click', function(ev) {
      var root = clickRoot(ev);
      if (!root || !root.closest) return;

      if (root.closest('#btn-open-accounts-modal')) {
        openAccountsModal(null);
        return;
      }
      if (root.closest('#btn-close-accounts-modal')) {
        closeAccountsModal();
        return;
      }

      var chip = root.closest('.js-modal-scroll');
      if (chip) {
        var tid = chip.getAttribute('data-target');
        var sec = tid ? document.getElementById(tid) : null;
        if (sec) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
      }

      var ce = root.closest('.js-copy-email');
      if (ce) {
        ev.preventDefault();
        copyText(ce.getAttribute('data-email') || '').then(function() {
          flashCopyButton(ce, 'email');
          showToast('Email copied');
        }).catch(function() { showToast('Could not copy email'); });
        return;
      }

      var cp = root.closest('.js-copy-password');
      if (cp) {
        ev.preventDefault();
        copyText(cp.getAttribute('data-password') || '').then(function() {
          flashCopyButton(cp, 'password');
          showToast('Password copied');
        }).catch(function() { showToast('Could not copy password'); });
        return;
      }

      var personaBtn = root.closest('.js-persona-signin');
      if (personaBtn) {
        var email = personaBtn.getAttribute('data-email') || '';
        var password = personaBtn.getAttribute('data-password') || '';
        var sectionId = personaBtn.getAttribute('data-section') || '';
        if (!sameOriginAsZammad()) {
          openAccountsModal(sectionId || null);
          showToast('One-click sign-in needs this page on the same host as Zammad (e.g. …/demo-portal/). Use copy below or deploy path-based Routes.');
          return;
        }
        personaBtn.classList.add('is-busy');
        personaBtn.setAttribute('aria-busy', 'true');
        signInToZammad(email, password).then(function() {
          personaBtn.classList.remove('is-busy');
          personaBtn.removeAttribute('aria-busy');
          window.open(ZAMMAD_BASE + '/#/', '_blank', 'noopener,noreferrer');
          showToast('Opened Zammad in a new tab.');
        }).catch(function(err) {
          personaBtn.classList.remove('is-busy');
          personaBtn.removeAttribute('aria-busy');
          openAccountsModal(sectionId || null);
          showToast((err && err.message) ? err.message : 'Sign-in failed. Use View all accounts to copy credentials.');
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
