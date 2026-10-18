"use client";

import dynamic from "next/dynamic";

// Client-only: the map reads the window size and uses WebGL.
const MapExplorer = dynamic(() => import("@/components/MapExplorer"), { ssr: false });

export default function MapPage() {
  return (
    <div className="relative -m-4 h-[calc(100vh-49px)] sm:-m-6">
      <MapExplorer />
    </div>
  );
}
