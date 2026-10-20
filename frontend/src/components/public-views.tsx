"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Star, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, Textarea } from "@/components/ui/fields";
import { ErrorState, LoadingBlock } from "@/components/ui/feedback";
import { api } from "@/lib/api";
import { readableOn } from "@/lib/branding";
import { formatDateTime, money, titleCase } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { PublicEstimate, PublicOrder, PublicReview } from "@/lib/types";

const ORDER_STEPS = [
  { key: "scheduled", label: "Scheduled" },
  { key: "in_progress", label: "In progress" },
  { key: "awaiting_parts", label: "Awaiting parts" },
  { key: "completed", label: "Completed" },
  { key: "invoiced", label: "Invoiced" },
];

function PublicShell({
  workspace,
  children,
}: {
  workspace: { display_name: string; primary_color: string; accent_color: string };
  children: React.ReactNode;
}) {
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--brand-primary", workspace.primary_color);
    root.style.setProperty("--brand-accent", workspace.accent_color);
    root.style.setProperty("--brand-primary-fg", readableOn(workspace.primary_color));
  }, [workspace.primary_color, workspace.accent_color]);

  return (
    <div className="min-h-screen bg-[var(--background)]">
      <header className="border-b border-[var(--border)]">
        <div className="mx-auto flex max-w-3xl items-center gap-2 px-4 py-4">
          <span className="rounded-lg bg-[var(--brand-primary)] p-1.5 text-[var(--brand-primary-fg)]">
            <Wrench className="h-4 w-4" aria-hidden="true" />
          </span>
          <span className="font-semibold tracking-tight">{workspace.display_name}</span>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-3xl px-4 py-8">
        {children}
      </main>
      <footer className="mx-auto max-w-3xl px-4 pb-8 text-xs text-[var(--muted-foreground)]">
        <p>
          Powered by{" "}
          <Link href="/" className="underline underline-offset-2">
            Vehicle Service Manager
          </Link>
        </p>
      </footer>
    </div>
  );
}

export function PublicOrderView() {
  const params = useParams<{ token: string }>();
  return <PublicOrderInner token={params.token ?? ""} />;
}

function PublicOrderInner({ token }: { token: string }) {
  const { data, error, isLoading, mutate } = useApi<PublicOrder>(
    token ? `/public/orders/${token}` : null,
  );

  if (error) {
    return (
      <PublicShell
        workspace={{
          display_name: "Vehicle Service Manager",
          primary_color: "#0f766e",
          accent_color: "#f59e0b",
        }}
      >
        <ErrorState
          message="This link is invalid or has expired. Ask the workshop to send a new one."
          retry={() => mutate()}
        />
      </PublicShell>
    );
  }
  if (isLoading && !data) return <LoadingBlock label="Loading your service order" />;
  if (!data) return null;

  const currentIndex = ORDER_STEPS.findIndex((step) => step.key === data.status);
  const cancelled = data.status === "cancelled";

  return (
    <PublicShell workspace={data.workspace}>
      <p className="text-sm text-[var(--muted-foreground)]">Service order</p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">{data.number}</h1>
      <p className="mt-1 text-sm text-[var(--muted-foreground)]">
        Last updated {formatDateTime(data.updated_at)}
      </p>

      <Card className="mt-6">
        <CardContent className="pt-6">
          {cancelled ? (
            <p className="font-medium text-[var(--destructive)]">This order was cancelled.</p>
          ) : (
            <ol className="grid gap-3 sm:grid-cols-5">
              {ORDER_STEPS.map((step, index) => {
                const done = currentIndex >= index && currentIndex !== -1;
                const active = currentIndex === index;
                return (
                  <li key={step.key} className="flex items-center gap-2 sm:flex-col sm:gap-1.5">
                    <span
                      className={
                        done
                          ? "flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--brand-primary)] text-xs font-semibold text-[var(--brand-primary-fg)]"
                          : "flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--muted)] text-xs font-semibold text-[var(--muted-foreground)]"
                      }
                      aria-hidden="true"
                    >
                      {index + 1}
                    </span>
                    <span
                      className={
                        active
                          ? "text-sm font-medium"
                          : "text-sm text-[var(--muted-foreground)]"
                      }
                      aria-current={active ? "step" : undefined}
                    >
                      {step.label}
                    </span>
                  </li>
                );
              })}
            </ol>
          )}
        </CardContent>
      </Card>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Card>
          <CardContent className="pt-6">
            <h2 className="text-sm font-medium">Vehicle</h2>
            <p className="mt-2 text-sm">
              {[data.vehicle.year, data.vehicle.make, data.vehicle.model]
                .filter(Boolean)
                .join(" ") || "—"}
            </p>
            <p className="text-sm text-[var(--muted-foreground)]">
              {data.vehicle.plate_number ?? "—"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <h2 className="text-sm font-medium">Schedule</h2>
            <p className="mt-2 text-sm">
              {data.scheduled_at
                ? `Scheduled for ${formatDateTime(data.scheduled_at)}`
                : "Not scheduled yet"}
            </p>
            <p className="text-sm text-[var(--muted-foreground)]">
              {data.completed_at
                ? `Completed ${formatDateTime(data.completed_at)}`
                : `Status: ${titleCase(data.status)}`}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardContent className="pt-6">
          <h2 className="text-sm font-medium">Work requested</h2>
          <p className="mt-2 whitespace-pre-wrap text-sm">{data.description}</p>
          {data.items.length > 0 && (
            <ul className="mt-4 space-y-2 border-t border-[var(--border)] pt-4 text-sm">
              {data.items.map((item, index) => (
                <li key={index} className="flex items-start justify-between gap-3">
                  <span>{item.description}</span>
                  <span className="shrink-0 text-xs capitalize text-[var(--muted-foreground)]">
                    {item.kind}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {data.inspection.length > 0 && (
        <Card className="mt-4">
          <CardContent className="pt-6">
            <h2 className="text-sm font-medium">
              Inspection{data.inspection_completed ? "" : " (in progress)"}
            </h2>
            <ul className="mt-3 space-y-3 text-sm">
              {data.inspection.map((item, index) => (
                <li key={index}>
                  <div className="flex items-start justify-between gap-3">
                    <span>{item.label}</span>
                    <span
                      className={
                        item.status === "ok"
                          ? "shrink-0 text-xs font-medium text-[var(--success)]"
                          : item.status === "attention"
                            ? "shrink-0 text-xs font-medium text-[var(--status-in-progress)]"
                            : item.status === "critical"
                              ? "shrink-0 text-xs font-medium text-[var(--destructive)]"
                              : "shrink-0 text-xs text-[var(--muted-foreground)]"
                      }
                    >
                      {item.status === "na" ? "N/A" : titleCase(item.status)}
                    </span>
                  </div>
                  {item.note && (
                    <p className="mt-0.5 text-[var(--muted-foreground)]">{item.note}</p>
                  )}
                  {item.photos.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {item.photos.map((src) => (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          key={src}
                          src={src}
                          alt={`${item.label} photo`}
                          className="h-20 w-20 rounded-md border border-[var(--border)] object-cover"
                          loading="lazy"
                        />
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <div className="mt-6 rounded-xl border border-[var(--border)] bg-[var(--muted)] p-4 text-sm text-[var(--muted-foreground)]">
        <p>
          Questions about this job?{" "}
          {data.workspace.support_email ? (
            <a
              className="text-[var(--brand-text)] underline underline-offset-2"
              href={`mailto:${data.workspace.support_email}`}
            >
              Email {data.workspace.display_name}
            </a>
          ) : (
            "Contact the workshop and quote this order number."
          )}
        </p>
      </div>
    </PublicShell>
  );
}

export function PublicEstimateView() {
  const params = useParams<{ token: string }>();
  return <PublicEstimateInner token={params.token ?? ""} />;
}

function PublicEstimateInner({ token }: { token: string }) {
  const { data, error, isLoading, mutate } = useApi<PublicEstimate>(
    token ? `/public/estimates/${token}` : null,
  );

  return (
    <>
      {error && (
        <PublicShell
          workspace={{
            display_name: "Vehicle Service Manager",
            primary_color: "#0f766e",
            accent_color: "#f59e0b",
          }}
        >
          <ErrorState
            message="This link is invalid or has expired. Ask the workshop to send a new one."
            retry={() => mutate()}
          />
        </PublicShell>
      )}
      {isLoading && !data && <LoadingBlock label="Loading your estimate" />}
      {data && <EstimateBody data={data} token={token} mutate={mutate} />}
    </>
  );
}

function EstimateBody({
  data,
  token,
  mutate,
}: {
  data: PublicEstimate;
  token: string;
  mutate: () => void;
}) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState<"approve" | "decline" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function respond(decision: "approve" | "decline") {
    setBusy(decision);
    setActionError(null);
    try {
      await api(`/public/estimates/${token}/respond`, {
        body: { decision, name: name.trim() || null },
      });
      mutate();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not submit your answer");
    } finally {
      setBusy(null);
    }
  }

  const answered = data.status === "approved" || data.status === "declined";

  return (
    <PublicShell workspace={data.workspace}>
      <p className="text-sm text-[var(--muted-foreground)]">Estimate</p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">{data.number}</h1>
      <p className="mt-1 text-sm text-[var(--muted-foreground)]">
        {data.vehicle.plate_number ?? ""}
        {data.vehicle.plate_number && (data.vehicle.make || data.vehicle.model) ? " · " : ""}
        {[data.vehicle.year, data.vehicle.make, data.vehicle.model].filter(Boolean).join(" ")}
      </p>

      {answered && (
        <Card className="mt-6">
          <CardContent className="pt-6">
            {data.status === "approved" ? (
              <>
                <p className="font-medium text-[var(--success)]">Approved — thank you!</p>
                <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                  {data.converted_order_number
                    ? `We created service order ${data.converted_order_number} and will be in touch to schedule the work.`
                    : "We will be in touch to schedule the work."}
                </p>
              </>
            ) : (
              <>
                <p className="font-medium">Estimate declined</p>
                <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                  Thanks for letting us know. Contact the workshop if you would like to discuss
                  alternatives.
                </p>
              </>
            )}
          </CardContent>
        </Card>
      )}

      <Card className="mt-6">
        <CardContent className="pt-6">
          <p className="whitespace-pre-wrap text-sm">{data.description}</p>
          <div className="mt-5 overflow-hidden rounded-lg border border-[var(--border)]">
            <table className="w-full text-sm">
              <caption className="sr-only">Estimate line items</caption>
              <thead className="bg-[var(--muted)] text-left">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Description
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    Qty
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    Price
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item, index) => (
                  <tr key={index} className="border-t border-[var(--border)]">
                    <td className="px-3 py-2">{item.description}</td>
                    <td className="px-3 py-2 text-right">{item.quantity}</td>
                    <td className="px-3 py-2 text-right">
                      {money(item.total, data.workspace.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <dl className="mt-4 space-y-1 text-sm">
            <div className="flex justify-between">
              <dt className="text-[var(--muted-foreground)]">Labour</dt>
              <dd>{money(data.totals.labor, data.workspace.currency)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[var(--muted-foreground)]">Parts</dt>
              <dd>{money(data.totals.parts, data.workspace.currency)}</dd>
            </div>
            <div className="flex justify-between border-t border-[var(--border)] pt-2 text-base font-semibold">
              <dt>Total</dt>
              <dd>{money(data.totals.total, data.workspace.currency)}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {!answered && data.status === "sent" && (
        <Card className="mt-4">
          <CardContent className="space-y-4 pt-6">
            <div>
              <h2 className="font-medium">Approve this estimate</h2>
              <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                Approving authorises the work above at the quoted total.
              </p>
            </div>
            <div>
              <label htmlFor="responder-name" className="text-sm font-medium">
                Your name (optional)
              </label>
              <input
                id="responder-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={120}
                className="mt-1 h-9 w-full rounded-lg border border-[var(--input)] bg-[var(--card)] px-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)] [@media(pointer:coarse)]:h-11"
                autoComplete="name"
              />
            </div>
            {actionError && (
              <p role="alert" className="text-sm text-[var(--destructive)]">
                {actionError}
              </p>
            )}
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button onClick={() => respond("approve")} loading={busy === "approve"} disabled={Boolean(busy)}>
                Approve {money(data.totals.total, data.workspace.currency)}
              </Button>
              <Button
                variant="secondary"
                onClick={() => respond("decline")}
                loading={busy === "decline"}
                disabled={Boolean(busy)}
              >
                Decline
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {!answered && data.status !== "sent" && (
        <p className="mt-4 text-sm text-[var(--muted-foreground)]">
          This estimate is not ready for a decision yet.
        </p>
      )}

      <p className="mt-6 text-xs text-[var(--muted-foreground)]">
        Sent {formatDateTime(data.sent_at)}.{" "}
        {data.workspace.support_email && (
          <>
            Questions?{" "}
            <a
              className="underline underline-offset-2"
              href={`mailto:${data.workspace.support_email}`}
            >
              Contact {data.workspace.display_name}
            </a>
            .
          </>
        )}
      </p>
    </PublicShell>
  );
}

export function PublicReviewView() {
  const params = useParams<{ token: string }>();
  return <PublicReviewInner token={params.token ?? ""} />;
}

const RATING_LABELS: Record<number, string> = {
  1: "Poor",
  2: "Fair",
  3: "Good",
  4: "Very good",
  5: "Excellent",
};

function PublicReviewInner({ token }: { token: string }) {
  const { data, error, isLoading, mutate } = useApi<PublicReview>(
    token ? `/public/reviews/${token}` : null,
  );
  const [rating, setRating] = useState(0);
  const [hover, setHover] = useState(0);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  if (error) {
    return (
      <PublicShell workspace={{
        display_name: "Vehicle Service Manager",
        primary_color: "#0f766e",
        accent_color: "#f59e0b",
      }}>
        <ErrorState
          message="This review link is invalid or has expired."
          retry={() => mutate()}
        />
      </PublicShell>
    );
  }
  if (isLoading && !data) return <LoadingBlock label="Loading" />;
  if (!data) return null;

  const submitted = data.status === "submitted";
  const shown = hover || rating;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (rating < 1) {
      setSubmitError("Choose a star rating first.");
      return;
    }
    setBusy(true);
    setSubmitError(null);
    try {
      await api(`/public/reviews/${token}`, {
        body: { rating, comment: comment.trim() || null },
      });
      mutate();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Could not submit your review");
    } finally {
      setBusy(false);
    }
  }

  return (
    <PublicShell workspace={data.workspace}>
      <p className="text-sm text-[var(--muted-foreground)]">Service order {data.order_number}</p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">
        {submitted ? "Thank you for your feedback" : `How did we do?`}
      </h1>

      {submitted ? (
        <Card className="mt-6">
          <CardContent className="space-y-3 pt-6">
            <div className="flex items-center gap-1" aria-label={`${data.rating ?? 0} out of 5 stars`}>
              {[1, 2, 3, 4, 5].map((value) => (
                <Star
                  key={value}
                  className={
                    (data.rating ?? 0) >= value
                      ? "h-6 w-6 fill-[var(--brand-accent)] text-[var(--brand-accent)]"
                      : "h-6 w-6 text-[var(--muted-foreground)]"
                  }
                  aria-hidden="true"
                />
              ))}
            </div>
            {data.comment && <p className="text-sm">{data.comment}</p>}
            <p className="text-sm text-[var(--muted-foreground)]">
              We appreciate you taking the time to tell us about your visit.
            </p>
            {data.review_url && (
              <a
                href={data.review_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-9 items-center rounded-lg bg-[var(--brand-primary)] px-4 text-sm font-medium text-[var(--brand-primary-fg)]"
              >
                Share your review publicly
              </a>
            )}
          </CardContent>
        </Card>
      ) : (
        <form onSubmit={submit} className="mt-6 space-y-5">
          <Card>
            <CardContent className="space-y-4 pt-6">
              <fieldset>
                <legend className="text-sm font-medium">Your rating</legend>
                <div className="mt-2 flex items-center gap-1">
                  {[1, 2, 3, 4, 5].map((value) => (
                    <button
                      key={value}
                      type="button"
                      aria-label={`${value} star${value === 1 ? "" : "s"} — ${RATING_LABELS[value]}`}
                      aria-pressed={rating === value}
                      onMouseEnter={() => setHover(value)}
                      onMouseLeave={() => setHover(0)}
                      onFocus={() => setHover(value)}
                      onBlur={() => setHover(0)}
                      onClick={() => setRating(value)}
                      className="rounded-md p-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]"
                    >
                      <Star
                        className={
                          shown >= value
                            ? "h-8 w-8 fill-[var(--brand-accent)] text-[var(--brand-accent)]"
                            : "h-8 w-8 text-[var(--muted-foreground)]"
                        }
                        aria-hidden="true"
                      />
                    </button>
                  ))}
                  <span className="ml-2 text-sm text-[var(--muted-foreground)]" aria-live="polite">
                    {shown ? RATING_LABELS[shown] : ""}
                  </span>
                </div>
              </fieldset>
              <Field label="Anything you would like to add?" htmlFor="r-comment">
                <Textarea
                  id="r-comment"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="Optional — what went well, or what we could improve."
                />
              </Field>
              {submitError && (
                <p role="alert" className="text-sm text-[var(--destructive)]">
                  {submitError}
                </p>
              )}
              <Button type="submit" loading={busy}>
                Send review
              </Button>
            </CardContent>
          </Card>
        </form>
      )}
    </PublicShell>
  );
}
