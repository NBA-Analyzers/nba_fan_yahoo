// Chat page: one conversation at a time, a fresh session per "New chat".
const leagueId = window.LEAGUE_ID || null;
const messages = document.getElementById("chatMessages");
const emptyState = document.getElementById("emptyState");
const composer = document.getElementById("composer");
const input = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");

let sessionId = newSessionId();
let busy = false;

function newSessionId() {
  return window.crypto && crypto.randomUUID
    ? crypto.randomUUID()
    : "session_" + Math.random().toString(36).slice(2) + "_" + Date.now();
}

function addMessage(kind, html) {
  emptyState.hidden = true;
  const div = document.createElement("div");
  div.className = "msg " + kind;
  div.innerHTML = html;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// Light Markdown: headings, bullet and numbered lists, bold, italics, inline code
function inline(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\s][^*]*?)\*(?!\*)/g, "$1<em>$2</em>");
}

function formatAnswer(text) {
  const out = [];
  let list = null;
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  let para = [];
  const closePara = () => { if (para.length) { out.push(`<p>${para.join("<br>")}</p>`); para = []; } };

  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    let m;
    if (!line) { closePara(); closeList(); continue; }
    if ((m = line.match(/^#{1,6}\s+(.*)$/))) {
      closePara(); closeList();
      out.push(`<h4>${inline(m[1])}</h4>`);
    } else if ((m = line.match(/^[-•*]\s+(.*)$/))) {
      closePara();
      if (list !== "ul") { closeList(); out.push("<ul>"); list = "ul"; }
      out.push(`<li>${inline(m[1])}</li>`);
    } else if ((m = line.match(/^\d+[.)]\s+(.*)$/))) {
      closePara();
      if (list !== "ol") { closeList(); out.push("<ol>"); list = "ol"; }
      out.push(`<li>${inline(m[1])}</li>`);
    } else {
      closeList();
      para.push(inline(line));
    }
  }
  closePara(); closeList();
  return out.join("");
}

function setBusy(value) {
  busy = value;
  sendButton.disabled = value;
}

async function failure(res) {
  if (res.status === 401) return new Error("Your sign-in has expired. Please refresh the page and sign in again.");
  let message = "Something went wrong. Please try again.";
  try { message = JSON.parse(await res.text()).error || message; } catch (e) {}
  return new Error(message);
}

// The answer arrives as it is written: one JSON object per line ({delta}, then {done} or {error}).
// `onText` gets the whole answer so far each time it grows.
async function ask(question, onText) {
  const res = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, user_message: question, league_id: leagueId, stream: true }),
  });
  if (!res.ok) throw await failure(res);
  if (!res.body || !res.body.getReader) return res.text();  // an old browser: no streaming
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "", answer = "", finished = false;
  const handle = (line) => {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    if (event.error) throw new Error(event.error);
    if (event.delta) { answer += event.delta; onText(answer); }
    if (event.done) finished = true;
  };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    lines.forEach(handle);
  }
  handle(buffer);
  if (!finished && !answer) throw new Error("The answer was cut off. Please try again.");
  return answer;
}

async function send(question) {
  question = question.trim();
  if (!question || busy) return;
  addMessage("user", escapeHtml(question));
  input.value = "";
  autoGrow();
  setBusy(true);
  const typing = addMessage("bot", '<span class="typing" aria-label="Thinking"><span></span><span></span><span></span></span>');
  try {
    const answer = await ask(question, (text) => {
      typing.innerHTML = formatAnswer(text);
      messages.scrollTop = messages.scrollHeight;
    });
    typing.innerHTML = formatAnswer(answer);
  } catch (e) {
    typing.remove();
    addMessage("note", escapeHtml(e.message));
  } finally {
    setBusy(false);
    messages.scrollTop = messages.scrollHeight;
    input.focus();
  }
}

function newChat() {
  sessionId = newSessionId();
  messages.querySelectorAll(".msg").forEach((m) => m.remove());
  emptyState.hidden = false;
  input.focus();
}

function autoGrow() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 160) + "px";
}

composer.addEventListener("submit", (e) => { e.preventDefault(); send(input.value); });
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(input.value); }
});
input.addEventListener("input", autoGrow);
document.getElementById("newChatButton").addEventListener("click", newChat);
document.querySelectorAll(".suggestion").forEach((b) => b.addEventListener("click", () => send(b.textContent)));
input.focus();
