"use client";

import * as DropdownPrimitive from "@radix-ui/react-dropdown-menu";

import { cn } from "@/lib/cn";

export const DropdownMenu = DropdownPrimitive.Root;
export const DropdownMenuTrigger = DropdownPrimitive.Trigger;

export function DropdownMenuContent({
  children,
  align = "end",
  className,
}: {
  children: React.ReactNode;
  align?: "start" | "center" | "end";
  className?: string;
}) {
  return (
    <DropdownPrimitive.Portal>
      <DropdownPrimitive.Content
        align={align}
        sideOffset={6}
        className={cn(
          "z-50 min-w-44 overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--card)] p-1 shadow-lg",
          className,
        )}
      >
        {children}
      </DropdownPrimitive.Content>
    </DropdownPrimitive.Portal>
  );
}

export function DropdownMenuItem({
  className,
  danger,
  ...props
}: DropdownPrimitive.DropdownMenuItemProps & { danger?: boolean }) {
  return (
    <DropdownPrimitive.Item
      className={cn(
        "flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none transition-colors",
        danger
          ? "text-[var(--destructive)] focus:bg-[color-mix(in_oklab,var(--destructive)_10%,transparent)]"
          : "text-[var(--foreground)] focus:bg-[var(--muted)]",
        "data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export function DropdownMenuLabel({ children }: { children: React.ReactNode }) {
  return (
    <DropdownPrimitive.Label className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
      {children}
    </DropdownPrimitive.Label>
  );
}

export function DropdownMenuSeparator() {
  return <DropdownPrimitive.Separator className="my-1 h-px bg-[var(--border)]" />;
}
