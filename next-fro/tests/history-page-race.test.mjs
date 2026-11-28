import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";

const require = createRequire(import.meta.url);
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const source = fs.readFileSync(
  new URL("../app/(workspace)/history/page.tsx", import.meta.url),
  "utf8",
);
const output = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    jsx: ts.JsxEmit.ReactJSX,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;

function renderWithResult(tab, result) {
  const states = [null, tab, 7, 1, null, result, "", 0];
  let index = 0;
  const copy = {
    navigation: { history: "学习记录" },
    history: {
      subtitle: "记录",
      refresh: "刷新",
      checkinsTab: "任务打卡",
      focusTab: "专注自习",
      reviewsTab: "笔记复习",
      practiceTab: "智能练习",
      loading: "正在读取学习记录…",
      reviewCount: (count) => `共 ${count} 次复习`,
      noteDeleted: "笔记已删除",
      emptyRecords: "暂无记录",
      dataScope: "分开统计",
    },
  };
  const dependencies = {
    react: {
      Suspense: React.Suspense,
      useState: () => [states[index++], () => {}],
      useEffect: () => {},
      useMemo: (calculate) => calculate(),
    },
    "react/jsx-runtime": require("react/jsx-runtime"),
    "next/navigation": { useSearchParams: () => ({ get: () => null }) },
    "next/link": {
      default: ({ children }) => React.createElement("span", null, children),
    },
    "lucide-react": { Check: () => null, ChevronDown: () => null },
    "@/messages": { messages: copy },
    "@/messages/zh-CN/ai-practice": { aiPractice: {} },
  };
  const compiled = { exports: {} };
  new Function("require", "module", "exports", output)(
    (name) => dependencies[name] ?? {},
    compiled,
    compiled.exports,
  );
  const page = compiled.exports.default();
  return renderToStaticMarkup(page.props.children.type());
}

test("review tab never renders stale focus items while its own request is pending", () => {
  const focusResult = {
    key: "focus|7||1|0",
    data: { items: [{ id: 1, focus_date: "2026-11-28" }], total: 1 },
    error: "",
  };
  const markup = renderWithResult("reviews", focusResult);
  assert.match(markup, /正在读取学习记录/);
  assert.doesNotMatch(markup, /2026-11-28/);
});

test("review tab renders a matching review response", () => {
  const reviewResult = {
    key: "reviews|7||1|0",
    data: {
      items: [
        {
          id: 2,
          note_id: 5,
          note_title: "数学笔记",
          note_deleted_at: null,
          plan_id: null,
          reviewed_at: "2026-11-28T10:00:00",
        },
      ],
      total: 1,
    },
    error: "",
  };
  const markup = renderWithResult("reviews", reviewResult);
  assert.match(markup, /数学笔记/);
  assert.match(markup, /2026-11-28 10:00/);
});
