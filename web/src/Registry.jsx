import { useEffect, useMemo, useState } from "react";
import { api } from "./api";

const FILTERS = [
  ["all", "All"],
  ["page", "Pages"],
  ["ask", "Questions"],
];

const LABELS = { page: "Page", ask: "Question", message: "Message", call: "Call", order: "Order", intro: "Text" };

function when(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function host(url) {
  try {
    return new URL(url).host;
  } catch (error) {
    return "Open";
  }
}

export default function Registry() {
  const [entries, setEntries] = useState([]);
  const [counts, setCounts] = useState({});
  const [kind, setKind] = useState("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [status, setStatus] = useState("Loading the registry…");

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const payload = await api("/registry");
        if (!alive) return;
        setEntries(Array.isArray(payload.entries) ? payload.entries : []);
        setCounts(payload.counts || {});
        setStatus("Updated " + new Date().toLocaleTimeString());
      } catch (error) {
        if (alive) setStatus("The registry is not reachable right now.");
      }
    }
    load();
    const timer = setInterval(load, 8000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return entries.filter((entry) => {
      const haystack = `${entry.title || ""} ${entry.detail || ""} ${entry.url || ""}`.toLowerCase();
      return (kind === "all" || entry.kind === kind) && (!needle || haystack.includes(needle));
    });
  }, [entries, kind, query]);

  return (
    <section className="panel">
      <p className="kicker">Agent registry</p>
      <div className="title-row">
        <h1>What the agent has checked</h1>
        <p className="quiet">{status}</p>
      </div>
      <div className="stats">
        {[
          ["page", "pages checked"],
          ["ask", "questions"],
        ].map(([key, label]) => (
          <p key={key}>
            <strong>{counts[key] || 0}</strong>
            <span>{label}</span>
          </p>
        ))}
      </div>
      <div className="toolbar">
        <div className="filters" role="group" aria-label="Log type">
          {FILTERS.map(([id, label]) => (
            <button key={id} type="button" aria-pressed={kind === id} onClick={() => setKind(id)}>
              {label}
            </button>
          ))}
        </div>
        <label className="finder">
          Search
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter the log" />
        </label>
      </div>
      <div className="split">
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Type</th>
              <th>What happened</th>
            </tr>
          </thead>
          <tbody>
            {visible.length ? (
              visible.map((entry) => (
                <tr key={entry.id || entry.title + entry.at} className={selected && selected.id === entry.id ? "picked" : ""} onClick={() => setSelected(entry)}>
                  <td>{when(entry.at)}</td>
                  <td>{LABELS[entry.kind] || "Log"}</td>
                  <td>
                    <strong>{entry.title}</strong>
                    {entry.detail ? <span className="detail"> {entry.detail}</span> : null}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={3}>Nothing is in the registry yet. Download the extension and open a product page.</td>
              </tr>
            )}
          </tbody>
        </table>
        <aside className="detail-card">
          {selected ? <EntryDetail entry={selected} /> : <p className="quiet">Select a finding to read it and the agent vote.</p>}
        </aside>
      </div>
    </section>
  );
}

function EntryDetail({ entry }) {
  const rounds = (entry.ballot && entry.ballot.rounds) || [];
  return (
    <div>
      <p className="kicker">{LABELS[entry.kind] || "Log"}</p>
      <h2>{entry.title}</h2>
      <p>{entry.detail}</p>
      {entry.url ? (
        <p>
          <a href={entry.url}>{host(entry.url)}</a>
        </p>
      ) : null}
      {rounds.map((round) => (
        <div key={round.name}>
          <h3>{round.name}</h3>
          <ul className="votes">
            {(round.agents || []).map((agent) => (
              <li key={agent.name + round.name}>
                <strong>{agent.name}</strong> {agent.vote === "yes" ? "yes" : "no"}
                {agent.story ? <span> — {agent.story}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ))}
      {entry.ballot && entry.ballot.decision ? <p className="decision">{entry.ballot.decision}</p> : null}
    </div>
  );
}
