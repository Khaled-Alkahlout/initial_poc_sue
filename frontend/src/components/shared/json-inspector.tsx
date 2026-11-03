import { Braces } from "lucide-react";
export function JsonInspector({
  value,
  title = "Technische metadata",
}: {
  value: unknown;
  title?: string;
}) {
  return (
    <details className="inspector">
      <summary>
        <Braces size={15} />
        {title}
      </summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
