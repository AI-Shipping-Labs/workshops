const log = document.getElementById('log');
const form = document.getElementById('form');
const input = document.getElementById('q');
const button = form.querySelector('button');

function scrollToBottom() {
  log.scrollTop = log.scrollHeight;
}

function addNode(cls, text = '') {
  const node = document.createElement('div');
  node.className = cls;
  node.textContent = text;
  log.appendChild(node);
  scrollToBottom();
  return node;
}

function addToolNode(name, args) {
  const details = document.createElement('details');
  details.className = 'tool';
  details.open = false;

  const summary = document.createElement('summary');
  const title = document.createElement('span');
  title.className = 'tool-title';
  title.textContent = `${name}(${JSON.stringify(args)})`;
  const status = document.createElement('span');
  status.className = 'tool-status';
  status.textContent = 'running…';
  summary.appendChild(title);
  summary.appendChild(status);
  details.appendChild(summary);

  const pre = document.createElement('pre');
  pre.textContent = '';
  details.appendChild(pre);

  log.appendChild(details);
  scrollToBottom();
  return { details, status, pre };
}

function parseSSE(buffer) {
  const events = [];
  const chunks = buffer.split('\n\n');
  const remainder = chunks.pop();
  for (const raw of chunks) {
    if (!raw.trim()) continue;
    const lines = raw.split('\n');
    const event = lines.find((l) => l.startsWith('event: '))?.slice(7);
    const data = lines.find((l) => l.startsWith('data: '))?.slice(6);
    if (event && data) events.push({ event, data: JSON.parse(data) });
  }
  return { events, remainder };
}

async function ask(question) {
  addNode('user', question);
  const thinking = addNode('status', 'thinking…');

  let answerNode = null;
  let pendingTool = null;

  const res = await fetch('/ask/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  });

  if (!res.ok) {
    thinking.remove();
    addNode('assistant', `Error: ${res.status} ${res.statusText}`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const { events, remainder } = parseSSE(buffer);
    buffer = remainder;

    for (const { event, data } of events) {
      if (event === 'token') {
        thinking.remove();
        if (!answerNode) answerNode = addNode('assistant');
        answerNode.textContent += data.delta;
        scrollToBottom();
      } else if (event === 'tool_call') {
        thinking.remove();
        answerNode = null;
        pendingTool = addToolNode(data.name, data.arguments);
      } else if (event === 'tool_result') {
        if (pendingTool) {
          pendingTool.status.textContent = Array.isArray(data.result)
            ? `${data.result.length} hits`
            : 'done';
          pendingTool.pre.textContent = JSON.stringify(data.result, null, 2);
          pendingTool = null;
        }
      } else if (event === 'iteration') {
        // optional — noisy, skip for now
      } else if (event === 'done') {
        thinking.remove();
      }
    }
  }

  thinking.remove();
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (!q) return;
  input.value = '';
  button.disabled = true;
  try {
    await ask(q);
  } finally {
    button.disabled = false;
    input.focus();
  }
});
