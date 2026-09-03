"use client";

import { useEffect, useRef, useState, type ReactElement } from "react";

export type AttachKind = "camera" | "image" | "file";

type Props = {
  disabled?: boolean;
  onPick: (kind: AttachKind, file: File) => void;
};

const ACTIONS: Array<{
  id: AttachKind;
  label: string;
  accept: string;
  capture?: boolean;
}> = [
  {
    id: "camera",
    label: "Camera",
    accept: "image/*",
    capture: true,
  },
  {
    id: "image",
    label: "Image",
    accept: "image/*",
  },
  {
    id: "file",
    label: "File",
    accept: ".pdf,.csv,.txt,.xlsx,.xls,.doc,.docx,image/*",
  },
];

function CameraIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M9.4 5.5h5.2l1.1 1.5H19a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2h3.3L9.4 5.5ZM12 17.2A3.7 3.7 0 1 0 12 9.8a3.7 3.7 0 0 0 0 7.4Zm0-1.8a1.9 1.9 0 1 1 0-3.8 1.9 1.9 0 0 1 0 3.8Z"
      />
    </svg>
  );
}

function ImageIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Zm0 2v8.2l3.4-3.4a1 1 0 0 1 1.4 0L14 15l2.1-2.1a1 1 0 0 1 1.4 0L19 14.4V6H5Zm3.2 2.2a1.4 1.4 0 1 1 0 2.8 1.4 1.4 0 0 1 0-2.8Z"
      />
    </svg>
  );
}

function FileIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M14 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-6Zm0 1.5L17.5 8H14V3.5ZM8 12h8v1.5H8V12Zm0 3.5h8V17H8v-1.5Zm0-7h4V10H8V8.5Z"
      />
    </svg>
  );
}

const ICONS: Record<AttachKind, () => ReactElement> = {
  camera: CameraIcon,
  image: ImageIcon,
  file: FileIcon,
};

export default function ChatAttachFab({ disabled, onPick }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRefs = useRef<Record<AttachKind, HTMLInputElement | null>>({
    camera: null,
    image: null,
    file: null,
  });

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const onClick = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onClick);
    };
  }, [open]);

  const trigger = (kind: AttachKind) => {
    setOpen(false);
    inputRefs.current[kind]?.click();
  };

  return (
    <div className={`chat-fab${open ? " is-open" : ""}`} ref={rootRef}>
      {ACTIONS.map((action) => (
        <input
          key={action.id}
          ref={(node) => {
            inputRefs.current[action.id] = node;
          }}
          type="file"
          accept={action.accept}
          capture={action.capture ? "environment" : undefined}
          className="chat-fab-input"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) onPick(action.id, file);
          }}
        />
      ))}

      <div className="chat-fab-stack" aria-hidden={!open}>
        {[...ACTIONS].reverse().map((action, index) => {
          const Icon = ICONS[action.id];
          return (
            <div
              key={action.id}
              className="chat-fab-item"
              style={{ transitionDelay: open ? `${index * 40}ms` : "0ms" }}
            >
              <button
                type="button"
                className="chat-fab-action"
                disabled={disabled || !open}
                tabIndex={open ? 0 : -1}
                onClick={() => trigger(action.id)}
                aria-label={action.label}
              >
                <Icon />
              </button>
              <span className="chat-fab-label">{action.label}</span>
            </div>
          );
        })}
      </div>

      <button
        type="button"
        className={`chat-fab-toggle${open ? " is-on" : ""}`}
        disabled={disabled}
        aria-expanded={open}
        aria-label={open ? "Close attach menu" : "Attach"}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="chat-fab-plus" aria-hidden="true" />
      </button>
    </div>
  );
}
