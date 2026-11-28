import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

const source = fs.readFileSync(new URL("../components/auth/UsersProfile.tsx", import.meta.url), "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText;

function setup({ revokeOtherSessions = async () => {}, logoutAllSessions = async () => {} } = {}) {
  const state = [];
  let cursor = 0;
  const authEvents = [];
  const messages = { profile: { logoutOthers: "退出其他设备", logoutAll: "退出全部设备", logoutCurrent: "退出当前设备", confirmPassword: "确认密码" }, auth: {}, common: { cancel: "取消" }, navigation: {} };
  const dependencies = {
    react: {
      useState(initial) {
        const index = cursor++;
        if (!(index in state)) state[index] = initial;
        return [state[index], (next) => { state[index] = typeof next === "function" ? next(state[index]) : next; }];
      },
      useEffect() {},
    },
    "react/jsx-runtime": { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    "next/navigation": { useRouter: () => ({ replace() {} }) },
    "next/image": () => null,
    "@radix-ui/react-alert-dialog": { Root: "alert-root", Portal: "alert-portal", Overlay: "alert-overlay", Content: "alert-content", Title: "alert-title", Description: "alert-description", Cancel: "alert-cancel" },
    "lucide-react": Object.fromEntries(["Camera", "ChevronDown", "ChevronRight", "KeyRound", "Mail", "MonitorSmartphone", "Pencil", "ShieldCheck", "UserRound", "X"].map((name) => [name, () => null])),
    "@/components/ui/dialog": Object.fromEntries(["Dialog", "DialogClose", "DialogContent", "DialogDescription", "DialogHeader", "DialogTitle"].map((name) => [name, name])),
    "@/contexts/AuthContext": { useAuth: () => ({ status: "authenticated", user: { username: "student" }, clear: () => authEvents.push("clear") }) },
    "@/services/auth.service": { revokeOtherSessions, logoutAllSessions, listSessions: async () => ({ data: { items: [], total: 0 } }) },
    "@/lib/api/client": { API_BASE_URL: "" },
    "@/messages": { messages },
    "@/components/common/LandscapeScene": { LandscapeScene: () => null },
    "@/components/ui/SaveSuccessDialog": { SaveSuccessDialog: () => null },
    "@/components/css/Profile.css": {},
    "@/components/css/ProfileAuth.css": {},
  };
  const compiledModule = { exports: {} };
  new Function("require", "module", "exports", output)((name) => {
    if (!(name in dependencies)) throw new Error(`Unexpected import: ${name}`);
    return dependencies[name];
  }, compiledModule, compiledModule.exports);
  return { render: () => { cursor = 0; return compiledModule.exports.default(); }, authEvents };
}

function find(node, predicate) {
  if (Array.isArray(node)) return node.map((child) => find(child, predicate)).find(Boolean);
  if (!node || typeof node !== "object") return undefined;
  if (predicate(node)) return node;
  return find(node.props?.children, predicate);
}

const passwordInput = (tree) => find(tree, (node) => node.type === "input" && node.props.id === "profile-session-confirm-password");
const otherDevicesButton = (tree) => find(tree, (node) => node.type === "button" && node.props.children === "退出其他设备");
const dialogRoot = (tree) => find(tree, (node) => node.type === "alert-root");
const dialogForm = (tree) => find(tree, (node) => node.type === "form" && find(node, (child) => child.type === "input" && child.props.id === "profile-session-confirm-password"));

test("device confirmation password is empty on open, after failure, and after reopening", async () => {
  const { render } = setup({ revokeOtherSessions: async () => { throw new Error("密码错误"); } });
  let tree = render();
  otherDevicesButton(tree).props.onClick();
  tree = render();
  assert.equal(passwordInput(tree).props.value, "");
  assert.equal(passwordInput(tree).props.readOnly, true);
  passwordInput(tree).props.onFocus();
  passwordInput(tree).props.onChange({ target: { value: "password123" } });
  tree = render();
  await dialogForm(tree).props.onSubmit({ preventDefault() {} });
  tree = render();
  assert.equal(passwordInput(tree).props.value, "");
  assert.equal(find(tree, (node) => node.props?.role === "alert")?.props.children, "密码错误");
  dialogRoot(tree).props.onOpenChange(false);
  tree = render();
  otherDevicesButton(tree).props.onClick();
  tree = render();
  assert.equal(passwordInput(tree).props.value, "");
  assert.equal(passwordInput(tree).props.readOnly, true);
});

test("all-device logout clears the password before the request finishes", async () => {
  let finishLogout;
  const { render, authEvents } = setup({ logoutAllSessions: () => new Promise((resolve) => { finishLogout = resolve; }) });
  let tree = render();
  find(tree, (node) => node.type === "button" && node.props.children === "退出全部设备").props.onClick();
  tree = render();
  passwordInput(tree).props.onFocus();
  passwordInput(tree).props.onChange({ target: { value: "password123" } });
  tree = render();
  const pending = dialogForm(tree).props.onSubmit({ preventDefault() {} });
  tree = render();
  assert.equal(passwordInput(tree).props.value, "");
  assert.deepEqual(authEvents, []);
  finishLogout();
  await pending;
  tree = render();
  assert.equal(dialogRoot(tree).props.open, false);
  assert.deepEqual(authEvents, ["clear"]);
});
