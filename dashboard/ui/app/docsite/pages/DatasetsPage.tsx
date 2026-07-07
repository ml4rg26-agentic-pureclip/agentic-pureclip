import { useEffect, useState } from "react";

// ── Curated catalog content ────────────────────────────────────────────────

interface Row {
  dataset: string;
  rbp: string;
  cell: string;
  motif: string;
  role: string;
  positional?: boolean;
  control?: boolean;
}

const PRELIMINARY: Row[] = [
  { dataset: "RBFOX2_K562", rbp: "RBFOX2", cell: "K562", motif: "UGCAUG", role: "splicing regulator" },
  { dataset: "RBFOX2_HepG2", rbp: "RBFOX2", cell: "HepG2", motif: "UGCAUG", role: "splicing regulator" },
  { dataset: "QKI_K562", rbp: "QKI", cell: "K562", motif: "ACUAAY", role: "STAR-family" },
  { dataset: "QKI_HepG2", rbp: "QKI", cell: "HepG2", motif: "ACUAAY", role: "STAR-family" },
  { dataset: "PUM1_K562", rbp: "PUM1", cell: "K562", motif: "UGUANAUA", role: "Pumilio" },
];

const NEW: Row[] = [
  { dataset: "HNRNPK_HepG2", rbp: "HNRNPK", cell: "HepG2", motif: "UUCCCAGUCCC", role: "hnRNP, C-rich, splicing/translation" },
  { dataset: "HNRNPK_K562", rbp: "HNRNPK", cell: "K562", motif: "UUCCCAUCCCC", role: "hnRNP, C-rich" },
  { dataset: "HNRNPM_HepG2", rbp: "HNRNPM", cell: "HepG2", motif: "UUUGUUGGUUG", role: "hnRNP, GU-rich, splicing" },
  { dataset: "HNRNPM_K562", rbp: "HNRNPM", cell: "K562", motif: "UUUUGUGGCUG", role: "hnRNP, GU-rich" },
  { dataset: "SF3B1_K562", rbp: "SF3B1", cell: "K562", motif: "UAACCUAACAG", role: "U2 snRNP, branch point", positional: true },
  { dataset: "SF3B4_HepG2", rbp: "SF3B4", cell: "HepG2", motif: "UCUCUGACCCC", role: "U2 snRNP", positional: true },
  { dataset: "SF3B4_K562", rbp: "SF3B4", cell: "K562", motif: "UUUUUCAGGUA", role: "U2 snRNP", positional: true },
  { dataset: "SFPQ_HepG2", rbp: "SFPQ", cell: "HepG2", motif: "UUGUUCCGUCU", role: "paraspeckle, splicing" },
  { dataset: "SRSF1_HepG2", rbp: "SRSF1", cell: "HepG2", motif: "ACCUGGACAGG", role: "SR protein, exonic splicing enhancer" },
  { dataset: "SRSF1_K562", rbp: "SRSF1", cell: "K562", motif: "UCUGGAUCUGG", role: "SR protein" },
  { dataset: "U2AF1_HepG2", rbp: "U2AF1", cell: "HepG2", motif: "UUUUCACAGGC", role: "3′ splice-site AG", positional: true },
  { dataset: "U2AF1_K562", rbp: "U2AF1", cell: "K562", motif: "UUUCUAGGUGC", role: "3′ splice-site AG", positional: true },
  { dataset: "U2AF2_HepG2", rbp: "U2AF2", cell: "HepG2", motif: "UUUUUCAGGUU", role: "polypyrimidine tract", positional: true },
  { dataset: "U2AF2_K562", rbp: "U2AF2", cell: "K562", motif: "UUUUUCAGGUU", role: "polypyrimidine tract", positional: true },
  { dataset: "RBM22_HepG2", rbp: "RBM22", cell: "HepG2", motif: "GUGGUGCCCCG", role: "spliceosome (Prp19 complex)" },
  { dataset: "RBM22_K562", rbp: "RBM22", cell: "K562", motif: "UUGGUAAUUUU", role: "spliceosome" },
  { dataset: "PCBP1_HepG2", rbp: "PCBP1", cell: "HepG2", motif: "CCCCCCC", role: "poly-C binding" },
  { dataset: "PCBP1_K562", rbp: "PCBP1", cell: "K562", motif: "CCCCCCC", role: "poly-C binding" },
  { dataset: "PUM2_K562", rbp: "PUM2", cell: "K562", motif: "UUUGUAUAUAU", role: "Pumilio (same family as PUM1)", control: true },
  { dataset: "PTBP1_HepG2", rbp: "PTBP1", cell: "HepG2", motif: "UUUCUUCUUUU", role: "splicing repressor, CU-rich" },
];

// ── Small presentational helpers ───────────────────────────────────────────

function Stat({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-4">
      <div className="text-3xl font-extrabold text-white leading-none">{value}</div>
      <div className="mt-1 text-xs uppercase tracking-wide text-gray-500">{label}</div>
    </div>
  );
}

function DatasetTable({ rows, registered }: { rows: Row[]; registered: Set<string> }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left text-indigo-400 border-b-2 border-gray-700">
            <th className="py-2 pr-3 font-semibold">Dataset</th>
            <th className="py-2 pr-3 font-semibold">RBP</th>
            <th className="py-2 pr-3 font-semibold">Cell</th>
            <th className="py-2 pr-3 font-semibold">Top motif</th>
            <th className="py-2 pr-3 font-semibold">Role</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.dataset} className="border-b border-gray-800 hover:bg-gray-900/60">
              <td className="py-1.5 pr-3 font-mono text-gray-200">
                {r.dataset}
                {registered.has(r.dataset) && (
                  <span className="ml-2 text-emerald-400" title="registered in pipeline">●</span>
                )}
              </td>
              <td className="py-1.5 pr-3 text-gray-300">{r.rbp}</td>
              <td className="py-1.5 pr-3 text-gray-400">{r.cell}</td>
              <td className="py-1.5 pr-3">
                <code className="text-amber-300 bg-gray-800/70 px-1.5 py-0.5 rounded">{r.motif}</code>
              </td>
              <td className="py-1.5 pr-3 text-gray-400">
                {r.role}
                {r.positional && <span className="ml-2 text-rose-400 text-xs">(positional)</span>}
                {r.control && <span className="ml-2 text-emerald-400 text-xs">(control)</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function DatasetsPage() {
  const [registered, setRegistered] = useState<Set<string>>(new Set());
  const [total, setTotal] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/options", { headers: { Accept: "application/json" } })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d: { datasets?: string[] }) => {
        if (!alive) return;
        const ds = d.datasets ?? [];
        setRegistered(new Set(ds));
        setTotal(ds.length);
      })
      .catch(() => void 0);
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="max-w-screen-xl mx-auto px-6 py-8 text-gray-200">
      <p className="text-indigo-400 text-xs font-bold uppercase tracking-widest">Data reference</p>
      <h1 className="text-3xl font-bold text-white mt-1">Dataset Catalog</h1>
      <p className="text-gray-400 mt-2 max-w-3xl">
        Which ENCODE eCLIP datasets this project uses, where they came from, what they add, and how
        to run them. The <span className="text-emerald-400">●</span> marker means the dataset is
        currently registered in the pipeline (live from <code className="text-amber-300">/api/options</code>).
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-6">
        <Stat value={total ?? "…"} label="Registered datasets" />
        <Stat value={20} label="New (2026-07)" />
        <Stat value={15} label="RNA-binding proteins" />
        <Stat value={2} label="Cell lines" />
      </div>

      <h2 className="text-xl font-semibold text-white border-b-2 border-indigo-500 pb-1 mt-10 mb-3">
        1 · Origin & layout
      </h2>
      <p className="text-gray-400 max-w-3xl">
        All datasets are ENCODE <strong className="text-gray-200">eCLIP</strong> experiments (two IP
        replicates + a size-matched input control, aligned to{" "}
        <code className="text-amber-300">GRCh38.primary_assembly</code>), stored under{" "}
        <code className="text-amber-300">data/&lt;RBP&gt;_&lt;cell&gt;/</code> with{" "}
        <code className="text-amber-300">bam/</code>, <code className="text-amber-300">top_regions/</code>,{" "}
        <code className="text-amber-300">top_crosslink_sites/</code>,{" "}
        <code className="text-amber-300">top_genes/</code> and{" "}
        <code className="text-amber-300">biotypes_genetypes/</code>. In July 2026 three Google-Drive
        folders (37.6 GiB) added <strong className="text-gray-200">20 new datasets</strong> after
        de-duplication (one folder re-packaged the preliminary batch; several files were duplicates).
      </p>

      <h2 className="text-xl font-semibold text-white border-b-2 border-indigo-500 pb-1 mt-10 mb-3">
        2 · Preliminary batch <span className="text-gray-500 text-sm font-normal">(sequence-specific RBPs)</span>
      </h2>
      <DatasetTable rows={PRELIMINARY} registered={registered} />
      <p className="text-gray-500 text-sm mt-2">Crisp, well-defined k-mer motifs — the clean cases the pipeline was tuned on.</p>

      <h2 className="text-xl font-semibold text-white border-b-2 border-indigo-500 pb-1 mt-10 mb-3">
        3 · New datasets (2026-07) <span className="text-emerald-400 text-sm font-normal">· 20 new</span>
      </h2>
      <p className="text-gray-400 max-w-3xl mb-3">
        Twelve new RBPs, mostly <strong className="text-gray-200">splicing factors / spliceosome
        components</strong> — a harder, more diverse class whose binding is often positional or
        degenerate rather than a single k-mer. Motifs are the top consensus auto-resolved from the
        PWM catalog (mCrossBase/ATtRACT, cell-line specific).
      </p>
      <DatasetTable rows={NEW} registered={registered} />

      <div className="mt-8 rounded-xl border border-rose-500/60 bg-rose-950/30 px-5 py-4">
        <p className="text-rose-300 font-semibold">Caveat — motif priors</p>
        <p className="text-gray-300 text-sm mt-1">
          For positional binders (U2AF1/U2AF2/SF3B1/SF3B4/RBM22) the “top motif” is a weak/degenerate
          proxy. Motif-aware scoring should be down-weighted or replaced by a positional prior for
          these, or scores will mislead. Also confirm each dataset’s shipped benchmark files were
          generated consistently with the preliminary batch before treating scores as comparable.
        </p>
      </div>

      <h2 className="text-xl font-semibold text-white border-b-2 border-indigo-500 pb-1 mt-10 mb-3">
        4 · What they add
      </h2>
      <ul className="list-disc pl-6 text-gray-400 space-y-1 max-w-3xl">
        <li><strong className="text-gray-200">Scale:</strong> the benchmark grows from 5 to 25 datasets (5×).</li>
        <li><strong className="text-gray-200">Diversity:</strong> a new class of RBP (splicing factors) that stresses the pipeline beyond crisp-motif proteins.</li>
        <li><strong className="text-gray-200">Paired cell lines</strong> (K562 + HepG2) enable cross-cell-line reproducibility analysis.</li>
        <li><strong className="text-gray-200">PUM2_K562</strong> is a positive control: same motif family as PUM1, so existing priors transfer.</li>
      </ul>

      <h2 className="text-xl font-semibold text-white border-b-2 border-indigo-500 pb-1 mt-10 mb-3">
        5 · How to run
      </h2>
      <p className="text-gray-400 max-w-3xl">
        Datasets are registered in <code className="text-amber-300">pipeline/datasets.py</code>; per-dataset
        configs live in <code className="text-amber-300">config/datasets/*.yaml</code>. Preliminary
        (chr21-restricted) optimization for all 20:
      </p>
      <pre className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 mt-2 text-sm text-amber-200 overflow-x-auto">
uv run python scripts/run/batch_runner.py --manifest config/new_batch_runs.yaml --parallel 4</pre>

      <div className="mt-6 rounded-xl border border-emerald-500/60 bg-emerald-950/30 px-5 py-4">
        <p className="text-emerald-300 font-semibold">Recommendation</p>
        <p className="text-gray-300 text-sm mt-1">
          Optimize on restricted regions (chr21, minutes per iteration) to search PureCLIP
          parameters, then run a <em>single full-genome confirmation</em> per dataset (~3.5 h each).
          This keeps the search cheap and pays the full-genome cost only ~20 times. Prioritize PUM2
          (control) and the splicing factors, but fix the per-RBP motif priors first so scoring
          stays meaningful. Budget ≈ 3–4 machine-days for the full new batch end-to-end.
        </p>
      </div>

      <p className="text-gray-600 text-xs mt-10 border-t border-gray-800 pt-4">
        Source: 3 shared Google-Drive folders (37.6 GiB) · see{" "}
        <code className="text-amber-300">NEW_DATA_INVESTIGATION.md</code> for the full investigation and time budget.
      </p>
    </div>
  );
}
