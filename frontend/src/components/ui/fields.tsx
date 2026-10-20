import { forwardRef } from "react";
import { ChevronDown, CircleAlert } from "lucide-react";

import { cn } from "@/lib/cn";

/* Accessible form primitives. Field wires the label and error/hint text;
 * inputs set aria-invalid so error styling and SR state line up. */

export function Field({
  label,
  htmlFor,
  hint,
  error,
  required,
  children,
  className,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string | null;
  required?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={htmlFor} className="block text-xs font-medium text-[var(--foreground)]">
        {label}
        {required && (
          <span className="ml-1 text-[var(--destructive)]" aria-hidden="true">
            *
          </span>
        )}
      </label>
      {children}
      {hint && !error && (
        <p id={`${htmlFor}-hint`} className="text-xs text-[var(--muted-foreground)]">
          {hint}
        </p>
      )}
      {error && (
        <p
          id={`${htmlFor}-error`}
          className="flex items-start gap-1.5 text-xs font-medium text-[var(--destructive)]"
        >
          <CircleAlert className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {error}
        </p>
      )}
    </div>
  );
}

const controlClasses =
  "h-9 w-full rounded-lg border border-[var(--input)] bg-[var(--card)] px-3 text-base text-[var(--foreground)] placeholder:text-[color-mix(in_oklab,var(--muted-foreground)_85%,transparent)] focus:border-[var(--brand-primary)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)] disabled:opacity-50 aria-invalid:border-[var(--destructive)] sm:text-sm [@media(pointer:coarse)]:h-11";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input ref={ref} className={cn(controlClasses, className)} {...props} />
  ),
);
Input.displayName = "Input";

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(controlClasses, "h-auto min-h-20 py-2", className)}
    {...props}
  />
));
Textarea.displayName = "Textarea";

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  children: React.ReactNode;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, children, ...props }, ref) => (
    <span className="relative block">
      <select
        ref={ref}
        className={cn(controlClasses, "appearance-none pr-9", className)}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--muted-foreground)]"
        aria-hidden="true"
      />
    </span>
  ),
);
Select.displayName = "Select";
