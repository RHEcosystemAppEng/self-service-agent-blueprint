{{- define "zammad-embed.chatEmbedPage" -}}
{{- $zammadUrl := .zammadUrl -}}
{{- $chatId := .Values.chatId | default 1 -}}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Zammad Chat Embed</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 680px; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; }
    pre { background: #f5f5f5; padding: 1rem; overflow-x: auto; border-radius: 4px; }
    code { font-size: 0.9em; }
    h1 { font-size: 1.25rem; }
    #zammad-embed-debug { white-space: pre-wrap; font-size: 0.85rem; background: #1e1e1e; color: #d4d4d4; padding: 1rem; border-radius: 4px; max-height: 14rem; overflow: auto; }
  </style>
</head>
<body>
  <p><a href="index.html">← Demo login portal</a></p>
  <h1>Zammad Chat - Embed Code</h1>
  <p>Copy the following code into your website before the closing <code>&lt;/body&gt;</code> tag:</p>
  <pre><code>&lt;script src="{{ $zammadUrl }}/assets/chat/chat-no-jquery.min.js"&gt;&lt;/script&gt;
&lt;script&gt;
(function() { new ZammadChat({{ "{" }} fontSize: '12px', chatId: {{ $chatId }} {{ "}" }}); })();
&lt;/script&gt;</code></pre>
  <p><strong>Why the button may stay hidden:</strong> Zammad only shows the widget when at least one agent is <em>available for chat</em> (has capacity). Turning the channel on under Admin → Channels → Chat is not enough: log in as an agent, open the <strong>Chat</strong> panel in Zammad, set your max concurrent chats, and put yourself <strong>online / available for chat</strong>. See <a href="https://admin-docs.zammad.org/en/latest/channels/chat.html">Zammad Chat documentation</a>.</p>
  <p><strong>Allowed websites:</strong> If you set allowed websites on the chat channel, include this page&apos;s origin (scheme + host). If that field is empty, all origins are allowed.</p>
  <hr style="margin: 2rem 0; border: none; border-top: 1px solid #ddd;">
  <h2>Live preview</h2>
  <p>The snippet in the grey box is escaped for copy-paste only. Scripts below load the real widget from <code>{{ $zammadUrl }}</code> (chatId {{ $chatId }}).</p>
  <p><strong>Widget debug log</strong> (also see the browser console):</p>
  <pre id="zammad-embed-debug"></pre>
  <script src="{{ $zammadUrl }}/assets/chat/chat-no-jquery.min.js"></script>
  <script>
  (function() {
    var el = document.getElementById('zammad-embed-debug');
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
      onReady: function() {
        log('onReady: WebSocket/CSS path ok. If you still see no chat button, Zammad reports no agent available for this chat (offline queue) — see note above.');
      },
      onConnectionEstablished: function() { log('onConnectionEstablished'); }
    });
  })();
  </script>
</body>
</html>
{{- end }}
