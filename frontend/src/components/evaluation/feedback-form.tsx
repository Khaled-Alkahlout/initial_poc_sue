"use client";
import { useCallback, useState } from "react";
import { MessageSquare } from "lucide-react";
import { api, errorMessage } from "@/lib/api/client";
import type { FeedbackInput } from "@/lib/api/contracts";
import { useApi } from "@/hooks/use-api";
import { Card, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Select, Textarea } from "@/components/ui/fields";
import { Badge } from "@/components/shared/status";
import { dateTime } from "@/lib/formatters";

const labels = {
  correct: "Correct",
  incorrect: "Incorrect",
  needs_review: "Nader beoordelen",
};
export function FeedbackForm({
  targetId,
  targetType,
}: {
  targetId: string;
  targetType: FeedbackInput["target_type"];
}) {
  const loader = useCallback(() => api.getFeedback(targetId), [targetId]);
  const { data, error, refresh } = useApi(loader);
  const [label, setLabel] = useState<FeedbackInput["label"]>("needs_review");
  const [comment, setComment] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    setMessage(null);
    try {
      await api.submitFeedback({
        target_id: targetId,
        target_type: targetType,
        label,
        comment,
        reviewer,
      });
      setMessage(
        "Review opgeslagen. De technische uitslag blijft ongewijzigd.",
      );
      setComment("");
      refresh();
    } catch (reason) {
      setFailure(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card>
      <CardHeader
        title="Ontwikkelaarsreview"
        description="Een afzonderlijk oordeel van een reviewer; geen wijziging van metingen en geen feedback naar het model."
        action={<MessageSquare size={17} className="muted" />}
      />
      <div className="panel-body">
        <form onSubmit={submit} className="form-grid !mt-0">
          <div className="grid-two">
            <label className="field">
              <span>Reviewlabel</span>
              <Select
                value={label}
                onChange={(e) =>
                  setLabel(e.target.value as FeedbackInput["label"])
                }
              >
                {Object.entries(labels).map(([key, text]) => (
                  <option value={key} key={key}>
                    {text}
                  </option>
                ))}
              </Select>
            </label>
            <label className="field">
              <span>Reviewer · optioneel</span>
              <Input
                maxLength={80}
                value={reviewer}
                onChange={(e) => setReviewer(e.target.value)}
                placeholder="Naam of initialen"
              />
            </label>
          </div>
          <label className="field">
            <span>Toelichting · optioneel</span>
            <Textarea
              rows={3}
              maxLength={2000}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Welke aanname, afwijking of beperking verdient aandacht?"
            />
          </label>
          {(failure || error) && (
            <p role="alert" className="form-error">
              {failure || error}
            </p>
          )}
          {message && (
            <p role="status" className="success-message">
              {message}
            </p>
          )}
          <div className="form-actions">
            <Button type="submit" disabled={busy}>
              {busy ? "Opslaan…" : "Review opslaan"}
            </Button>
          </div>
        </form>
        {data?.map((review) => (
          <div className="feedback-record" key={review.id}>
            <Badge
              tone={
                review.label === "incorrect"
                  ? "red"
                  : review.label === "correct"
                    ? "green"
                    : "amber"
              }
            >
              {labels[review.label]}
            </Badge>
            {review.comment && <p>{review.comment}</p>}
            <small>
              {review.reviewer || "Anonieme reviewer"} ·{" "}
              {dateTime(review.created_at)}
            </small>
          </div>
        ))}
      </div>
    </Card>
  );
}
