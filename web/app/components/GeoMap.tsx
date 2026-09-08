"use client";

import { useMemo } from "react";
import { ComposableMap, Geographies, Geography } from "react-simple-maps";
import topology from "world-atlas/countries-110m.json";
import { NUMERIC_TO_ISO2, countryName } from "../lib/countries";

/**
 * Choropleth of one theme's country weights.
 *
 * `values` is ISO2 -> 0..1 (already normalised by the caller, since the two maps in
 * Theme Detail derive their weights very differently: one from a curated rank order,
 * the other from Trends' 0-100 scale).
 *
 * The topology is imported, not fetched, so it is bundled at build time and works under
 * `output: "export"` with no network at runtime.
 */
export default function GeoMap({
  values,
  accent,
  emptyLabel = "No data yet",
}: {
  values: Record<string, number>;
  accent: string;
  emptyLabel?: string;
}) {
  const hasData = Object.keys(values).length > 0;

  // Pre-resolve so the render loop is a lookup rather than a search per country.
  const shade = useMemo(() => {
    const rgb = hexToRgb(accent);
    return (iso2: string | undefined) => {
      if (!iso2) return null;
      const v = values[iso2];
      if (v === undefined) return null;
      // Floor the alpha so a low-but-present weight is still visibly distinct from
      // "no data" — the difference between "a little" and "none" is the whole point.
      const alpha = 0.22 + 0.78 * Math.max(0, Math.min(1, v));
      return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`;
    };
  }, [values, accent]);

  if (!hasData) {
    return (
      <div className="flex h-[190px] items-center justify-center rounded border border-edge bg-panel2 text-xs text-muted">
        {emptyLabel}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded border border-edge bg-panel2">
      <ComposableMap
        projection="geoEqualEarth"
        projectionConfig={{ scale: 148 }}
        width={800}
        height={380}
        style={{ width: "100%", height: "auto" }}
      >
        <Geographies geography={topology}>
          {({ geographies }: { geographies: any[] }) =>
            geographies.map((geo) => {
              const iso2 = NUMERIC_TO_ISO2[String(geo.id)];
              const fill = shade(iso2);
              const label = iso2 ? countryName(iso2) : geo.properties?.name;
              const weight = iso2 ? values[iso2] : undefined;
              return (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  fill={fill ?? "#1c2230"}
                  stroke="#0a0c10"
                  strokeWidth={0.35}
                  style={{
                    default: { outline: "none" },
                    hover: { outline: "none", fill: fill ?? "#262c38" },
                    pressed: { outline: "none" },
                  }}
                >
                  {fill && (
                    <title>
                      {label}
                      {weight !== undefined ? ` — ${Math.round(weight * 100)}` : ""}
                    </title>
                  )}
                </Geography>
              );
            })
          }
        </Geographies>
      </ComposableMap>
    </div>
  );
}

function hexToRgb(hex: string) {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(full, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}
