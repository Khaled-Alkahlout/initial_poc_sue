import Link from "next/link";
import { EmptyState } from "@/components/shared/states";
import { Button } from "@/components/ui/button";
export default function NotFound() {
  return (
    <div className="stack">
      <EmptyState
        title="Niet gevonden"
        description="Deze query, run of evaluatie bestaat niet in de beschikbare gegevens."
      />
      <Button asChild variant="outline">
        <Link href="/">Terug naar overzicht</Link>
      </Button>
    </div>
  );
}
