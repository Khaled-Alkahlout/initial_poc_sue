"use client";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Overview } from "@/lib/api/contracts";
export function ConditionChart({ data }: { data: Overview["conditions"] }) {
  return (
    <div
      className="chart"
      aria-label="Historische uitkomsten per contextconditie"
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          margin={{ top: 10, right: 20, left: -20, bottom: 5 }}
        >
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="condition"
            tick={{ fontSize: 10, fill: "var(--muted)" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fontSize: 10, fill: "var(--muted)" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "var(--surface)",
              borderColor: "var(--border)",
              borderRadius: 6,
              fontSize: 11,
            }}
          />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          <Bar
            dataKey="accepted"
            name="Geaccepteerd binnen test"
            fill="var(--accent)"
            isAnimationActive={false}
          />
          <Bar
            dataKey="rejected"
            name="Afgewezen"
            fill="var(--red)"
            isAnimationActive={false}
          />
          <Bar
            dataKey="inconclusive"
            name="Onbeslist / fout"
            fill="var(--amber)"
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
