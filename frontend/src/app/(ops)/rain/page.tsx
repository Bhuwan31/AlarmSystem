"use client";

import StationTable from "@/components/StationTable";
import { PageHeader } from "@/components/ui";
import { useRain } from "@/lib/hooks";

export default function RainPage() {
  const { data } = useRain();
  return (
    <div>
      <PageHeader title="Rain gauges" subtitle="Live DHM rainfall stations. Heavy rain within 20 km of a river gauge raises that river to at least WATCH (rule R6)." />
      <StationTable data={data} kind="rain" />
    </div>
  );
}
