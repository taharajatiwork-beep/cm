import type {
  HTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

function cx(...parts: Array<string | false | undefined>) {
  return parts.filter(Boolean).join(" ");
}

type Grow = { grow?: boolean; className?: string };

export function Input({
  grow,
  className = "",
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & Grow) {
  return <input className={cx("control", grow && "control--grow", className)} {...rest} />;
}

export function TextArea({
  grow,
  className = "",
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement> & Grow) {
  return <textarea className={cx("control", grow && "control--grow", className)} {...rest} />;
}

export function Select({
  grow,
  className = "",
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & Grow) {
  return (
    <select className={cx("control", grow && "control--grow", className)} {...rest}>
      {children}
    </select>
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
  return (
    <div className={cx("field", className)}>
      {label ? <label>{label}</label> : null}
      {children}
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
