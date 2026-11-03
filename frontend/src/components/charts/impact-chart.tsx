"use client";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Query } from "@/lib/api/contracts";
import { count } from "@/lib/formatters";
export function ImpactChart({ queries }: { queries: Query[] }) {
  return (
    <div
      className="chart"
      aria-label="Totale workloadimpact per query; gesimuleerde cijfers"
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={queries}
          layout="vertical"
          margin={{ top: 15, right: 25, bottom: 5, left: 0 }}
        >
          <CartesianGrid stroke="var(--border)" horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={count}
            tick={{ fontSize: 9, fill: "var(--muted)" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            dataKey="query_id"
            type="category"
            width={118}
            tick={{ fontSize: 10, fill: "var(--muted)" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            formatter={(value) => [
              `${count(Number(value))} ms`,
              "Totale impact",
            ]}
            contentStyle={{
              background: "var(--surface)",
              borderColor: "var(--border)",
              borderRadius: 6,
              fontSize: 11,
            }}
            cursor={{ fill: "var(--surface-subtle)" }}
          />
          <Bar
            dataKey="impact_ms"
            fill="var(--accent)"
            radius={[0, 4, 4, 0]}
            barSize={20}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
