import { describe, expect, it } from "vitest";
import type { Column } from "../components/ui/Table";
import { withoutEmptyColumns } from "./columns";

type Row = { title: string; board?: string; code?: string };

const columns: Column<Row>[] = [
  { key: "title", header: "t", render: (row) => row.title },
  { key: "board", header: "b", render: (row) => row.board ?? "" },
  { key: "code", header: "c", render: (row) => row.code ?? "" },
];
const filled = { board: (row: Row) => Boolean(row.board), code: (row: Row) => Boolean(row.code) };

describe("withoutEmptyColumns", () => {
  it("hides columns empty in every row and keeps unchecked ones", () => {
    const rows: Row[] = [{ title: "card one" }, { title: "card two", code: "X1" }];
    expect(withoutEmptyColumns(columns, rows, filled).map((c) => c.key)).toEqual(["title", "code"]);
  });

  it("keeps a column if any row has a value", () => {
    const rows: Row[] = [{ title: "a", board: "board one" }, { title: "b" }];
    expect(withoutEmptyColumns(columns, rows, filled).map((c) => c.key)).toEqual(["title", "board"]);
  });

  it("keeps everything when there are no rows", () => {
    expect(withoutEmptyColumns(columns, [], filled)).toHaveLength(3);
  });
});
