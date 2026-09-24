"use client";

import { useEffect, useId, useRef, useState } from "react";

type Suggestion = {
  name: string;
  detail: string;
  address: string;
  placeId?: string | null;
};

export function AddressField({
  value,
  onChange,
  onPlaceId,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  onPlaceId: (placeId: string | null) => void;
  disabled?: boolean;
}) {
  const listId = useId();
  const box = useRef<HTMLDivElement>(null);
  const picked = useRef(false);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Suggestion[]>([]);
  const [hi, setHi] = useState(0);

  useEffect(() => {
    const q = value.trim();
    if (picked.current || q.length < 2) {
      setItems([]);
      setOpen(false);
      return;
    }
    const ctrl = new AbortController();
    const t = window.setTimeout(async () => {
      try {
        const res = await fetch(`/api/places?q=${encodeURIComponent(q)}`, {
          cache: "no-store",
          signal: ctrl.signal,
        });
        if (!res.ok) return;
        const data = (await res.json()) as { suggestions?: Suggestion[] };
        const next = data.suggestions ?? [];
        setItems(next);
        setHi(0);
        setOpen(next.length > 0);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
      }
    }, 220);
    return () => {
      ctrl.abort();
      window.clearTimeout(t);
    };
  }, [value]);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  function pick(item: Suggestion) {
    picked.current = true;
    onChange(item.address);
    onPlaceId(item.placeId ?? null);
    setItems([]);
    setOpen(false);
  }

  return (
    <div ref={box} className="relative">
      <input
        required
        autoComplete="off"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        disabled={disabled}
        value={value}
        onChange={(e) => {
          picked.current = false;
          onChange(e.target.value);
          onPlaceId(null);
        }}
        onFocus={() => {
          if (!picked.current && items.length) setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            if (open && items.length) {
              e.preventDefault();
              pick(items[hi] ?? items[0]);
            }
            return;
          }
          if (!open || !items.length) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setHi((i) => (i + 1) % items.length);
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setHi((i) => (i - 1 + items.length) % items.length);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
        placeholder="Grace Darling"
        className="w-full border-b border-ink bg-transparent py-2 text-base outline-none"
      />
      {open && items.length ? (
        <ul
          id={listId}
          role="listbox"
          className="absolute left-0 right-0 top-full z-20 mt-1 border border-ink bg-paper"
        >
          {items.map((item, i) => (
            <li key={item.placeId || item.address}>
              <button
                type="button"
                role="option"
                aria-selected={i === hi}
                className={`block w-full px-3 py-2 text-left ${i === hi ? "bg-card" : ""}`}
                onMouseEnter={() => setHi(i)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(item)}
              >
                <span className="block text-sm text-ink">{item.name}</span>
                {item.detail ? <span className="block text-xs text-muted">{item.detail}</span> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
