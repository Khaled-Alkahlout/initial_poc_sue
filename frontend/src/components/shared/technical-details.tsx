import { Braces, ChevronDown } from "lucide-react";
import type { ReactNode } from "react";

export function TechnicalDetails({
  children,
  title = "Technical Details",
  description,
}: {
  children: ReactNode;
  title?: string;
  description?: string;
}) {
  return (
    <details className="panel technical-details">
      <summary>
        <span className="section-icon">
          <Braces size={17} />
        </span>
        <span>
          <strong>{title}</strong>
          {description && <small>{description}</small>}
        </span>
        <ChevronDown className="details-chevron" size={17} />
      </summary>
      <div className="panel-body stack">{children}</div>
    </details>
  );
}
