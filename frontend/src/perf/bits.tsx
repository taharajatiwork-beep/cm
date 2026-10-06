import { useRef, type ReactNode } from "react";
import { Button, Icon } from "../components/ui";

export function FilePick({
  accept,
  label,
  hint,
  busy,
  onFile,
}: {
  accept: string;
  label: ReactNode;
  hint?: ReactNode;
  busy?: boolean;
  onFile: (file: File) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" className="drop-zone" disabled={busy} onClick={() => ref.current?.click()}>
        <Icon name="upload" size={22} />
        <strong>{label}</strong>
        {hint ? <span dir={typeof hint === "string" && hint.trim().startsWith(".") ? "ltr" : undefined}>{hint}</span> : null}
      </button>
      <input
        ref={ref}
        hidden
        type="file"
        accept={accept}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          event.target.value = "";
        }}
      />
    </>
  );
}

export function FileButton({
  accept,
  label,
  onFile,
}: {
  accept: string;
  label: ReactNode;
  onFile: (file: File) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <Button type="button" variant="secondary" onClick={() => ref.current?.click()}>
        {label}
      </Button>
      <input
        ref={ref}
        hidden
        type="file"
        accept={accept}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          event.target.value = "";
        }}
      />
    </>
  );
}
