"use client";
// Charts (ECharts, tree-shaken, SVG renderer). Colours come from the page's CSS tokens so light and dark mode
// both follow the design tokens; one series hue, neutrals for ranges and expectations, status red only for a limit.
import ReactEChartsCore from "echarts-for-react/lib/core";
import { BarChart, LineChart } from "echarts/charts";
import { AriaComponent, GridComponent, LegendComponent, MarkAreaComponent, MarkLineComponent,
         TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { SVGRenderer } from "echarts/renderers";
import { useEffect, useState } from "react";
import { formatNumber, sar } from "@/lib/format";

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent,
             MarkAreaComponent, AriaComponent, SVGRenderer]);

type Tokens = { ink: string; muted: string; series: string; band: string; grid: string; act: string; paper: string };
const FALLBACK: Tokens = { ink: "#14213d", muted: "#5b6475", series: "#2a78d6", band: "#d9dde5", grid: "#e4e7ec",
                           act: "#b42318", paper: "#f7f8fa" };

function useTokens(): Tokens {
  const [tokens, setTokens] = useState(FALLBACK);
  useEffect(() => {
    const read = () => {
      const s = getComputedStyle(document.documentElement);
      const v = (name: string, fb: string) => s.getPropertyValue(name).trim() || fb;
      setTokens({ ink: v("--ink", FALLBACK.ink), muted: v("--muted", FALLBACK.muted),
                  series: v("--series-1", FALLBACK.series), band: v("--band", FALLBACK.band),
                  grid: v("--grid", FALLBACK.grid), act: v("--act", FALLBACK.act), paper: v("--paper", FALLBACK.paper) });
    };
    read();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", read);
    return () => mq.removeEventListener("change", read);
  }, []);
  return tokens;
}

const axis = (t: Tokens) => ({
  axisLine: { lineStyle: { color: t.grid } }, axisTick: { show: false },
  axisLabel: { color: t.muted, fontFamily: "inherit" }, splitLine: { lineStyle: { color: t.grid } },
});
const tooltip = (t: Tokens) => ({
  backgroundColor: t.paper, borderColor: t.grid, textStyle: { color: t.ink, fontFamily: "inherit" },
});

function Frame({ option, height, label }: { option: object; height: number; label: string }) {
  return (
    <div role="img" aria-label={label}>
      <ReactEChartsCore echarts={echarts} option={option} notMerge style={{ height, width: "100%" }}
                        opts={{ renderer: "svg" }} />
    </div>
  );
}

/** A KPI over time with its normal range as a grey band (§12.2). */
export function SeriesChart({ months, values, lower, upper, unit, name }: {
  months: string[]; values: (number | null)[]; lower: number | null; upper: number | null; unit: string; name: string;
}) {
  const t = useTokens();
  const option = {
    aria: { enabled: true }, animation: false,
    grid: { left: 64, right: 16, top: 16, bottom: 28 },
    tooltip: { trigger: "axis", ...tooltip(t), axisPointer: { type: "line", lineStyle: { color: t.muted } },
               valueFormatter: (v: number) => (v == null ? "n.m." : formatNumber(v, unit)) },
    xAxis: { type: "category", data: months, ...axis(t), splitLine: { show: false } },
    yAxis: { type: "value", scale: true, ...axis(t), axisLabel: { ...axis(t).axisLabel,
             formatter: (v: number) => formatNumber(v, unit) } },
    series: [{
      name, type: "line", data: values, showSymbol: false, connectNulls: false,
      lineStyle: { width: 2, color: t.series }, itemStyle: { color: t.series },
      markArea: lower != null && upper != null ? { silent: true, itemStyle: { color: t.band, opacity: 0.55 },
        label: { show: true, position: "insideTopLeft", color: t.muted, formatter: "Normal range" },
        data: [[{ yAxis: lower }, { yAxis: upper }]] } : undefined,
    }],
  };
  return <Frame option={option} height={240} label={`${name} over the last ${months.length} months`} />;
}

/** The 13-week cash fan (§12.8): the 10th–90th percentile band, the median and the minimum. */
export function FanChart({ weeks, minimum }: {
  weeks: { start: string; p10: number; p50: number; p90: number }[]; minimum: number;
}) {
  const t = useTokens();
  const labels = weeks.map((w) => new Date(`${w.start}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }));
  const option = {
    aria: { enabled: true }, animation: false,
    grid: { left: 72, right: 24, top: 28, bottom: 64 },
    legend: { bottom: 0, textStyle: { color: t.muted }, data: ["Median", "1 in 10 low – 1 in 10 high"] },
    tooltip: { trigger: "axis", ...tooltip(t), formatter: (items: { dataIndex: number }[]) => {
      const w = weeks[items[0].dataIndex];
      return `Week from ${w.start}<br/>Median ${sar(w.p50)}<br/>1 in 10 low ${sar(w.p10)}<br/>1 in 10 high ${sar(w.p90)}`;
    } },
    xAxis: { type: "category", data: labels, boundaryGap: false, ...axis(t), splitLine: { show: false } },
    yAxis: { type: "value", scale: true, ...axis(t), axisLabel: { ...axis(t).axisLabel, formatter: (v: number) => sar(v) } },
    series: [
      { name: "low", type: "line", stack: "fan", data: weeks.map((w) => w.p10), symbol: "none",
        lineStyle: { opacity: 0 }, tooltip: { show: false } },
      { name: "1 in 10 low – 1 in 10 high", type: "line", stack: "fan", data: weeks.map((w) => w.p90 - w.p10),
        symbol: "none", lineStyle: { opacity: 0 }, areaStyle: { color: t.series, opacity: 0.18 },
        itemStyle: { color: t.series } },
      { name: "Median", type: "line", data: weeks.map((w) => w.p50), symbol: "none",
        lineStyle: { width: 2, color: t.series }, itemStyle: { color: t.series },
        markLine: { silent: true, symbol: "none", lineStyle: { color: t.act, type: "dashed", width: 1.5 },
                    label: { formatter: `Minimum ${sar(minimum)}`, color: t.ink, position: "insideEndTop" },
                    data: [{ yAxis: minimum }] } },
    ],
  };
  return <Frame option={option} height={300} label="Thirteen-week cash forecast with its likely range and the minimum" />;
}

/** IT-01: first-two-digit shares of bill amounts against Benford's expected shares (§13). */
export function BenfordChart({ rows }: { rows: { digits: number; actual: number; expected: number }[] }) {
  const t = useTokens();
  const option = {
    aria: { enabled: true }, animation: false,
    grid: { left: 52, right: 16, top: 24, bottom: 40 },
    legend: { bottom: 0, textStyle: { color: t.muted }, data: ["Bills", "Benford's expected share"] },
    tooltip: { trigger: "axis", ...tooltip(t), valueFormatter: (v: number) => `${(v * 100).toFixed(2)}%` },
    xAxis: { type: "category", data: rows.map((r) => String(r.digits)), ...axis(t), splitLine: { show: false },
             axisLabel: { ...axis(t).axisLabel, interval: 9 } },
    yAxis: { type: "value", ...axis(t), axisLabel: { ...axis(t).axisLabel, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
    series: [
      { name: "Bills", type: "bar", data: rows.map((r) => r.actual), barCategoryGap: "25%",
        itemStyle: { color: t.series, borderRadius: [2, 2, 0, 0] } },
      { name: "Benford's expected share", type: "line", data: rows.map((r) => r.expected), symbol: "none",
        lineStyle: { width: 2, color: t.ink }, itemStyle: { color: t.ink } },
    ],
  };
  return <Frame option={option} height={260} label="Bill amounts' first two digits against Benford's law" />;
}
