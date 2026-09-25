/** Screenshots in frontend/public/how-it-works/: 1600×1000 WebP from a scratch backend (no emails, fixtures only,
 * throwaway DB) after running samples 01, 03, 04 and 06. Retake them when those pages change. */
export const SHOTS = {
  process: { file: "process-06-fraud.webp", path: "/process", width: 1600, height: 1000 },
  review: { file: "review-04-send-to-vendor.webp", path: "/review", width: 1600, height: 1000 },
  respond: { file: "respond-04.webp", path: "/respond/…", width: 1600, height: 1000 },
  createPo: { file: "create-po.webp", path: "/pos?create", width: 1600, height: 1000 },
  dashboard: { file: "dashboard.webp", path: "/dashboard", width: 1600, height: 1000 },
  tests: { file: "tests.webp", path: "/tests", width: 1600, height: 1000 },
} as const
