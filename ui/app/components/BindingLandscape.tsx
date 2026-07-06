import { useEffect, useMemo, useState } from "react";
import { fetchRunSites, fmt, fmtx, type RunSites } from "../lib/api";

/**
 * "Where did the RBP dock?" — a genomic track of the best iteration's
 * reproducible binding sites, with the RBP animated hopping from site to site.
 * Positions are real (from binding_sites.reproducible.bed); when a run has no
 * coordinate file we fall back to an evenly-spaced schematic from n_sites.
 */
export function BindingLandscape({
  dataset,
  protein,
  cellLine,
}: {
  dataset: string;
  protein?: string | null;
  cellLine?: string | null;
}) {
  const [data, setData] = useState<RunSites | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    fetchRunSites(dataset)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [dataset]);

  // Normalize sites to 0..1 along the track. Fall back to a schematic if the
  // run has no coordinate file (older runs) but reported a site count.
  const { marks, schematic, extent } = useMemo(() => {
    const ext = data?.extent;
    const real = (data?.sites ?? []).filter((s) => Number.isFinite(s.start));
    if (real.length && ext && ext.end > ext.start) {
      const span = ext.end - ext.start;
      return {
        schematic: false,
        extent: ext,
        marks: real.map((s) => ({
          x: ((s.start + s.end) / 2 - ext.start) / span,
          motif: !!s.motif,
        })),
      };
    }
    const n = Math.min(60, Math.max(0, data?.n_sites ?? 0));
    const rate = data?.motif_hit_rate ?? 0;
    return {
      schematic: n > 0,
      extent: null,
      marks: Array.from({ length: n }, (_, i) => ({
        x: n === 1 ? 0.5 : i / (n - 1),
        motif: i % Math.max(2, Math.round(1 / (rate || 0.25))) === 0,
      })),
    };
  }, [data]);

  // Sample up to 12 docking stops so the protein hop reads clearly.
  const stops = useMemo(() => {
    if (!marks.length) return [] as number[];
    const step = Math.max(1, Math.ceil(marks.length / 12));
    return marks.filter((_, i) => i % step === 0).map((m) => m.x);
  }, [marks]);

  const anim = useMemo(() => makeHopKeyframes(stops), [stops]);

  if (error) {
    return <div className="landscape-empty">Binding landscape unavailable ({error}).</div>;
  }
  if (!data) {
    return <div className="landscape-empty">Loading binding landscape…</div>;
  }
  if (!marks.length) {
    return (
      <div className="landscape-empty">
        No binding sites recorded for {dataset} yet.
      </div>
    );
  }

  const label = [protein || dataset.split("_")[0], cellLine].filter(Boolean).join(" · ");
  const motifPct =
    data.motif_hit_rate != null ? Math.round(data.motif_hit_rate * 100) : null;

  return (
    <div className="landscape">
      <style>{anim.css}</style>
      <div className="landscape-head">
        <span className="ll-title">🧬 Binding landscape — where {label} docked</span>
        <span className="ll-meta">
          {data.chrom ?? "genome"}
          {extent ? ` · ${fmtKb(extent.start)}–${fmtKb(extent.end)}` : ""} ·{" "}
          {data.n_sites ?? marks.length} sites
          {data.run_id ? ` · ${data.run_id}` : ""}
        </span>
      </div>

      <div className="ll-track" aria-hidden>
        {/* RNA backbone */}
        <div className="ll-rna" />
        {/* binding sites */}
        {marks.map((m, i) => (
          <span
            key={i}
            className={`ll-site${m.motif ? " motif" : ""}`}
            style={{ left: `${m.x * 100}%` }}
            title={m.motif ? "motif-bearing site" : "binding site"}
          />
        ))}
        {/* the traveling RBP */}
        {stops.length > 0 && (
          <div className="ll-rbp" style={{ animation: `${anim.name} ${anim.dur}s ease-in-out infinite` }}>
            <span className="ll-rbp-body">{proteinGlyph(protein || dataset)}</span>
            <span className="ll-rbp-foot" />
          </div>
        )}
      </div>

      <div className="ll-legend">
        <span className="ll-key"><i className="dot motif" /> motif-bearing{motifPct != null ? ` (~${motifPct}%)` : ""}</span>
        <span className="ll-key"><i className="dot plain" /> binding site</span>
        {data.motif_enrichment != null && (
          <span className="ll-key">enrichment {fmtx(data.motif_enrichment)}</span>
        )}
        {data.reproducibility != null && (
          <span className="ll-key">reproducibility {fmt(data.reproducibility, 3)}</span>
        )}
        {schematic && <span className="ll-key schematic">schematic (no coordinate file)</span>}
      </div>
      <div className="ll-note">
        Each mark is a reproducible binding site along {data.chrom ?? "the genome"}; the RBP
        glyph hops between representative sites. Motif flags are approximate (per-site
        motif calls aren't persisted).
      </div>
    </div>
  );
}

/* Build a CSS @keyframes that walks the protein across the sampled site
   x-positions, dipping onto the RNA at each stop. Data-driven so the hop lands
   on real binding sites. */
function makeHopKeyframes(stops: number[]): { name: string; css: string; dur: number } {
  if (!stops.length) return { name: "ll-none", css: "", dur: 0 };
  const name = `ll-hop-${stops.length}-${Math.round((stops[0] + stops[stops.length - 1]) * 100)}`;
  const n = stops.length;
  const frames: string[] = [];
  stops.forEach((x, i) => {
    const base = (i / n) * 100;
    const dwell = base + (1 / n) * 100 * 0.62;
    // travel to the site, then dock (dip down) and hold briefly
    frames.push(`${base.toFixed(2)}% { left:${(x * 100).toFixed(2)}%; transform:translate(-50%,-2px); }`);
    frames.push(`${dwell.toFixed(2)}% { left:${(x * 100).toFixed(2)}%; transform:translate(-50%,4px); }`);
  });
  frames.push(`100% { left:${(stops[0] * 100).toFixed(2)}%; transform:translate(-50%,-2px); }`);
  const dur = Math.max(6, Math.min(20, n * 1.4));
  return { name, css: `@keyframes ${name} { ${frames.join(" ")} }`, dur };
}

function proteinGlyph(seed: string): string {
  const glyphs = ["🔴", "🟣", "🔵", "🟢", "🟠"];
  let h = 0;
  for (const c of seed) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return glyphs[h % glyphs.length];
}

function fmtKb(bp: number): string {
  if (bp >= 1e6) return `${(bp / 1e6).toFixed(2)}Mb`;
  if (bp >= 1e3) return `${Math.round(bp / 1e3)}kb`;
  return `${bp}`;
}
