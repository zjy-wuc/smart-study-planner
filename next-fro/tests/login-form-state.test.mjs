import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

const source = fs.readFileSync(new URL("../components/auth/LoginForm.tsx", import.meta.url), "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText;

class ApiError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
    this.status = 401;
  }
}

function setup(loginUser = async () => ({ authEpoch: "test", data: { user: {} } })) {
  const state = [];
  let cursor = 0;
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in state)) state[index] = initial;
      return [state[index], (next) => { state[index] = typeof next === "function" ? next(state[index]) : next; }];
    },
  };
  const copy = { usernameLogin: "username", emailPasswordLogin: "email-password", emailCodeLogin: "email-code" };
  const dependencies = {
    react,
    "react/jsx-runtime": { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    "next/navigation": { useRouter: () => ({ replace() {} }) },
    "next/link": () => null,
    "@/contexts/AuthContext": { useAuth: () => ({ completeLogin() {} }) },
    "@/lib/auth/coordinator": { sameAuthEpoch: () => true },
    "@/lib/api/client": { ApiError },
    "@/services/auth.service": { loginUser, loginWithEmail: loginUser, sendEmailCode: async () => {} },
    "@/messages": { messages: { auth: copy, common: { appName: "Study" } } },
    "@/components/css/LoginForm.css": {},
    "@/components/css/AuthFields.css": {},
  };
  const module = { exports: {} };
  new Function("require", "module", "exports", output)((name) => {
    if (!(name in dependencies)) throw new Error(`Unexpected import: ${name}`);
    return dependencies[name];
  }, module, module.exports);
  return () => { cursor = 0; return module.exports.default(); };
}

function find(node, predicate) {
  if (Array.isArray(node)) return node.map((child) => find(child, predicate)).find(Boolean);
  if (!node || typeof node !== "object") return undefined;
  if (predicate(node)) return node;
  return find(node.props?.children, predicate);
}

const input = (tree, id) => find(tree, (node) => node.type === "input" && node.props.id === id);
const tab = (tree, name) => find(tree, (node) => node.type === "button" && node.props.children === name);

test("switching login modes clears the identifier, password and one-time code", () => {
  const render = setup();
  let tree = render();
  input(tree, "login-identifier").props.onChange({ target: { value: "student" } });
  input(tree, "login-password").props.onChange({ target: { value: "password123" } });
  tree = render();
  tab(tree, "username").props.onClick();
  tree = render();
  assert.equal(input(tree, "login-password").props.value, "password123");
  tab(tree, "email-code").props.onClick();
  tree = render();
  assert.equal(input(tree, "login-identifier").props.value, "");
  input(tree, "login-code").props.onChange({ target: { value: "123456" } });
  tree = render();
  tab(tree, "username").props.onClick();
  tree = render();
  assert.equal(input(tree, "login-password").props.value, "");
  tab(tree, "email-code").props.onClick();
  tree = render();
  assert.equal(input(tree, "login-code").props.value, "");
});

test("credential rejection clears the password; network and rate-limit errors keep it", async () => {
  for (const [failure, expected] of [[new ApiError("INVALID_CREDENTIALS"), ""], [new Error("offline"), "password123"], [new ApiError("RATE_LIMITED"), "password123"]]) {
    const render = setup(async () => { throw failure; });
    let tree = render();
    input(tree, "login-identifier").props.onChange({ target: { value: "student" } });
    input(tree, "login-password").props.onChange({ target: { value: "password123" } });
    tree = render();
    await tree.props.onSubmit({ preventDefault() {} });
    tree = render();
    assert.equal(input(tree, "login-password").props.value, expected);
    assert.equal(input(tree, "login-identifier").props.value, "student");
  }
});

test("invalid email code clears only the code, and successful login clears the secret", async () => {
  const renderInvalid = setup(async () => { throw new ApiError("EMAIL_CODE_INVALID"); });
  let tree = renderInvalid();
  tab(tree, "email-code").props.onClick();
  tree = renderInvalid();
  input(tree, "login-identifier").props.onChange({ target: { value: "student@example.com" } });
  input(tree, "login-code").props.onChange({ target: { value: "123456" } });
  tree = renderInvalid();
  await tree.props.onSubmit({ preventDefault() {} });
  tree = renderInvalid();
  assert.equal(input(tree, "login-identifier").props.value, "student@example.com");
  assert.equal(input(tree, "login-code").props.value, "");

  const renderSuccess = setup();
  tree = renderSuccess();
  input(tree, "login-identifier").props.onChange({ target: { value: "student" } });
  input(tree, "login-password").props.onChange({ target: { value: "password123" } });
  tree = renderSuccess();
  await tree.props.onSubmit({ preventDefault() {} });
  tree = renderSuccess();
  assert.equal(input(tree, "login-password").props.value, "");
});

test("changing the email invalidates the code typed for the previous address", () => {
  const render = setup();
  let tree = render();
  tab(tree, "email-code").props.onClick();
  tree = render();
  input(tree, "login-code").props.onChange({ target: { value: "123456" } });
  tree = render();
  input(tree, "login-identifier").props.onChange({ target: { value: "new@example.com" } });
  tree = render();
  assert.equal(input(tree, "login-code").props.value, "");
});
