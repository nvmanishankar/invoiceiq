import { Fragment, type ReactNode } from "react"

import { cn } from "@/lib/utils"

export type Column<T> = { key: string; head: ReactNode; cell: (row: T) => ReactNode; align?: "left" | "right"; className?: (row: T) => string | undefined }

/** Plain finance table: no zebra, 1px dividers, hover rows, money right-aligned. */
export function DataTable<T>({ columns, rows, rowKey, rowClassName, onRowClick, caption, renderExpanded }: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T, i: number) => string
  rowClassName?: (row: T) => string | undefined
  /** Mouse shortcut only: put a real button in a cell for keyboard users. */
  onRowClick?: (row: T) => void
  caption?: string
  /** Detail shown in a full-width row under a row; return null to keep it closed. */
  renderExpanded?: (row: T) => ReactNode | null
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[14px]">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="border-b border-line">
            {columns.map((c) => (
              <th key={c.key} scope="col" className={cn("label px-3 py-2 font-normal", c.align === "right" ? "text-right" : "text-left")}>
                {c.head}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const detail = renderExpanded?.(r) ?? null
            return (
              <Fragment key={rowKey(r, i)}>
                <tr onClick={onRowClick && (() => onRowClick(r))}
                  className={cn("border-b border-line hover:bg-hover/70", !detail && "last:border-b-0", onRowClick && "cursor-pointer", rowClassName?.(r))}>
                  {columns.map((c) => (
                    <td key={c.key} className={cn("px-3 py-2.5 align-top text-ink", c.align === "right" && "num text-right", c.className?.(r))}>
                      {c.cell(r)}
                    </td>
                  ))}
                </tr>
                {detail && (
                  <tr className="border-b border-line bg-hover/40 last:border-b-0">
                    <td colSpan={columns.length} className="px-3 pt-1 pb-5">{detail}</td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
