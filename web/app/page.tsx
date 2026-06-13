"use client";

import { useEffect, useMemo, useState } from "react";
import type { ScoresResponse } from "./lib/types";
import RotationMap from "./components/RotationMap";
import ThemeDetail from "./components/ThemeDetail";
import Movers from "./components/Movers";

type Tab = "map" | "detail" | "movers";

export default function Page() {
  const [data, setData] = useState<ScoresResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("map");
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    // In the static (Pages) build the site is served under BASE_PATH, so the
    // pre-rendered /api/scores file lives there too. Empty in dev/node-server mode.
    const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
    fetch(`${base}/api/scores`)
      .then((r) => r.json())
      .then((d) => (d.error ? setError(d.error) : setData(d)))
      .catch((e) => setError(String(e)));
  }, []);

  const selectedTheme = useMemo(
    () => data?.themes.find((t) => t.id === selected) ?? null,
    [data, selected],
  );

  function openTheme(id: string) {
    setSelected(id);
    setTab("detail");
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: "map", label: "Rotation Map" },
    { key: "detail", label: "Theme Detail" },
    { key: "movers", label: "Movers" },
  ];

  return (
    <main className="min-h-screen px-4 py-3 md:px-6">
      <header className="mb-3 flex flex-col gap-2 border-b border-edge pb-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            Attention Rotation Monitor
          </h1>
          <p className="text-xs text-muted">
            research (slow money) vs speculative (fast money) attention · z-scores vs
            trailing 90d
          </p>
        </div>
        <div className="text-xs text-muted">
          {data?.asOf ? `as of ${data.asOf}` : ""}
        </div>
      </header>

      <nav className="mb-4 flex gap-1">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded px-3 py-1.5 text-xs font-medium transition ${
              tab === t.key
                ? "bg-panel2 text-accent"
                : "text-muted hover:bg-panel hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {error && (
        <div className="rounded border border-froth/40 bg-froth/10 p-4 text-sm text-froth">
          Failed to load data: {error}
          <div className="mt-1 text-xs text-muted">
            Populate the database first: <code>python collector/seed_demo.py</code> (dev)
            or run the real collector + backfill.
          </div>
        </div>
      )}

      {!error && !data && <div className="text-sm text-muted">Loading…</div>}

      {data && (
        <>
          {tab === "map" && (
            <RotationMap themes={data.themes} onSelect={openTheme} />
          )}
          {tab === "detail" && (
            <ThemeDetail
              themes={data.themes}
              selected={selectedTheme}
              onSelect={setSelected}
            />
          )}
          {tab === "movers" && (
            <Movers themes={data.themes} onSelect={openTheme} />
          )}
        </>
      )}
    </main>
  );
}
