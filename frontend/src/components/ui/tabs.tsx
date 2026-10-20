"use client";

import { useRef } from "react";

import { cn } from "@/lib/cn";

/* Hand-rolled accessible tabs: roving tabindex, arrow/Home/End navigation. */

export interface TabDef {
  id: string;
  label: string;
}

export function TabList({
  tabs,
  value,
  onChange,
  label,
  className,
}: {
  tabs: TabDef[];
  value: string;
  onChange: (id: string) => void;
  label: string;
  className?: string;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(event: React.KeyboardEvent, index: number) {
    let next = -1;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    if (next >= 0) {
      event.preventDefault();
      const target = tabs[next];
      onChange(target.id);
      refs.current[target.id]?.focus();
    }
  }

  return (
    <div
      role="tablist"
      aria-label={label}
      className={cn(
        "flex gap-4 overflow-x-auto border-b border-[var(--border)] [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
        className,
      )}
    >
      {tabs.map((tab, index) => {
        const selected = tab.id === value;
        return (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[tab.id] = el;
            }}
            role="tab"
            id={`tab-${tab.id}`}
            type="button"
            aria-selected={selected}
            aria-controls={`panel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(e) => onKeyDown(e, index)}
            className={cn(
              "-mb-px min-h-9 whitespace-nowrap border-b-2 px-1 text-sm font-medium transition-colors [@media(pointer:coarse)]:min-h-11",
              selected
                ? "border-[var(--brand-primary)] text-[var(--foreground)]"
                : "border-transparent text-[var(--muted-foreground)] hover:border-[var(--border)] hover:text-[var(--foreground)]",
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({
  id,
  value,
  children,
  className,
}: {
  id: string;
  value: string;
  children: React.ReactNode;
  className?: string;
}) {
  if (id !== value) return null;
  return (
    <div
      role="tabpanel"
      id={`panel-${id}`}
      aria-labelledby={`tab-${id}`}
      tabIndex={0}
      className={cn("focus-visible:outline-2 focus-visible:outline-offset-4", className)}
    >
      {children}
    </div>
  );
}
