"use client";

import { Fragment, useState } from "react";
import useSWR from "swr";

import { Empty, LevelBadge, Notice, PageHeader, Panel, Stat } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { LEVEL_COLOR } from "@/lib/colors";

type Level = "NORMAL" | "WATCH" | "WARNING" | "CRITICAL";
interface ClsReport { accuracy: number; macro_f1: number; recall_per_class: number[]; warning_recall: number; warning_precision: number; confusion: number[][]; feature_importance?: Record<string, number>; trained_on?: number }
interface RegH { rmse_scaled: number; mae_scaled: number; skill_vs_persistence: number; median_abs_pct_error: number; median_abs_pct_error_persistence: number; median_abs_pct_error_high_flow: number | null }
interface Policy { flood_events: number; warned_in_advance: number; warned_by_onset_day: number; mean_lead_days: number; false_alarm_ratio: number; level_changes_per_station_year: number; mean_reward_per_day: number }
interface Metrics {
  classification: Record<"baseline_today_class" | "logistic_regression" | "random_forest" | "svm", ClsReport> & {
    flood_svm_rain_only: { roc_auc: number; recall: number; precision: number; f1: number; trained_on: number; confusion: number[][] } };
  regression: Record<"linear_regression" | "xgboost" | "lstm" | "persistence_baseline", { "1d": RegH; "3d": RegH; train_loss_by_epoch?: number[]; feature_importance_1d?: Record<string, number> }>;
  clustering: { k: number; silhouette: number; features: string[]; names: string[]; sizes: number[]; centres: Record<string, number>[] };
  anomaly: { readings: number; gauges: number; flagged: number; flagged_share: number; rule_flagged: number; also_flagged_by_rules: number; note: string };
  dqn: { steps: number; episodes: number; episode_days: number; gamma: number; reward: string; state: string[]; actions: string[];
    training_curve: { episode: number; step: number; mean_reward_per_day: number; epsilon: number }[]; evaluation_2023_2024: Record<"dqn" | "random_forest" | "threshold_rule_today", Policy> };
}
interface Meta {
  trained_at: string; train_seconds: number; period: { start: string; end: string; test_from: string }; samples: { train: number; test: number };
  class_counts_test: number[]; versions: Record<string, string>; data_sources: string[];
  stations: { id: number; name: string; cluster: number; pca: [number, number]; climate: Record<string, number> }[];
}
interface OutlookStation {
  station_id: number; name: string; cluster_name: string; as_of: string; flow_m3s: number; level_now: Level; flow_30d: number[];
  thresholds_m3s: { watch: number; warning: number; critical: number }; rain_7d_mm: number; forecast_rain_3d_mm: number;
  forecast_rain_7d_mm: number; forecast_uncertainty: number; upstream: string[]; upstream_flow_m3s: number | null;
  soil_moisture: number; headwater_temp_c: number; headwater_snow_30d_cm: number;
  classification: Record<"logistic_regression" | "random_forest" | "svm", { level: Level; probabilities: number[] }>;
  flood_probability_rain_only: number;
  regression: Record<"linear_regression" | "xgboost" | "lstm", { flow_1d_m3s: number; flow_3d_m3s: number }>;
  dqn: { current_alert: Level; recommended: Level; q_values: number[] };
}
interface Day30 {
  date: string; level: Level; probabilities: number[]; chance_flow_at_or_above: { watch: number; warning: number; critical: number };
  flow_m3s: { low: number; middle: number; high: number }; rain_mm: number; rain_source: string;
}
interface Station30 {
  station_id: number; name: string; current_level: Level; highest_level: Level; highest_level_date: string;
  first_date: { watch: string | null; warning: string | null; critical: string | null };
  thresholds_m3s: { watch: number; warning: number; critical: number }; futures: number; days: Day30[];
}
interface Outlook30Data { today: string; days: number; stations: Station30[]; method: string; note: string }
interface Anomaly { station_id: number; name: string; observed_at: string; value_m: number; score: number; rule_quality: string; main_reason: string }

const LEVELS: Level[] = ["NORMAL", "WATCH", "WARNING", "CRITICAL"];
const CLUSTER_COLORS = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1"];
const INPUT_LABEL: Record<string, string> = {
  flow_now: "river flow today", flow_change_1d: "flow change, 1 day", flow_change_3d: "flow change, 3 days", flow_mean_7d: "flow, 7-day average",
  flow_max_30d: "highest flow, 30 days", rain_today: "rain today", rain_3d: "rain, last 3 days", rain_7d: "rain, last 7 days", rain_30d: "rain, last 30 days",
  forecast_rain_1d: "rain forecast, 1 day", forecast_rain_3d: "rain forecast, 3 days", forecast_rain_7d: "rain forecast, 7 days",
  forecast_uncertainty: "forecast uncertainty", season_sin: "time of year", season_cos: "time of year (2)", class_now: "today's level",
  upstream_flow_now: "upstream flow", upstream_change_1d: "upstream change, 1 day", upstream_change_3d: "upstream change, 3 days",
  has_upstream: "has upstream rivers", soil_moisture: "soil wetness", soil_moisture_change_7d: "soil wetting, 7 days",
  headwater_temp_3d: "mountain temperature", headwater_warmth_7d: "mountain warmth (melt)", headwater_snow_30d: "mountain snow, 30 days",
};
const pct = (v: number) => `${Math.round(v * 100)}%`;
const MODEL_NAME: Record<string, string> = {
  baseline_today_class: "No model: keep today's level", logistic_regression: "Weighted risk score", random_forest: "Vote of many if-then rule sets", svm: "Flood / normal boundary finder",
  linear_regression: "Straight-line flow estimate", xgboost: "Step-by-step corrected flow estimate", lstm: "Flow estimate that reads the last 30 days in order", persistence_baseline: "No model: assume no change",
  dqn: "Warning agent (learned by trial and reward)", threshold_rule_today: "Current rule: today's level",
};

export default function MlPage() {
  const { data: models, error } = useSWR<{ meta: Meta; metrics: Metrics }>("/api/v1/ml/models", fetcher);
  const { data: outlook, error: outErr } = useSWR<{ today: string; stations: OutlookStation[]; note: string }>(models ? "/api/v1/ml/outlook" : null, fetcher, { revalidateOnFocus: false });
  const { data: o30, error: o30Err } = useSWR<Outlook30Data>(models ? "/api/v1/ml/outlook30" : null, fetcher, { revalidateOnFocus: false });
  const { data: anom } = useSWR<{ hours: number; readings_scored: number; gauges: number; anomalies: Anomaly[]; total_anomalies: number }>(models ? "/api/v1/ml/anomalies" : null, fetcher);

  if (error) return <div className="space-y-4"><PageHeader title="ML models" /><Notice kind="warn">{(error as Error).message}</Notice></div>;
  if (!models) return <div className="space-y-4"><PageHeader title="ML models" /><p className="text-sm text-slate-400">Loading models…</p></div>;
  const { meta, metrics: m } = models;
  const c = m.classification, r = m.regression, d = m.dqn.evaluation_2023_2024;

  return (
    <div className="space-y-4">
      <PageHeader title="ML models" subtitle="Models that predict the risk level, forecast river flow, decide when to warn (now and for the next 30 days), group similar rivers and spot faulty sensor readings — trained on six years of river and rain data for 24 Nepal river stations." />
      <Notice kind="info">
        Advisory only: these models never issue or change a warning — the rule engine and human approval still decide.
        Trained on {meta.period.start.slice(0, 4)}–{String(Number(meta.period.test_from.slice(0, 4)) - 1)} and scored on {meta.period.test_from.slice(0, 4)}–{meta.period.end.slice(0, 4)}, years the models never saw.
        Data: {meta.data_sources.join("; ")}. Flood levels are each station&apos;s own daily-flow percentiles (WATCH ≥ P90, WARNING ≥ P97, CRITICAL ≥ P99.5).
      </Notice>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Stat label="Risk level in next 3 days" value={pct(c.random_forest.warning_recall)} sub="of WARNING+ days caught" />
        <Stat label="Flood or not, from rain alone" value={c.flood_svm_rain_only.roc_auc.toFixed(2)} sub="ROC AUC" />
        <Stat label="River flow 1 day ahead" value={`${r.xgboost["1d"].median_abs_pct_error}%`} sub={`median error (no-change: ${r.persistence_baseline["1d"].median_abs_pct_error}%)`} />
        <Stat label="River flow 3 days ahead" value={`${r.xgboost["3d"].median_abs_pct_error}%`} sub={`median error (no-change: ${r.persistence_baseline["3d"].median_abs_pct_error}%)`} />
        <Stat label="Warning agent: warned early" value={pct(d.dqn.warned_in_advance)} sub={`of ${d.dqn.flood_events} floods · rule: ${pct(d.threshold_rule_today.warned_in_advance)}`} />
        <Stat label="Groups of similar rivers" value={m.clustering.k} sub={`separation score ${m.clustering.silhouette}`} />
      </div>

      <Outlook30 data={o30} error={o30Err as Error | undefined} />

      <Outlook data={outlook} error={outErr as Error | undefined} />

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Risk level in the next 3 days" note={`${meta.samples.test.toLocaleString()} test days · WARNING+ days: ${meta.class_counts_test[2] + meta.class_counts_test[3]}`}>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-400"><tr><th className="py-1">Model</th><th>Accuracy</th><th>Macro F1</th><th title="Share of real WARNING/CRITICAL days the model called WARNING or higher">Flood recall</th><th title="Share of the model's WARNING+ calls that were right">Flood precision</th></tr></thead>
            <tbody>{(["baseline_today_class", "logistic_regression", "random_forest", "svm"] as const).map((k) => (
              <tr key={k} className="border-t border-white/5"><td className="py-1.5">{MODEL_NAME[k]}</td><td>{pct(c[k].accuracy)}</td><td>{c[k].macro_f1.toFixed(2)}</td><td>{pct(c[k].warning_recall)}</td><td>{pct(c[k].warning_precision)}</td></tr>
            ))}</tbody>
          </table>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <Confusion title="Vote of rule sets — what it called vs what happened" m={c.random_forest.confusion} labels={LEVELS} />
            <Bars title="Vote of rule sets — what it looks at" values={c.random_forest.feature_importance ?? {}} />
          </div>
          <div className="mt-4 rounded-lg bg-black/20 p-3 text-sm">
            <div className="font-medium">Flood or not, from <em>rain only</em> (no river reading)</div>
            <p className="text-xs text-slate-400">For places without a gauge. Trained on {c.flood_svm_rain_only.trained_on.toLocaleString()} days.</p>
            <div className="mt-2 flex flex-wrap gap-4 text-xs">
              <span>ROC AUC <b>{c.flood_svm_rain_only.roc_auc}</b></span><span>Recall <b>{pct(c.flood_svm_rain_only.recall)}</b></span>
              <span>Precision <b>{pct(c.flood_svm_rain_only.precision)}</b></span><span>F1 <b>{c.flood_svm_rain_only.f1}</b></span>
            </div>
          </div>
        </Panel>

        <Panel title="River flow 1 and 3 days ahead" note="Skill = how much better than assuming “no change” (1 = perfect, 0 = no better)">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-400"><tr><th className="py-1">Model</th><th>Skill +1 d</th><th>Skill +3 d</th><th>Median error +1 d</th><th>+3 d</th><th title="Median error on days at WATCH level or above">High flows +1 d</th></tr></thead>
            <tbody>{(["persistence_baseline", "linear_regression", "xgboost", "lstm"] as const).map((k) => (
              <tr key={k} className="border-t border-white/5"><td className="py-1.5">{MODEL_NAME[k]}</td><td>{r[k]["1d"].skill_vs_persistence.toFixed(2)}</td><td>{r[k]["3d"].skill_vs_persistence.toFixed(2)}</td>
                <td>{r[k]["1d"].median_abs_pct_error}%</td><td>{r[k]["3d"].median_abs_pct_error}%</td><td>{r[k]["1d"].median_abs_pct_error_high_flow ?? "—"}%</td></tr>
            ))}</tbody>
          </table>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <Bars title="Step-by-step estimate — what it looks at (+1 day)" values={r.xgboost.feature_importance_1d ?? {}} />
            <div>
              <div className="mb-1 text-xs font-semibold text-slate-300">30-day reader — training error by pass over the data</div>
              <Line points={(r.lstm.train_loss_by_epoch ?? []).map((v, i) => [i + 1, v])} xLabel="pass" yLabel="error" color="#76b7b2" />
            </div>
          </div>
        </Panel>
      </div>

      <Panel title="Warning agent — learns when to warn by trial and reward" note={`${m.dqn.steps.toLocaleString()} practice days · ${m.dqn.episodes} practice runs of ${m.dqn.episode_days} days`}>
        <p className="text-sm text-slate-300">
          The agent looks at today&apos;s river flow, rain, rain forecast, season and the level currently shown, and chooses which level to show
          (NORMAL / WATCH / WARNING / CRITICAL). It learns from a score, not from answers — <span className="text-slate-400">{m.dqn.reward}</span>.
          Because it is judged on what happens over the <b>next 3 days</b>, it learns to warn early.
        </p>
        <div className="mt-3 grid gap-4 lg:grid-cols-2">
          <div>
            <div className="mb-1 text-xs font-semibold text-slate-300">Learning curve — average score per day as it practised</div>
            <Line points={m.dqn.training_curve.map((p) => [p.episode, p.mean_reward_per_day])} xLabel="practice run" yLabel="score / day" color="#edc948" />
          </div>
          <div className="overflow-x-auto">
            <div className="mb-1 text-xs font-semibold text-slate-300">Test years {meta.period.test_from.slice(0, 4)}–{meta.period.end.slice(0, 4)}: {d.dqn.flood_events} floods across 24 stations</div>
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-400"><tr><th className="py-1">Approach</th><th title="Flood onsets with a WARNING+ shown 1-3 days before">Warned before</th><th>By onset day</th><th>Mean lead</th><th title="Share of WARNING+ days with no flood in the next 3 days">False alarms</th><th>Changes / yr</th><th>Score / day</th></tr></thead>
              <tbody>{(["threshold_rule_today", "random_forest", "dqn"] as const).map((k) => (
                <tr key={k} className={`border-t border-white/5 ${k === "dqn" ? "font-medium text-amber-100" : ""}`}><td className="py-1.5">{MODEL_NAME[k]}</td><td>{pct(d[k].warned_in_advance)}</td><td>{pct(d[k].warned_by_onset_day)}</td>
                  <td>{d[k].mean_lead_days} d</td><td>{pct(d[k].false_alarm_ratio)}</td><td>{d[k].level_changes_per_station_year}</td><td>{d[k].mean_reward_per_day}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      </Panel>

      <div className="grid gap-4 xl:grid-cols-2">
        <Clusters meta={meta} cl={m.clustering} />
        <Panel title="Faulty-reading finder — real gauge readings" note={`trained on ${m.anomaly.readings.toLocaleString()} readings from ${m.anomaly.gauges} gauges`}>
          <p className="text-xs text-slate-400">{m.anomaly.note} In training it flagged {m.anomaly.flagged} readings ({pct(m.anomaly.flagged_share)}); the rule checks had flagged {m.anomaly.rule_flagged}, {m.anomaly.also_flagged_by_rules} of them the same.</p>
          {!anom ? <p className="mt-2 text-sm text-slate-400">Scoring recent readings…</p> : anom.anomalies.length === 0
            ? <Empty>No unusual readings in the last {anom.hours} hours ({anom.readings_scored.toLocaleString()} readings from {anom.gauges} gauges checked).</Empty>
            : (
              <div className="mt-2 max-h-80 overflow-y-auto">
                <p className="mb-1 text-xs text-slate-300">{anom.total_anomalies} unusual of {anom.readings_scored.toLocaleString()} readings in the last {anom.hours} h</p>
                <table className="w-full text-xs">
                  <thead className="text-left text-slate-400"><tr><th className="py-1">Gauge</th><th>Time (UTC)</th><th>Level</th><th>Why</th><th>Rules</th></tr></thead>
                  <tbody>{anom.anomalies.slice(0, 50).map((a) => (
                    <tr key={`${a.station_id}-${a.observed_at}`} className="border-t border-white/5">
                      <td className="py-1"><a href={`/stations/${a.station_id}`} className="text-sky-300 hover:underline">{a.name}</a></td>
                      <td>{a.observed_at.slice(5, 16).replace("T", " ")}</td><td>{a.value_m.toFixed(2)} m</td><td>{a.main_reason}</td><td>{a.rule_quality}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
        </Panel>
      </div>

      <p className="text-[11px] text-slate-500">Trained {meta.trained_at.replace("T", " ").slice(0, 16)} UTC in {Math.round(meta.train_seconds / 60)} min · {Object.entries(meta.versions).map(([k, v]) => `${k} ${v}`).join(" · ")} · retrain: <code>docker compose --profile ml run --rm ml-train</code></p>
    </div>
  );
}

function Outlook({ data, error }: { data?: { today: string; stations: OutlookStation[]; note: string }; error?: Error }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <Panel title="Today — what each model says" note={data ? `GloFAS flow as of ${data.stations[0]?.as_of ?? data.today} · rain forecast for the next 3 days` : undefined}>
      {error ? <Notice kind="warn">{error.message}</Notice> : !data ? <p className="text-sm text-slate-400">Fetching live river flow and rain forecast for 24 stations…</p> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1000px] text-xs">
            <thead className="text-left text-slate-400">
              <tr><th className="py-1">Station</th><th>Last 30 days</th><th>Flow now</th><th>Now</th><th title="Rain over the last 7 days / forecast for the next 3 and 7 days">Rain past 7 d / next 3 d / 7 d</th>
                <th>Weighted score</th><th>Rule-set vote</th><th>Boundary finder</th><th title="Chance of WARNING+ in 3 days, judged from rain only">Flood chance (rain)</th>
                <th title="Straight-line / step-by-step / 30-day reader">Flow +1 d (3 estimates)</th><th>Flow +3 d</th><th>Warning agent</th></tr>
            </thead>
            <tbody>{data.stations.map((s) => (
              <Fragment key={s.station_id}>
                <tr className="cursor-pointer border-t border-white/5 hover:bg-white/[0.03]" onClick={() => setOpen(open === s.station_id ? null : s.station_id)}>
                  <td className="py-1.5 pr-2"><div className="font-medium text-slate-200">{s.name}</div><div className="text-[10px] text-slate-500">{s.cluster_name}</div></td>
                  <td><Spark values={s.flow_30d} warn={s.thresholds_m3s.warning} /></td>
                  <td className="tabular-nums">{s.flow_m3s.toLocaleString()} m³/s</td>
                  <td><LevelBadge level={s.level_now} /></td>
                  <td className="tabular-nums">{s.rain_7d_mm} / {s.forecast_rain_3d_mm} / {s.forecast_rain_7d_mm} mm</td>
                  {(["logistic_regression", "random_forest", "svm"] as const).map((k) => <td key={k}><LevelBadge level={s.classification[k].level} /></td>)}
                  <td className="tabular-nums">{pct(s.flood_probability_rain_only)}</td>
                  <td className="tabular-nums">{s.regression.linear_regression.flow_1d_m3s} / {s.regression.xgboost.flow_1d_m3s} / {s.regression.lstm.flow_1d_m3s}</td>
                  <td className="tabular-nums">{s.regression.linear_regression.flow_3d_m3s} / {s.regression.xgboost.flow_3d_m3s} / {s.regression.lstm.flow_3d_m3s}</td>
                  <td><span className="text-slate-400">{s.dqn.current_alert === s.dqn.recommended ? "keep " : `${s.dqn.current_alert} → `}</span><LevelBadge level={s.dqn.recommended} /></td>
                </tr>
                {open === s.station_id && (
                  <tr className="bg-black/20"><td colSpan={12} className="p-3">
                    <div className="grid gap-3 text-[11px] md:grid-cols-3">
                      <div><div className="mb-1 font-semibold text-slate-300">Chance of each level</div>
                        {(["logistic_regression", "random_forest", "svm"] as const).map((k) => (
                          <div key={k} className="mb-1"><span className="inline-block w-48 text-slate-400">{MODEL_NAME[k]}</span>
                            {LEVELS.map((l, i) => <span key={l} className="mr-2">{l.slice(0, 4)} {pct(s.classification[k].probabilities[i])}</span>)}</div>
                        ))}</div>
                      <div><div className="mb-1 font-semibold text-slate-300">Warning agent — expected score of each choice</div>
                        {LEVELS.map((l, i) => <div key={l}><span className="inline-block w-20 text-slate-400">{l}</span>{s.dqn.q_values[i].toFixed(2)}{l === s.dqn.recommended ? " ← best" : ""}</div>)}
                        <div className="mt-1 text-slate-500">Current alert comes from the rule engine&apos;s latest level for this gauge.</div></div>
                      <div><div className="mb-1 font-semibold text-slate-300">This station&apos;s flood flows (from 2019–2022)</div>
                        <div>WATCH ≥ {s.thresholds_m3s.watch} m³/s</div><div>WARNING ≥ {s.thresholds_m3s.warning} m³/s</div><div>CRITICAL ≥ {s.thresholds_m3s.critical} m³/s</div>
                        <div className="mt-2 mb-1 font-semibold text-slate-300">Other inputs today</div>
                        <div>Upstream: {s.upstream.length ? `${s.upstream_flow_m3s?.toLocaleString()} m³/s from ${s.upstream.map((u) => u.replace(/ (River )?at .*/, "")).join(", ")}` : "no model station upstream"}</div>
                        <div>Rain forecast uncertainty: {s.forecast_uncertainty < 0.25 ? "low" : s.forecast_uncertainty < 0.5 ? "medium" : "high"} ({s.forecast_uncertainty})</div>
                        <div>Soil wetness: {s.soil_moisture} m³/m³</div>
                        <div>Mountain temperature: {s.headwater_temp_c} °C · snow last 30 days: {s.headwater_snow_30d_cm} cm</div></div>
                    </div>
                  </td></tr>
                )}
              </Fragment>
            ))}</tbody>
          </table>
          <p className="mt-2 text-[11px] text-slate-500">{data.note} Click a row for the chances and the agent&apos;s scores.</p>
        </div>
      )}
    </Panel>
  );
}

function Clusters({ meta, cl }: { meta: Meta; cl: Metrics["clustering"] }) {
  const [hover, setHover] = useState<string | null>(null);
  const pts = meta.stations.map((s) => s.pca);
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const W = 420, H = 240, pad = 18;
  const sx = (v: number) => pad + ((v - x0) / (x1 - x0 || 1)) * (W - 2 * pad), sy = (v: number) => H - pad - ((v - y0) / (y1 - y0 || 1)) * (H - 2 * pad);
  return (
    <Panel title="Groups of rivers with similar rain and flow" note={`${cl.k} groups · separation score ${cl.silhouette}`}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-lg bg-black/20" role="img" aria-label="Stations placed by how alike their rain and flow are, coloured by group">
        {meta.stations.map((s) => (
          <circle key={s.id} cx={sx(s.pca[0])} cy={sy(s.pca[1])} r={hover === s.name ? 7 : 5} fill={CLUSTER_COLORS[s.cluster % 5]} stroke="#0b1220"
            onMouseEnter={() => setHover(s.name)} onMouseLeave={() => setHover(null)}><title>{s.name}</title></circle>
        ))}
        <text x={W - 6} y={H - 4} textAnchor="end" fontSize="9" fill="#64748b">more alike →</text>
        <text x={6} y={12} fontSize="9" fill="#64748b">↑</text>
        {hover && <text x={W / 2} y={14} textAnchor="middle" fontSize="11" fill="#e2e8f0">{hover}</text>}
      </svg>
      <div className="mt-2 space-y-2 text-xs">
        {cl.names.map((n, i) => (
          <div key={i}>
            <div className="flex items-center gap-2 font-medium"><span className="h-2.5 w-2.5 rounded-full" style={{ background: CLUSTER_COLORS[i % 5] }} />{n} · {cl.sizes[i]} stations</div>
            <div className="text-slate-400">{Math.round(cl.centres[i].annual_rain_mm)} mm rain/yr · {pct(cl.centres[i].monsoon_share)} in Jun–Sep · median flow {Math.round(10 ** cl.centres[i].log10_median_flow)} m³/s ·
              {" "}{meta.stations.filter((s) => s.cluster === i).map((s) => s.name.replace(/ (River )?at .*/, "")).join(", ")}</div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function Confusion({ title, m, labels }: { title: string; m: number[][]; labels: string[] }) {
  const max = Math.max(...m.flat(), 1);
  return (
    <div>
      <div className="mb-1 text-xs font-semibold text-slate-300">{title}</div>
      <table className="text-[10px]">
        <thead><tr><th className="pr-1 text-left text-slate-500">true ↓ / predicted →</th>{labels.map((l) => <th key={l} className="px-1 text-slate-400">{l.slice(0, 4)}</th>)}</tr></thead>
        <tbody>{m.map((row, i) => (
          <tr key={i}><td className="pr-1 text-slate-400">{labels[i]}</td>{row.map((v, j) => (
            <td key={j} className="px-1 py-0.5 text-center tabular-nums" style={{ background: `rgba(${i === j ? "89,161,79" : "225,87,89"},${(v / max) ** 0.5 * 0.8})` }}>{v}</td>
          ))}</tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function Bars({ title, values }: { title: string; values: Record<string, number> }) {
  const top = Object.entries(values).slice(0, 10), max = Math.max(...top.map(([, v]) => v), 1e-9);
  return (
    <div>
      <div className="mb-1 text-xs font-semibold text-slate-300">{title}</div>
      {top.map(([k, v]) => (
        <div key={k} className="mb-0.5 flex items-center gap-2 text-[10px]">
          <span className="w-36 shrink-0 truncate text-slate-400">{INPUT_LABEL[k] ?? k.replaceAll("_", " ")}</span>
          <span className="h-2 rounded bg-sky-400/70" style={{ width: `${(v / max) * 100}%` }} />
          <span className="tabular-nums text-slate-500">{v.toFixed(2)}</span>
        </div>
      ))}
    </div>
  );
}

function Line({ points, xLabel, yLabel, color }: { points: [number, number][]; xLabel: string; yLabel: string; color: string }) {
  if (points.length < 2) return <p className="text-xs text-slate-500">No data.</p>;
  const W = 420, H = 150, l = 34, b = 18;
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const sx = (v: number) => l + ((v - x0) / (x1 - x0 || 1)) * (W - l - 6), sy = (v: number) => 6 + (1 - (v - y0) / (y1 - y0 || 1)) * (H - b - 12);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`${yLabel} by ${xLabel}`}>
      <polyline points={points.map(([x, y]) => `${sx(x)},${sy(y)}`).join(" ")} fill="none" stroke={color} strokeWidth="2" />
      {[y0, (y0 + y1) / 2, y1].map((v) => <text key={v} x={l - 4} y={sy(v) + 3} textAnchor="end" fontSize="9" fill="#94a3b8">{v.toFixed(Math.abs(y1 - y0) < 1 ? 3 : 1)}</text>)}
      <text x={l} y={H - 3} fontSize="9" fill="#94a3b8">{x0}</text>
      <text x={W - 6} y={H - 3} textAnchor="end" fontSize="9" fill="#94a3b8">{x1} {xLabel}</text>
      <line x1={l} x2={W - 6} y1={H - b} y2={H - b} stroke="#334155" />
    </svg>
  );
}

function Spark({ values, warn }: { values: number[]; warn: number }) {
  const W = 90, H = 24, max = Math.max(...values, warn), min = Math.min(...values);
  const y = (v: number) => H - 2 - ((v - min) / (max - min || 1)) * (H - 4);
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-label="flow over the last 30 days">
      <line x1={0} x2={W} y1={y(warn)} y2={y(warn)} stroke="#e8a33d" strokeDasharray="2 2" strokeWidth="1" />
      <polyline points={values.map((v, i) => `${(i / (values.length - 1)) * W},${y(v)}`).join(" ")} fill="none" stroke="#7dd3fc" strokeWidth="1.5" />
    </svg>
  );
}

const shortDate = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });

function Outlook30({ data, error }: { data?: Outlook30Data; error?: Error }) {
  const [open, setOpen] = useState<number | null>(null);
  const days = data?.stations[0]?.days ?? [];
  const seasonalFrom = days.findIndex((d) => d.rain_source !== "forecast");
  const counts = LEVELS.map((l) => data?.stations.filter((s) => s.highest_level === l).length ?? 0);
  const sep = (i: number) => (i === seasonalFrom ? { borderLeft: "2px dashed #94a3b8", paddingLeft: 1 } : {});
  return (
    <Panel title="Next 30 days — warning agent outlook" note={data ? `from ${shortDate(data.today)} · ${data.stations[0]?.futures ?? 0} possible river futures per station` : undefined}>
      {error ? <Notice kind="warn">{error.message}</Notice> : !data ? <p className="text-sm text-slate-400">Running the warning agent through 51 possible futures for 24 rivers (up to a minute the first time)…</p> : (
        <div>
          <p className="mb-2 text-xs text-slate-400">{data.method}</p>
          <div className="mb-3 flex flex-wrap gap-3 text-xs">
            {LEVELS.map((l, i) => <span key={l} className="flex items-center gap-1.5"><LevelBadge level={l} /> highest for {counts[i]} station{counts[i] === 1 ? "" : "s"}</span>)}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-xs">
              <thead className="text-left text-slate-400">
                <tr><th className="py-1 pr-2">Station</th><th>Now</th><th>Highest</th>
                  <th>
                    <div className="flex gap-0.5">
                      {days.map((d, i) => (
                        <span key={d.date} className="w-4 shrink-0 text-center text-[9px] font-normal" style={sep(i)}>
                          {i % 5 === 0 ? shortDate(d.date) : ""}
                        </span>
                      ))}
                    </div>
                  </th></tr>
              </thead>
              <tbody>{data.stations.map((s) => (
                <Fragment key={s.station_id}>
                  <tr className="cursor-pointer border-t border-white/5 hover:bg-white/[0.03]" onClick={() => setOpen(open === s.station_id ? null : s.station_id)}>
                    <td className="py-1.5 pr-2 font-medium text-slate-200">{s.name}</td>
                    <td><LevelBadge level={s.current_level} /></td>
                    <td className="pr-2 whitespace-nowrap"><LevelBadge level={s.highest_level} />{s.highest_level !== "NORMAL" && <span className="ml-1 text-slate-400">{shortDate(s.highest_level_date)}</span>}</td>
                    <td>
                      <div className="flex gap-0.5">
                        {s.days.map((d, i) => (
                          <span key={d.date} className="block h-4 w-4 shrink-0 rounded-sm"
                            style={{ background: LEVEL_COLOR[d.level], opacity: d.level === "NORMAL" ? 0.35 + (1 - d.probabilities[0]) * 0.65 : 1, ...sep(i) }}
                            title={`${shortDate(d.date)}: ${d.level}\n` + LEVELS.map((l, k) => `${l} ${pct(d.probabilities[k])}`).join(" · ") +
                              `\nflow ${d.flow_m3s.low}–${d.flow_m3s.high} m³/s (middle ${d.flow_m3s.middle})\nrain ${d.rain_mm} mm (${d.rain_source})`} />
                        ))}
                      </div>
                    </td>
                  </tr>
                  {open === s.station_id && (
                    <tr className="bg-black/20"><td colSpan={4} className="p-3"><Detail30 s={s} /></td></tr>
                  )}
                </Fragment>
              ))}</tbody>
            </table>
          </div>
          <p className="mt-2 text-[11px] text-slate-500">
            Each square is one day, coloured by the level the agent would show; a paler square means a lower chance of anything above NORMAL.
            Right of the dashed line, rain is a seasonal average, not a forecast. Hover a square for details, click a row for the flow chart. {data.note}
          </p>
        </div>
      )}
    </Panel>
  );
}

function Detail30({ s }: { s: Station30 }) {
  const W = 640, H = 170, pad = 30;
  const top = Math.max(s.thresholds_m3s.warning * 1.05, ...s.days.map((d) => d.flow_m3s.high));
  const x = (i: number) => pad + (i / Math.max(s.days.length - 1, 1)) * (W - pad - 8);
  const y = (v: number) => H - 18 - (v / top) * (H - 30);
  const band = [...s.days.map((d, i) => `${x(i)},${y(d.flow_m3s.high)}`), ...s.days.map((d, i) => `${x(i)},${y(d.flow_m3s.low)}`).reverse()].join(" ");
  return (
    <div className="grid gap-4 md:grid-cols-[2fr_1fr]">
      <div>
        <div className="mb-1 text-[11px] font-semibold text-slate-300">River flow over the next {s.days.length} days (shaded: likely range across the {s.futures} futures)</div>
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`Forecast flow for ${s.name}`}>
          {(["WATCH", "WARNING"] as const).map((l) => {
            const v = s.thresholds_m3s[l.toLowerCase() as "watch" | "warning"];
            return v <= top && (
              <g key={l}>
                <line x1={pad} x2={W - 8} y1={y(v)} y2={y(v)} stroke={LEVEL_COLOR[l]} strokeDasharray="4 3" />
                <text x={W - 10} y={y(v) - 3} textAnchor="end" fontSize="9" fill={LEVEL_COLOR[l]}>{l} {v} m³/s</text>
              </g>
            );
          })}
          <polygon points={band} fill="#76b7b2" opacity="0.25" />
          <polyline points={s.days.map((d, i) => `${x(i)},${y(d.flow_m3s.middle)}`).join(" ")} fill="none" stroke="#76b7b2" strokeWidth="2" />
          {s.days.map((d, i) => i % 5 === 0 && <text key={d.date} x={x(i)} y={H - 4} textAnchor="middle" fontSize="9" fill="#64748b">{shortDate(d.date)}</text>)}
          <text x={4} y={12} fontSize="9" fill="#64748b">m³/s</text>
          <text x={4} y={y(0) + 3} fontSize="9" fill="#64748b">0</text>
        </svg>
      </div>
      <div className="text-[11px]">
        <div className="mb-1 font-semibold text-slate-300">First day each level is expected</div>
        {(["watch", "warning", "critical"] as const).map((k) => (
          <div key={k} className="mb-0.5 flex items-center gap-2"><span className="w-16"><LevelBadge level={k.toUpperCase()} /></span>{s.first_date[k] ? shortDate(s.first_date[k]!) : "not in the next 30 days"}</div>
        ))}
        <div className="mt-2 font-semibold text-slate-300">Chance the river itself reaches WARNING flow</div>
        <div className="text-slate-400">at most {pct(Math.max(...s.days.map((d) => d.chance_flow_at_or_above.warning)))} of futures on any day</div>
      </div>
    </div>
  );
}
