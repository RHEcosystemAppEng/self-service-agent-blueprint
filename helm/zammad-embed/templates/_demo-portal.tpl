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
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ $product }} — Zammad demo login</title>
  <style>
    :root {
      --accent: #047857;
      --accent-hover: #059669;
      --text-muted: #64748b;
      --card: #ffffff;
      --border: #e2e8f0;
      --radius: 12px;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; margin: 0; }
    body {
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      color: #0f172a;
      overflow-x: hidden;
      background: #ffffff;
      min-height: 100vh;
    }
    .page {
      max-width: 36rem;
      margin: 0 auto;
      padding: 2rem 1.25rem 2.5rem;
    }
    @media (min-width: 480px) {
      .page { padding-top: 2.5rem; }
    }
    .page-header {
      text-align: center;
      margin-bottom: 1.75rem;
    }
    .page-header .brand {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 1.25rem;
      font-weight: 600;
      font-size: 1.05rem;
      color: #0f172a;
    }
    .page-header .brand span.icon {
      width: 40px;
      height: 40px;
      border-radius: 12px;
      background: linear-gradient(135deg, #dc2626, #b91c1c);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 1.15rem;
      color: #fff;
      box-shadow: 0 4px 14px -4px rgba(220, 38, 38, 0.45);
    }
    .page-header h1 {
      font-size: clamp(1.45rem, 4vw, 1.85rem);
      font-weight: 650;
      line-height: 1.25;
      margin: 0 0 0.65rem;
      color: #0f172a;
    }
    .page-header .lead {
      margin: 0 auto;
      font-size: 0.95rem;
      color: #64748b;
      max-width: 30ch;
      line-height: 1.55;
    }
    a.btn-hero-open {
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 1.5rem auto 0;
      padding: 1rem 1.75rem;
      font-size: 1.08rem;
      font-weight: 700;
      letter-spacing: 0.02em;
      color: #fff !important;
      background: linear-gradient(180deg, var(--accent-hover) 0%, var(--accent) 100%);
      border: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 14px;
      text-decoration: none;
      box-shadow: 0 8px 22px -6px rgba(5, 150, 105, 0.42), 0 2px 6px rgba(4, 120, 87, 0.18);
      transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
      width: 100%;
      max-width: 22rem;
    }
    a.btn-hero-open:hover {
      transform: translateY(-2px);
      filter: brightness(1.05);
      box-shadow: 0 12px 28px -6px rgba(5, 150, 105, 0.48), 0 4px 10px rgba(4, 120, 87, 0.22);
    }
    a.btn-hero-open:active {
      transform: translateY(0);
    }
    .hero-cta-note {
      margin: 0.65rem auto 0;
      font-size: 0.82rem;
      color: #94a3b8;
      max-width: 22rem;
    }
    .card {
      background: #fafafa;
      border-radius: var(--radius);
      border: 1px solid var(--border);
      padding: 1.25rem 1.35rem;
      margin-bottom: 1rem;
      box-shadow: 0 1px 2px rgba(15,23,42,0.04);
    }
    .card .hint {
      margin: 0 0 1rem;
      font-size: 0.85rem;
      color: var(--text-muted);
    }
    .card > h2 {
      margin: 0 0 0.5rem;
      font-size: 1.15rem;
    }
    nav.categories {
      display: flex;
      flex-wrap: wrap;
      gap: 0.45rem;
      margin-bottom: 0;
    }
    .persona-demo-label {
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.08em;
      color: var(--text-muted);
      margin: 0.25rem 0 0.75rem;
    }
    .persona-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(112px, 1fr));
      gap: 0.65rem;
    }
    .persona {
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      padding: 0.65rem 0.35rem;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: #ffffff;
      cursor: pointer;
      transition: border-color 0.15s, background 0.15s;
    }
    .persona:hover {
      border-color: var(--accent);
      background: #f0f7ff;
    }
    .persona .circle {
      width: 44px; height: 44px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.25rem;
      margin-bottom: 0.35rem;
    }
    .persona .name { font-size: 0.72rem; font-weight: 600; color: #334155; line-height: 1.2; }
    .persona .role { font-size: 0.65rem; color: var(--text-muted); margin-top: 0.15rem; }
    section.block {
      margin-bottom: 1.35rem;
      scroll-margin-top: 0.5rem;
    }
    section.block h3 {
      font-size: 0.95rem;
      margin: 0 0 0.65rem;
      color: #1e293b;
    }
    .table-wrap {
      width: 100%;
      overflow-x: auto;
      margin: 0;
    }
    table.accounts {
      width: 100%;
      table-layout: fixed;
      border-collapse: collapse;
      font-size: 0.82rem;
      min-width: 28rem;
    }
    table.accounts th:nth-child(1),
    table.accounts td:nth-child(1) { width: 13%; }
    table.accounts th:nth-child(2),
    table.accounts td:nth-child(2) { width: 32%; }
    table.accounts th:nth-child(3),
    table.accounts td:nth-child(3) { width: 18%; }
    table.accounts th:nth-child(4),
    table.accounts td:nth-child(4) { width: 37%; }
    table.accounts th, table.accounts td {
      text-align: left;
      padding: 0.5rem 0.5rem 0.5rem 0;
      padding-right: 0.65rem;
      border-bottom: 1px solid #f1f5f9;
      vertical-align: middle;
    }
    table.accounts thead th {
      color: var(--text-muted);
      font-weight: 600;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      border-bottom: 2px solid #e2e8f0;
      padding-top: 0.35rem;
    }
    table.accounts td.actions {
      text-align: left;
      vertical-align: middle;
      padding-left: 0.35rem;
    }
    table.accounts td.actions .btn { white-space: nowrap; }
    code.cred {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.78rem;
      word-break: break-all;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
    }
    button.btn, a.btn {
      font-size: 0.75rem;
      padding: 0.35rem 0.55rem;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: #fff;
      cursor: pointer;
      text-decoration: none;
      color: #334155;
      font-family: inherit;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
    }
    button.btn.primary, a.btn.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }
    button.btn.primary:hover, a.btn.primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
    button.btn:focus-visible, a.btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
    table.accounts td.actions button.btn.is-copied {
      animation: copyPop 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
      background: #ecfdf5 !important;
      border-color: #34d399 !important;
      color: #047857 !important;
      font-weight: 600;
    }
    @keyframes copyPop {
      0% { transform: scale(1); }
      35% { transform: scale(1.08); }
      100% { transform: scale(1); }
    }
    .toast {
      position: fixed;
      bottom: 1rem;
      left: 50%;
      transform: translateX(-50%) translateY(120%);
      background: #0f172a;
      color: #f8fafc;
      padding: 0.55rem 1rem;
      border-radius: 8px;
      font-size: 0.85rem;
      opacity: 0;
      transition: transform 0.25s, opacity 0.25s;
      z-index: 300;
      max-width: 90vw;
    }
    .toast.show {
      transform: translateX(-50%) translateY(0);
      opacity: 1;
    }
    body.modal-open {
      overflow: hidden;
    }
    .modal-open-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: stretch;
      margin-bottom: 1rem;
    }
    button.btn-view-all {
      width: 100%;
      font-size: 0.88rem;
      padding: 0.55rem 1rem;
      border-radius: 10px;
      font-weight: 600;
      background: #fff;
      border: 1px solid #cbd5e1;
      color: #475569;
      cursor: pointer;
      font-family: inherit;
      transition: border-color 0.15s, background 0.15s;
    }
    button.btn-view-all:hover {
      border-color: var(--accent);
      color: var(--accent);
      background: #f8fafc;
    }
    nav.categories button.category-chip {
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: #475569;
      padding: 0.4rem 0.65rem;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: #fff;
      cursor: pointer;
      font-family: inherit;
    }
    nav.categories button.category-chip:hover {
      border-color: var(--accent);
      color: var(--accent);
    }
    .modal-overlay {
      position: fixed;
      inset: 0;
      z-index: 250;
      background: rgba(15, 23, 42, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1rem;
      opacity: 0;
      visibility: hidden;
      transition: opacity 0.2s ease, visibility 0.2s ease;
    }
    .modal-overlay.is-open {
      opacity: 1;
      visibility: visible;
    }
    .modal-dialog {
      background: #fff;
      border-radius: 14px;
      width: min(720px, 100%);
      max-height: min(88vh, 920px);
      display: flex;
      flex-direction: column;
      box-shadow: 0 25px 50px -12px rgba(15, 23, 42, 0.35);
      border: 1px solid var(--border);
    }
    .modal-header {
      flex-shrink: 0;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      padding: 1rem 1.15rem;
      border-bottom: 1px solid var(--border);
    }
    .modal-header h2 {
      margin: 0;
      font-size: 1.1rem;
      font-weight: 650;
    }
    button.modal-close {
      border: none;
      background: #f1f5f9;
      width: 2.25rem;
      height: 2.25rem;
      border-radius: 8px;
      font-size: 1.35rem;
      line-height: 1;
      cursor: pointer;
      color: #475569;
      font-family: inherit;
    }
    button.modal-close:hover {
      background: #e2e8f0;
    }
    .modal-nav {
      flex-shrink: 0;
      padding: 0.6rem 1rem;
      border-bottom: 1px solid var(--border);
      background: #f8fafc;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }
    .modal-nav .categories {
      margin: 0;
      flex-wrap: nowrap;
      min-width: min-content;
    }
    .modal-body {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      padding: 1rem 1.15rem 1.35rem;
      -webkit-overflow-scrolling: touch;
    }
    .modal-body section.block:first-child h3 {
      margin-top: 0;
    }
    .modal-footer {
      flex-shrink: 0;
      padding: 1rem 1.15rem 1.15rem;
      border-top: 1px solid var(--border);
      background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
      text-align: center;
    }
    .modal-footer-hint {
      margin: 0 0 0.65rem;
      font-size: 0.82rem;
      color: #64748b;
    }
    a.btn-modal-open-zammad {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 100%;
      max-width: 20rem;
      margin: 0 auto;
      padding: 0.75rem 1.25rem;
      font-size: 1rem;
      font-weight: 700;
      border-radius: 12px;
      text-decoration: none;
      background: linear-gradient(180deg, var(--accent-hover) 0%, var(--accent) 100%);
      color: #fff !important;
      border: 1px solid rgba(255, 255, 255, 0.18);
      box-shadow: 0 6px 18px -4px rgba(5, 150, 105, 0.42);
      transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
    }
    a.btn-modal-open-zammad:hover {
      transform: translateY(-1px);
      filter: brightness(1.05);
      box-shadow: 0 8px 22px -4px rgba(5, 150, 105, 0.5);
    }
    section.block.persona-flash {
      animation: personaBgFlash 1.35s ease;
      border-radius: 10px;
    }
    @keyframes personaBgFlash {
      0%, 100% { background-color: transparent; }
      12% { background-color: #ecfdf5; }
      55% { background-color: #ecfdf5; }
    }
    .footer-links {
      font-size: 0.75rem;
      color: var(--text-muted);
      margin-top: 0.5rem;
      text-align: center;
    }
    .footer-links a { color: var(--accent); }
  </style>
</head>
<body>
  <div class="page">
    <header class="page-header">
      <div class="brand"><span class="icon" aria-hidden="true">⌂</span> {{ $product }}</div>
      <h1>{{ $hero }}</h1>
      <p class="lead">{{ $sub }}</p>
      <a class="btn-hero-open" href="{{ $u }}/" target="_blank" rel="noopener">Open Zammad</a>
      <p class="hero-cta-note">Opens the sign-in page in a new browser tab.</p>
    </header>

    <div class="card">
      <h2>Demo accounts</h2>
      <p class="hint">Tap a persona to see that account in a popup — copy email and password, then use <strong>Open Zammad</strong> above when you are ready.</p>
      <div class="modal-open-actions">
        <button type="button" class="btn-view-all" id="btn-open-accounts-modal">View all accounts &amp; passwords</button>
      </div>
      <p class="persona-demo-label">Persona quick pick</p>
      <div class="persona-grid" id="persona-grid"></div>
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
          <button type="button" class="category-chip js-modal-scroll" data-target="cat-admin">Admin</button>
          <button type="button" class="category-chip js-modal-scroll" data-target="cat-users">End users</button>
          <button type="button" class="category-chip js-modal-scroll" data-target="cat-managers">Managers</button>
          <button type="button" class="category-chip js-modal-scroll" data-target="cat-general">General handler</button>
          <button type="button" class="category-chip js-modal-scroll" data-target="cat-escalated">Escalated handler</button>
          <button type="button" class="category-chip js-modal-scroll" data-target="cat-specialist">Laptop specialist</button>
        </nav>
      </div>
      <div class="modal-body" id="accounts-modal-body">
        <section class="block" id="cat-admin">
          <h3>Admin</h3>
          <div class="table-wrap"><table class="accounts">
            <thead><tr><th>Role</th><th>Email</th><th>Password</th><th>Copy</th></tr></thead>
            <tbody>
              <tr>
                <td>Administrator</td>
                <td><code class="cred">admin@zammad.local</code></td>
                <td><code class="cred pw" data-pw="ZammadR0cks!">ZammadR0cks!</code></td>
                <td class="actions"><button type="button" class="btn js-copy-email" data-email="admin@zammad.local">Copy email</button><button type="button" class="btn js-copy-password" data-password="ZammadR0cks!">Copy password</button></td>
              </tr>
            </tbody>
          </table></div>
        </section>

        <section class="block" id="cat-users">
          <h3>End users (customers)</h3>
          <div class="table-wrap"><table class="accounts">
            <thead><tr><th>Role</th><th>Email</th><th>Password</th><th>Copy</th></tr></thead>
            <tbody>
              <tr>
                <td>Customer</td>
                <td><code class="cred">alice.johnson@company.com</code></td>
                <td><code class="cred">ChangeMe123!</code></td>
                <td class="actions"><button type="button" class="btn js-copy-email" data-email="alice.johnson@company.com">Copy email</button><button type="button" class="btn js-copy-password" data-password="ChangeMe123!">Copy password</button></td>
              </tr>
              <tr>
                <td>Customer</td>
                <td><code class="cred">john.doe@company.com</code></td>
                <td><code class="cred">ChangeMe123!</code></td>
                <td class="actions"><button type="button" class="btn js-copy-email" data-email="john.doe@company.com">Copy email</button><button type="button" class="btn js-copy-password" data-password="ChangeMe123!">Copy password</button></td>
              </tr>
            </tbody>
          </table></div>
        </section>

        <section class="block" id="cat-managers">
          <h3>Managers</h3>
          <div class="table-wrap"><table class="accounts">
            <thead><tr><th>Role</th><th>Email</th><th>Password</th><th>Copy</th></tr></thead>
            <tbody>
              <tr>
                <td>Manager agent</td>
                <td><code class="cred">manager1@example.com</code></td>
                <td><code class="cred">ChangeMe123!</code></td>
                <td class="actions"><button type="button" class="btn js-copy-email" data-email="manager1@example.com">Copy email</button><button type="button" class="btn js-copy-password" data-password="ChangeMe123!">Copy password</button></td>
              </tr>
              <tr>
                <td>Manager agent</td>
                <td><code class="cred">manager2@example.com</code></td>
                <td><code class="cred">ChangeMe123!</code></td>
                <td class="actions"><button type="button" class="btn js-copy-email" data-email="manager2@example.com">Copy email</button><button type="button" class="btn js-copy-password" data-password="ChangeMe123!">Copy password</button></td>
              </tr>
            </tbody>
          </table></div>
        </section>

        <section class="block" id="cat-general">
          <h3>General ticket handlers</h3>
          <div class="table-wrap"><table class="accounts">
            <thead><tr><th>Role</th><th>Email</th><th>Password</th><th>Copy</th></tr></thead>
            <tbody>
              <tr>
                <td>Agent</td>
                <td><code class="cred">ticket_handler1@example.com</code></td>
                <td><code class="cred">ChangeMe123!</code></td>
                <td class="actions"><button type="button" class="btn js-copy-email" data-email="ticket_handler1@example.com">Copy email</button><button type="button" class="btn js-copy-password" data-password="ChangeMe123!">Copy password</button></td>
              </tr>
              <tr>
                <td>Agent</td>
                <td><code class="cred">ticket_handler2@example.com</code></td>
                <td><code class="cred">ChangeMe123!</code></td>
                <td class="actions"><button type="button" class="btn js-copy-email" data-email="ticket_handler2@example.com">Copy email</button><button type="button" class="btn js-copy-password" data-password="ChangeMe123!">Copy password</button></td>
              </tr>
            </tbody>
          </table></div>
        </section>

        <section class="block" id="cat-escalated">
          <h3>Escalated laptop refresh handlers</h3>
          <div class="table-wrap"><table class="accounts">
            <thead><tr><th>Role</th><th>Email</th><th>Password</th><th>Copy</th></tr></thead>
            <tbody>
              <tr>
                <td>Agent</td>
                <td><code class="cred">escalated_laptop_refresh_handler1@example.com</code></td>
                <td><code class="cred">ChangeMe123!</code></td>
                <td class="actions"><button type="button" class="btn js-copy-email" data-email="escalated_laptop_refresh_handler1@example.com">Copy email</button><button type="button" class="btn js-copy-password" data-password="ChangeMe123!">Copy password</button></td>
              </tr>
              <tr>
                <td>Agent</td>
                <td><code class="cred">escalated_laptop_refresh_handler2@example.com</code></td>
                <td><code class="cred">ChangeMe123!</code></td>
                <td class="actions"><button type="button" class="btn js-copy-email" data-email="escalated_laptop_refresh_handler2@example.com">Copy email</button><button type="button" class="btn js-copy-password" data-password="ChangeMe123!">Copy password</button></td>
              </tr>
            </tbody>
          </table></div>
        </section>

        <section class="block" id="cat-specialist">
          <h3>Laptop specialist</h3>
          <div class="table-wrap"><table class="accounts">
            <thead><tr><th>Role</th><th>Email</th><th>Password</th><th>Copy</th></tr></thead>
            <tbody>
              <tr>
                <td>Agent</td>
                <td><code class="cred">agent.laptop-specialist@example.com</code></td>
                <td><code class="cred">ChangeMe123!</code></td>
                <td class="actions"><button type="button" class="btn js-copy-email" data-email="agent.laptop-specialist@example.com">Copy email</button><button type="button" class="btn js-copy-password" data-password="ChangeMe123!">Copy password</button></td>
              </tr>
            </tbody>
          </table></div>
        </section>
      </div>
      <div class="modal-footer">
        <p class="modal-footer-hint">Copy what you need above, then sign in:</p>
        <a class="btn-modal-open-zammad" href="{{ $u }}/" target="_blank" rel="noopener">Open Zammad</a>
      </div>
    </div>
  </div>

  <div class="toast" id="toast" role="status" aria-live="polite"></div>

  <script>
  (function() {
    function showToast(msg) {
      var el = document.getElementById('toast');
      el.textContent = msg;
      el.classList.add('show');
      clearTimeout(showToast._t);
      showToast._t = setTimeout(function() { el.classList.remove('show'); }, 2800);
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

    var modal = document.getElementById('accounts-modal');
    var modalBody = document.getElementById('accounts-modal-body');

    function flashSection(id) {
      if (!id) return;
      var el = document.getElementById(id);
      if (!el) return;
      el.classList.remove('persona-flash');
      void el.offsetWidth;
      el.classList.add('persona-flash');
      setTimeout(function() { el.classList.remove('persona-flash'); }, 1400);
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
      if (scrollToId) {
        requestAnimationFrame(function() {
          requestAnimationFrame(function() {
            var el = document.getElementById(scrollToId);
            if (el && modalBody) {
              el.scrollIntoView({ behavior: 'smooth', block: 'start' });
              setTimeout(function() { flashSection(scrollToId); }, 280);
            }
          });
        });
      }
    }

    function closeAccountsModal() {
      if (!modal) return;
      modal.classList.remove('is-open');
      modal.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('modal-open');
    }

    var btnOpen = document.getElementById('btn-open-accounts-modal');
    if (btnOpen) btnOpen.addEventListener('click', function() { openAccountsModal(null); });

    document.querySelectorAll('.js-modal-jump').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var id = btn.getAttribute('data-target');
        openAccountsModal(id);
      });
    });

    document.querySelectorAll('.js-modal-scroll').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var id = btn.getAttribute('data-target');
        var el = id ? document.getElementById(id) : null;
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });

    var btnClose = document.getElementById('btn-close-accounts-modal');
    if (btnClose) btnClose.addEventListener('click', closeAccountsModal);

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

    document.querySelectorAll('.js-copy-email').forEach(function(btn) {
      btn.addEventListener('click', function(ev) {
        ev.stopPropagation();
        var v = btn.getAttribute('data-email') || '';
        copyText(v).then(function() {
          flashCopyButton(btn, 'email');
          showToast('Email copied');
        }).catch(function() { showToast('Could not copy email'); });
      });
    });
    document.querySelectorAll('.js-copy-password').forEach(function(btn) {
      btn.addEventListener('click', function(ev) {
        ev.stopPropagation();
        var v = btn.getAttribute('data-password') || '';
        copyText(v).then(function() {
          flashCopyButton(btn, 'password');
          showToast('Password copied');
        }).catch(function() { showToast('Could not copy password'); });
      });
    });

    var personas = [
      { icon: '🛡️', bg: '#dbeafe', name: 'Admin', role: 'Full admin', email: 'admin@zammad.local', password: 'ZammadR0cks!', anchor: '#cat-admin' },
      { icon: '👤', bg: '#dcfce7', name: 'Alice', role: 'Customer', email: 'alice.johnson@company.com', password: 'ChangeMe123!', anchor: '#cat-users' },
      { icon: '👤', bg: '#e0e7ff', name: 'John', role: 'Customer', email: 'john.doe@company.com', password: 'ChangeMe123!', anchor: '#cat-users' },
      { icon: '💼', bg: '#fce7f3', name: 'Manager 1', role: 'Manager', email: 'manager1@example.com', password: 'ChangeMe123!', anchor: '#cat-managers' },
      { icon: '🎫', bg: '#fef3c7', name: 'Handler', role: 'General queue', email: 'ticket_handler1@example.com', password: 'ChangeMe123!', anchor: '#cat-general' },
      { icon: '⚡', bg: '#ffedd5', name: 'Escalated', role: 'Laptop refresh', email: 'escalated_laptop_refresh_handler1@example.com', password: 'ChangeMe123!', anchor: '#cat-escalated' },
      { icon: '💻', bg: '#ccfbf1', name: 'Specialist', role: 'Laptop', email: 'agent.laptop-specialist@example.com', password: 'ChangeMe123!', anchor: '#cat-specialist' }
    ];

    var grid = document.getElementById('persona-grid');
    if (grid) {
      personas.forEach(function(p) {
        var div = document.createElement('button');
        div.type = 'button';
        div.className = 'persona';
        div.setAttribute('aria-label', p.name + ' — ' + p.role);
        div.innerHTML = '<span class="circle" style="background:' + p.bg + '">' + p.icon + '</span>' +
          '<span class="name">' + p.name + '</span><span class="role">' + p.role + '</span>';
        div.addEventListener('click', function() {
          var anchorId = (p.anchor || '').replace(/^#/, '');
          openAccountsModal(anchorId || null);
          showToast('Copy email & password below, then tap Open Zammad.');
        });
        grid.appendChild(div);
      });
    }
  })();
  </script>
</body>
</html>
{{- end }}
