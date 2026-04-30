{{- define "zammad-demo-site.chatSnippetPage" -}}
{{- $zammadUrl := .zammadUrl -}}
{{- $chatId := .Values.chatId | default 1 -}}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Zammad Chat snippet</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 680px; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; }
    pre { background: #f5f5f5; padding: 1rem; overflow-x: auto; border-radius: 4px; }
    code { font-size: 0.9em; }
    h1 { font-size: 1.25rem; }
    #demo-site-chat-debug { white-space: pre-wrap; font-size: 0.85rem; background: #1e1e1e; color: #d4d4d4; padding: 1rem; border-radius: 4px; max-height: 14rem; overflow: auto; }
  </style>
</head>
<body>
  <p><a href="index.html">← Demo site home</a></p>
  <h1>Zammad Chat snippet</h1>
  <p>Copy the following code into your website before the closing <code>&lt;/body&gt;</code> tag:</p>
  <pre><code>&lt;script src="{{ $zammadUrl }}/assets/chat/chat-no-jquery.min.js"&gt;&lt;/script&gt;
&lt;script&gt;
(function() { new ZammadChat({{ "{" }} fontSize: '12px', chatId: {{ $chatId }} {{ "}" }}); })();
&lt;/script&gt;</code></pre>
  <p><strong>Chat button missing?</strong> An agent must be <em>available for chat</em> in Zammad (Chat panel, online). See <a href="https://admin-docs.zammad.org/en/latest/channels/chat.html">Zammad Chat docs</a>. If the channel restricts origins, add this page&apos;s origin (scheme + host).</p>
  <hr style="margin: 2rem 0; border: none; border-top: 1px solid #ddd;">
  <h2>Live preview</h2>
  <p>Scripts below load the widget from <code>{{ $zammadUrl }}</code> (debug log + browser console).</p>
  <pre id="demo-site-chat-debug"></pre>
  <script src="{{ $zammadUrl }}/assets/chat/chat-no-jquery.min.js"></script>
  <script>
  (function() {
    var el = document.getElementById('demo-site-chat-debug');
    function log(m) {
      if (!el) return;
      var t = (typeof m === 'string') ? m : (m && m.message ? m.message : JSON.stringify(m));
      el.textContent += t + '\n';
    }
    new ZammadChat({
      fontSize: '12px',
      chatId: {{ $chatId }},
      debug: true,
      onError: function(m) { log('onError: ' + (m || '(empty)')); },
      onReady: function() { log('onReady'); },
      onConnectionEstablished: function() { log('onConnectionEstablished'); }
    });
  })();
  </script>
</body>
</html>
{{- end }}
