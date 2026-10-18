import { useEffect, useState } from "react";
import { api, clearSession, readSession } from "./api";
import Bills from "./Bills";
import Purchases from "./Purchases";
import Registry from "./Registry";
import SignIn from "./SignIn";
import Wishlist from "./Wishlist";

const TABS = [
  ["registry", "Registry"],
  ["purchases", "Purchases"],
  ["bills", "Bills"],
  ["wishlist", "Wishlist"],
];

export default function App() {
  const [session, setSession] = useState(readSession);
  const [tab, setTab] = useState("registry");

  useEffect(() => {
    function onStorage() {
      setSession(readSession());
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  async function signOut() {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch (error) {
      /* The local session is cleared either way. */
    }
    clearSession();
    setSession(readSession());
    setTab("registry");
  }

  const signedIn = Boolean(session.token);
  const privateTab = tab !== "registry";

  return (
    <div className="shell">
      <header className="top">
        <button className="brand" type="button" onClick={() => setTab("registry")}>
          <img src="/logo.jpeg" alt="" />
          Unmasked
        </button>
        <nav className="nav" aria-label="Main">
          {TABS.map(([id, label]) => (
            <button key={id} type="button" aria-pressed={tab === id} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </nav>
        <div className="actions">
          {signedIn ? (
            <>
              <span className="who">{session.account && session.account.name ? session.account.name : "Signed in"}</span>
              <button className="btn" type="button" onClick={signOut}>
                Sign out
              </button>
            </>
          ) : (
            <button className="btn fill" type="button" onClick={() => setTab("purchases")}>
              Sign in
            </button>
          )}
          <a className="btn fill" href="/extension.zip">
            Download the extension
          </a>
        </div>
      </header>
      <main>
        {tab === "registry" ? <Registry /> : null}
        {privateTab && !signedIn ? <SignIn onSignedIn={() => setSession(readSession())} /> : null}
        {tab === "purchases" && signedIn ? <Purchases /> : null}
        {tab === "bills" && signedIn ? <Bills /> : null}
        {tab === "wishlist" && signedIn ? <Wishlist /> : null}
      </main>
      <footer>
        Agent registry findings are public. Purchases, bills, and the wishlist stay on the signed-in account.{" "}
        <a href="/privacy">Privacy policy</a>
        {" · "}
        <a href="/terms">Terms</a>
      </footer>
    </div>
  );
}
