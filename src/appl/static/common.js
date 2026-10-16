// Helpers shared by the draft, season and manual-league pages. Load this before the page's own script.

const $ = (id) => document.getElementById(id);

const el = (tag, text, cls) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
};

const SIGNIN_EXPIRED = "Your sign-in has expired. Please refresh the page and sign in again.";

// fetch + JSON with one error convention: a failed call throws an Error carrying the server's
// message (and `.data`, `.status`); a 401 always reads as an expired sign-in.
async function fetchJson(url, options = {}) {
  const res = await fetch(url, { ...options, headers: { Accept: "application/json", ...(options.headers || {}) } });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) throw Object.assign(new Error(SIGNIN_EXPIRED), { data, status: 401 });
  if (!res.ok) throw Object.assign(new Error(data.error || res.statusText), { data, status: res.status });
  return data;
}

function jsonRequest(url, method = "GET", body) {
  return fetchJson(url, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

// Shows `msg` in the page's #error box, or hides the box when msg is empty.
function showError(msg) {
  const box = $("error");
  box.textContent = msg || "";
  box.style.display = msg ? "block" : "none";
}
