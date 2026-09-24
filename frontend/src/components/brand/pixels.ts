/** Turn an ASCII pixel map into [x, y] cells for every non-"." character. */
export function cells(rows: string[], ch?: string): [number, number][] {
  const out: [number, number][] = []
  rows.forEach((row, y) =>
    [...row].forEach((c, x) => {
      if (c !== "." && (ch === undefined || c === ch)) out.push([x, y])
    }),
  )
  return out
}
