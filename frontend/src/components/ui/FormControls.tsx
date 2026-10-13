import {
  useId,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { createContext, useContext } from "react";

const FieldIdContext = createContext<string | undefined>(undefined);

function cx(...parts: Array<string | false | undefined>) {
  return parts.filter(Boolean).join(" ");
}

type Grow = { grow?: boolean; className?: string };

function persianValidity<T extends HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(
  event: { currentTarget: T },
) {
  const el = event.currentTarget;
  el.setCustomValidity(el.validity.valueMissing ? "این فیلد را پر کنید" : "");
}

export function Input({
  grow,
  className = "",
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & Grow) {
  const fieldId = useContext(FieldIdContext);
  return (
    <input
      className={cx("control", grow && "control--grow", className)}
      {...rest}
      id={rest.id ?? fieldId}
      onInvalid={(event) => {
        persianValidity(event);
        rest.onInvalid?.(event);
      }}
      onInput={(event) => {
        event.currentTarget.setCustomValidity("");
        rest.onInput?.(event);
      }}
    />
  );
}

export function TextArea({
  grow,
  className = "",
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement> & Grow) {
  const fieldId = useContext(FieldIdContext);
  return (
    <textarea
      className={cx("control", grow && "control--grow", className)}
      {...rest}
      id={rest.id ?? fieldId}
      onInvalid={(event) => {
        persianValidity(event);
        rest.onInvalid?.(event);
      }}
      onInput={(event) => {
        event.currentTarget.setCustomValidity("");
        rest.onInput?.(event);
      }}
    />
  );
}

export function Select({
  grow,
  className = "",
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & Grow) {
  const fieldId = useContext(FieldIdContext);
  return (
    <select
      className={cx("control", grow && "control--grow", className)}
      {...rest}
      id={rest.id ?? fieldId}
      onInvalid={(event) => {
        persianValidity(event);
        rest.onInvalid?.(event);
      }}
      onChange={(event) => {
        event.currentTarget.setCustomValidity("");
        rest.onChange?.(event);
      }}
    >
      {children}
    </select>
  );
}

export function Checkbox({
  label,
  className = "",
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode }) {
  return (
    <label className={cx("check-row", className)}>
      <input {...rest} type="checkbox" />
      <span>{label}</span>
    </label>
  );
}

export function Field({
  label,
  children,
  className = "",
}: {
  label?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={cx("field", className)}>
      {label ? <label htmlFor={id}>{label}</label> : null}
      <FieldIdContext.Provider value={id}>{children}</FieldIdContext.Provider>
    </div>
  );
}

export function Toolbar({
  children,
  className = "",
  as: Tag = "div",
  ...rest
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "form";
} & HTMLAttributes<HTMLElement>) {
  return (
    <Tag className={cx("toolbar", className)} {...(rest as HTMLAttributes<HTMLElement>)}>
      {children}
    </Tag>
  );
}
