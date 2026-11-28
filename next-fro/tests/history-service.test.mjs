import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

const source = fs.readFileSync(
  new URL("../services/history.service.ts", import.meta.url),
  "utf8",
);
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;

test("learning history requests keep checkins, review records and plan filter separate", async () => {
  const paths = [];
  const service = { exports: {} };
  new Function("require", "module", "exports", output)(
    () => ({
      apiFetch: async (path) => {
        paths.push(path);
        return { data: { items: [], total: 0, page: 2, page_size: 20 } };
      },
    }),
    service,
    service.exports,
  );

  await service.exports.getCheckinSummary();
  await service.exports.getCheckins(30, 2, 7);
  await service.exports.getCheckins("all", 1, null);
  await service.exports.getReviewHistory(2);
  assert.deepEqual(paths, [
    "/history/checkin-summary",
    "/history/checkins?days=30&page=2&page_size=20&plan_id=7",
    "/history/checkins?days=all&page=1&page_size=20",
    "/history/reviews?page=2&page_size=20",
  ]);
});
