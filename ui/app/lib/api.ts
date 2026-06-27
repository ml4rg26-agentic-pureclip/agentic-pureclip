import { useEffect, useRef, useState } from "react";

// In dev the Vite proxy forwards /api -> the monitor backend. Override the base
// (e.g. for a static build hitting a remote monitor) with VITE_API_BASE.
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export interface Params {
  bandwidth_nt?: number;
  merge_distance_nt?: number;
  high_precision_mode?: boolean;
  learn_on_chr21?: boolean;
  min_crosslink_events?: number;
  force_width?: number;
}

export interface IterationRow {
  run_id: string;
  optimizer?: string;
  iter: number | null;
  n_sites: number | null;
  agreement: number | null;
  reproducibility: number | null;
  repro_enrichment: number | null;
  motif: number | null;
  enrichment: number | null;
  recall: number | null;
  composite: number | null;
  source: string;
}

export interface Experiment {
  name: string;
  best_composite: number | null;
  best_run: string | null;
  n_iters: number;
  iterations: IterationRow[];
}

export interface PlanJob {
  job_id: string;
  dataset: string;
  optimizer: string;
  max_iter: number;
  status: string;
  best_composite?: number | null;
  duration_s?: number | null;
  done_iters?: number;
  eta_remaining_s: number;
  per_iter_s?: number;
}

export interface Plan {
  manifest: string;
  started: string;
  jobs: PlanJob[];
  eta_remaining_s: number;
  counts: { done: number; running: number; queued: number };
}

export interface ActiveRun {
  is_active: boolean;
  optimizer: string | null;
  decide_label: string;
  job_id: string | null;
  stage: string;
  stage_index: number;
  substage: string | null;
  dataset: string | null;
  target_protein: string | null;
  cell_line: string | null;
  run_id: string | null;
  iteration: number | null;
  elapsed: string | null;
  params: Params;
  latest: IterationRow | null;
  reasoning: string | null;
}

export interface Proc {
  label: string;
  cpu: string;
  mem: string;
  etime: string;
}

export interface Status {
  host: string;
  cpus: string;
  mem: string;
  stages: string[];
  active: ActiveRun;
  plan: Plan | null;
  experiments: Experiment[];
  processes: Proc[];
}

export interface PollState {
  data: Status | null;
  error: string | null;
  updatedAt: Date | null;
}

/** Poll /api/status on an interval; returns the latest snapshot. */
export function useStatus(intervalMs = 6000): PollState {
  const [state, setState] = useState<PollState>({ data: null, error: null, updatedAt: null });
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let alive = true;
    async function tick() {
      try {
        const res = await fetch(`${API_BASE}/api/status`, { headers: { Accept: "application/json" } });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as Status;
        if (alive) setState({ data, error: null, updatedAt: new Date() });
      } catch (e) {
        if (alive) setState((s) => ({ ...s, error: e instanceof Error ? e.message : String(e) }));
      }
    }
    tick();
    timer.current = setInterval(tick, intervalMs);
    return () => {
      alive = false;
      if (timer.current) clearInterval(timer.current);
    };
  }, [intervalMs]);

  return state;
}

export const fmt = (v: number | null | undefined, d = 4) =>
  v === null || v === undefined ? "—" : Number(v).toFixed(d);
export const fmtx = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${Number(v).toFixed(2)}×`;

export function humanDur(s: number | null | undefined): string {
  if (s === null || s === undefined) return "—";
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${s}s`;
}

export function clockIn(s: number): string {
  return new Date(Date.now() + s * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}
