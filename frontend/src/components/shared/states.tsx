"use client";
import { AlertCircle, Inbox, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
export function EmptyState({
  title = "Geen gegevens beschikbaar",
  description = "Voor deze selectie zijn nog geen resultaten vastgelegd.",
}: {
  title?: string;
  description?: string;
}) {
  return (
    <div className="empty-state">
      <Inbox size={28} />
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}
export function ErrorState({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="error-state" role="alert">
      <AlertCircle size={22} />
      <div>
        <h2>Gegevens niet beschikbaar</h2>
        <p>{message}</p>
        <Button
          variant="outline"
          onClick={retry ?? (() => window.location.reload())}
        >
          Opnieuw proberen
        </Button>
      </div>
    </div>
  );
}
export function LoadingState() {
  return (
    <div className="empty-state" role="status">
      <LoaderCircle className="spin" />
      <p>Gegevens ophalen…</p>
    </div>
  );
}
