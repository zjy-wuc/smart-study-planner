import { messages } from "@/messages";

export default function AuthScene() {
  const copy = messages.auth;

  return (
    <aside className="login-scene" aria-label={copy.sceneTitle}>
      <p className="login-scene-title">{copy.sceneTitle}</p>
      <div className="login-scene-steps">
        <span>{copy.scenePlan}</span>
        <span aria-hidden="true">/</span>
        <span>{copy.sceneSteps}</span>
        <span aria-hidden="true">/</span>
        <span>{copy.sceneCheckin}</span>
      </div>
    </aside>
  );
}
