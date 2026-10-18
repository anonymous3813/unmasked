import { useState } from "react";
import { api, saveSession } from "./api";

export default function SignIn({ onSignedIn }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = await api(mode === "register" ? "/auth/register" : "/auth/login", {
        method: "POST",
        body: { email, password, name },
      });
      saveSession(payload.token, payload.account);
      setPassword("");
      onSignedIn(payload);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel account">
      <p className="kicker">Your account</p>
      <h1>{mode === "register" ? "Create an account" : "Sign in"}</h1>
      <p className="quiet">Purchases, bills, and the wishlist open after you sign in. The registry stays public.</p>
      <form className="signin" onSubmit={submit}>
        <label>
          Email
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} autoComplete="current-password" />
        </label>
        {mode === "register" ? (
          <label>
            Name
            <input type="text" value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" />
          </label>
        ) : null}
        <button className="btn fill" type="submit" disabled={busy}>
          {busy ? "Working…" : mode === "register" ? "Create account" : "Log in"}
        </button>
        <button
          className="btn"
          type="button"
          onClick={() => {
            setMode(mode === "register" ? "login" : "register");
            setError("");
          }}
        >
          {mode === "register" ? "I already have an account" : "Create an account"}
        </button>
      </form>
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
