// Sign-in with the Firebase SDK (email + password, email link, Google). The browser
// only proves who you are to Firebase; the server verifies the ID token at
// POST /auth/session and starts its own session. Nothing here is a secret.
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js";
import {
  getAuth, GoogleAuthProvider, signInWithPopup, signInWithEmailAndPassword,
  createUserWithEmailAndPassword, sendEmailVerification, sendPasswordResetEmail,
  sendSignInLinkToEmail, isSignInWithEmailLink, signInWithEmailLink, signOut,
} from "https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js";

const root = document.getElementById("signin");
const config = JSON.parse(root.dataset.firebase);
const auth = getAuth(initializeApp(config));
const $ = (id) => document.getElementById(id);
const msg = $("signin-msg");
let creating = false;

const say = (text, bad = false) => {
  msg.textContent = text;
  msg.className = "signin-msg" + (bad ? " bad" : "");
};

const FRIENDLY = {
  "auth/invalid-credential": "That email and password don't match.",
  "auth/wrong-password": "That email and password don't match.",
  "auth/user-not-found": "That email and password don't match.",
  "auth/email-already-in-use": "That email already has an account. Try signing in.",
  "auth/weak-password": "Use a password with at least 6 characters.",
  "auth/invalid-email": "That email address doesn't look right.",
  "auth/too-many-requests": "Too many tries. Wait a moment and try again.",
  "auth/popup-closed-by-user": "",
  "auth/cancelled-popup-request": "",
  "auth/popup-blocked": "Your browser blocked the sign-in window. Allow pop-ups for this site and try again.",
  "auth/network-request-failed": "Network problem. Check your connection and try again.",
};
const fail = (e) => {
  console.error("Sign-in error", e);
  say(FRIENDLY[e.code] ?? `Something went wrong signing in (${e.code || e.name || "unknown error"}). Please try again.`, true);
};

async function finish(user) {
  const idToken = await user.getIdToken();
  const resp = await fetch("/auth/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ idToken }),
  });
  const data = await resp.json().catch(() => ({}));
  if (resp.ok && data.redirect) { window.location.href = data.redirect; return; }
  await signOut(auth);
  say(data.error === "verify_email"
    ? "Please verify your email first. We sent you a link."
    : "Sign-in didn't work. Please try again.", true);
}

async function guard(fn) {
  document.querySelectorAll("#signin button").forEach((b) => (b.disabled = true));
  try { await fn(); } catch (e) { fail(e); }
  document.querySelectorAll("#signin button").forEach((b) => (b.disabled = false));
}

$("google-btn").addEventListener("click", () =>
  guard(async () => finish((await signInWithPopup(auth, new GoogleAuthProvider())).user)));

$("email-form").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const email = $("email").value.trim();
  const password = $("password").value;
  guard(async () => {
    if (creating) {
      const { user } = await createUserWithEmailAndPassword(auth, email, password);
      await sendEmailVerification(user);
      await signOut(auth);
      say("Account created. Check your inbox and click the link, then sign in.");
      return;
    }
    const { user } = await signInWithEmailAndPassword(auth, email, password);
    if (!user.emailVerified) {
      await sendEmailVerification(user);
      await signOut(auth);
      say("Please verify your email first. We just sent you a new link.", true);
      return;
    }
    await finish(user);
  });
});

$("toggle-mode").addEventListener("click", () => {
  creating = !creating;
  $("email-submit").textContent = creating ? "Create account" : "Sign in";
  $("toggle-mode").textContent = creating ? "I already have an account" : "Create an account";
  $("password").autocomplete = creating ? "new-password" : "current-password";
  say("");
});

$("link-btn").addEventListener("click", () => {
  const email = $("email").value.trim();
  if (!email) return say("Type your email first.", true);
  guard(async () => {
    await sendSignInLinkToEmail(auth, email, { url: window.location.origin + "/", handleCodeInApp: true });
    localStorage.setItem("emailForSignIn", email);
    say("We emailed you a sign-in link. Open it on this device.");
  });
});

$("reset-btn").addEventListener("click", () => {
  const email = $("email").value.trim();
  if (!email) return say("Type your email first.", true);
  guard(async () => {
    await sendPasswordResetEmail(auth, email);
    say("If that email has an account, a reset link is on its way.");
  });
});

// Coming back from the emailed sign-in link
if (isSignInWithEmailLink(auth, window.location.href)) {
  const email = localStorage.getItem("emailForSignIn") || window.prompt("Confirm your email to finish signing in");
  if (email) {
    guard(async () => {
      const { user } = await signInWithEmailLink(auth, email, window.location.href);
      localStorage.removeItem("emailForSignIn");
      await finish(user);
    });
  }
}
