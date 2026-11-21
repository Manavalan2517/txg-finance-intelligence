"use client";
// Charts load on demand: ECharts is the heaviest dependency, and most page views never open a chart.
import dynamic from "next/dynamic";

const box = (height: number) => function Placeholder() {
  return <div style={{ blockSize: height }} aria-busy="true" />;
};

export const SeriesChart = dynamic(() => import("./charts").then((m) => m.SeriesChart),
                                   { ssr: false, loading: box(240) });
export const FanChart = dynamic(() => import("./charts").then((m) => m.FanChart), { ssr: false, loading: box(300) });
export const BenfordChart = dynamic(() => import("./charts").then((m) => m.BenfordChart),
                                    { ssr: false, loading: box(260) });
