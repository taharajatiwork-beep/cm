import type { ReactNode, TableHTMLAttributes } from "react";

export type Column<T> = {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  className?: string;
};

type TableProps<T> = {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  empty?: ReactNode;
  className?: string;
  onRowClick?: (row: T) => void;
  isRowActive?: (row: T) => boolean;
} & Omit<TableHTMLAttributes<HTMLTableElement>, "children">;

export function Table<T>({
  columns,
  rows,
  rowKey,
  empty,
  className = "",
  onRowClick,
  isRowActive,
  ...rest
}: TableProps<T>) {
  if (rows.length === 0 && empty) {
    return <>{empty}</>;
  }

  return (
    <div className="ui-table-wrap">
      <table className={`table ui-table ${className}`.trim()} {...rest}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={c.className}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className={[onRowClick ? "is-clickable" : "", isRowActive?.(row) ? "is-active" : ""]
                .filter(Boolean)
                .join(" ") || undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((c) => (
                <td key={c.key} className={c.className}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
