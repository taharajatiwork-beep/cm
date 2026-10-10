import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";

/**
 * "danger" = solid red, only for the final confirm of a destructive action.
 * "danger-quiet" = red text, no fill: row-level delete buttons next to normal actions.
 */
export type ButtonVariant = "primary" | "secondary" | "danger" | "danger-quiet" | "ghost";

type Common = {
  variant?: ButtonVariant;
  children: ReactNode;
  className?: string;
};

type ButtonAsButton = Common &
  ButtonHTMLAttributes<HTMLButtonElement> & {
    to?: undefined;
  };

type ButtonAsLink = Common &
  Omit<LinkProps, "className"> & {
    to: string;
    disabled?: boolean;
  };

export type ButtonProps = ButtonAsButton | ButtonAsLink;

function variantClass(variant: ButtonVariant): string {
  if (variant === "primary") return "btn";
  if (variant === "secondary") return "btn secondary";
  if (variant === "danger") return "btn btn-danger";
  if (variant === "danger-quiet") return "btn btn-danger-quiet";
  return "btn btn-ghost";
}

export function Button(props: ButtonProps) {
  const { variant = "primary", children, className = "" } = props;
  const cls = `${variantClass(variant)} ${className}`.trim();

  if ("to" in props && props.to) {
    const { to, disabled, variant: _v, children: _c, className: _cl, ...rest } = props;
    if (disabled) {
      return (
        <span className={`${cls} is-disabled`} aria-disabled>
          {children}
        </span>
      );
    }
    return (
      <Link to={to} className={cls} {...rest}>
        {children}
      </Link>
    );
  }

  const {
    type = "button",
    variant: _v,
    children: _c,
    className: _cl,
    ...rest
  } = props as ButtonAsButton;
  return (
    <button type={type} className={cls} {...rest}>
      {children}
    </button>
  );
}
