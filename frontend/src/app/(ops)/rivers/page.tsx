"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import StationTable from "@/components/StationTable";
import { PageHeader } from "@/components/ui";
import { useRivers } from "@/lib/hooks";

function Rivers() {
  const level = useSearchParams().get("level") ?? undefined;
  const { data } = useRivers();
  return <StationTable data={data} kind="river" initialLevel={level} key={level ?? "all"} />;
}

export default function RiversPage() {
  return (
    <div>
      <PageHeader title="River gauges" subtitle="Live DHM river-level stations and their own devices. Index 1.0 = at the station's warning level. Risk comes from rules R1–R10." />
      <Suspense fallback={<p className="text-sm text-slate-400">Loading…</p>}><Rivers /></Suspense>
    </div>
  );
}
