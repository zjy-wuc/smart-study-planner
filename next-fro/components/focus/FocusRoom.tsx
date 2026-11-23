"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  Expand,
  Minimize2,
  MoreHorizontal,
  Pause,
  Play,
  RotateCcw,
  Square,
  Volume2,
  X,
} from "lucide-react";

import { messages } from "@/messages";
import { useFocusSession } from "@/hooks/useFocusSession";
import { listPlans } from "@/services/plans.service";
import { listPlanTasks } from "@/services/tasks.service";

import type { Plan } from "@/types/plan";
import type { PlanTask } from "@/types/task";
import type { FocusSession, FocusSessionType, FocusStart } from "@/types/focus";

import "@/components/css/Focus.css";

type SoundScene = "rain" | "sea" | "stream" | "crickets";
type VisualScene = "study" | SoundScene;

const SOUND_SCENES: { id: SoundScene; label: string; audio: string; image: string }[] = [
  { id: "rain", label: messages.focus.rain, audio: "/focus/audio/rain.mp3", image: "/focus/images/rain.jpg" },
  { id: "sea", label: messages.focus.sea, audio: "/focus/audio/sea.mp3", image: "/focus/images/sea.jpg" },
  { id: "stream", label: messages.focus.stream, audio: "/focus/audio/stream.mp3", image: "/focus/images/stream.jpg" },
  { id: "crickets", label: messages.focus.summerNight, audio: "/focus/audio/crickets.mp3", image: "/focus/images/night.jpg" },
];

function isSoundScene(value: string | null): value is SoundScene {
  return SOUND_SCENES.some((item) => item.id === value);
}

function getSoundScene(scene: SoundScene) {
  return SOUND_SCENES.find((item) => item.id === scene) ?? SOUND_SCENES[0];
}

function formatClock(seconds: number, showHours = false) {
  const safe = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  return showHours || hours > 0
    ? [hours, minutes, secs].map((value) => String(value).padStart(2, "0")).join(":")
    : [minutes, secs].map((value) => String(value).padStart(2, "0")).join(":");
}

function formatMinutes(seconds: number) {
  return Math.max(0, Math.round(seconds / 60));
}

function sessionReachedGoal(session: FocusSession) {
  return session.session_type === "POMODORO"
    && session.planned_seconds !== null
    && session.focused_seconds >= session.planned_seconds;
}

function useAmbientSound() {
  const [scene, setScene] = useState<SoundScene>(() => {
    if (typeof window === "undefined") return "rain";
    const saved = window.localStorage.getItem("focus-sound-scene");
    return isSoundScene(saved) ? saved : "rain";
  });
  const [volume, setVolume] = useState(() => {
    if (typeof window === "undefined") return 38;
    const saved = Number(window.localStorage.getItem("focus-sound-volume"));
    return Number.isFinite(saved) ? saved : 38;
  });
  const [playing, setPlaying] = useState(false);
  const [visualScene, setVisualScene] = useState<VisualScene>("study");
  const audio = useRef<HTMLAudioElement | null>(null);

  function stop() {
    audio.current?.pause();
    setPlaying(false);
  }

  function start(selected: SoundScene = scene) {
    const source = getSoundScene(selected).audio;
    setVisualScene(selected);
    const current = audio.current ?? new Audio(source);
    if (!audio.current) audio.current = current;
    if (!current.src.endsWith(source)) {
      current.src = source;
      current.load();
    }
    current.loop = true;
    current.volume = volume / 100;
    void current.play()
      .then(() => setPlaying(true))
      .catch(() => setPlaying(false));
  }

  useEffect(() => () => {
    audio.current?.pause();
    audio.current?.removeAttribute("src");
  }, []);

  useEffect(() => {
    window.localStorage.setItem("focus-sound-volume", String(volume));
    if (audio.current) audio.current.volume = volume / 100;
  }, [volume]);

  function selectScene(nextScene: SoundScene) {
    setScene(nextScene);
    setVisualScene(nextScene);
    window.localStorage.setItem("focus-sound-scene", nextScene);
    if (playing) start(nextScene);
  }

  return { scene, visualScene, setScene: selectScene, volume, setVolume, playing, start: () => start(), stop };
}

function FocusSummary({ session, onClose, onBreak }: {
  session: FocusSession;
  onClose: () => void;
  onBreak: () => void;
}) {
  const [sharing, setSharing] = useState(false);
  const reached = sessionReachedGoal(session);

  function exportCard() {
    try {
      const canvas = document.createElement("canvas");
      canvas.width = 960;
      canvas.height = 600;
      const context = canvas.getContext("2d");
      if (!context) throw new Error(messages.focus.exportFailed);
      const gradient = context.createLinearGradient(0, 0, 960, 600);
      gradient.addColorStop(0, "#eaf3ff");
      gradient.addColorStop(1, "#f5fbf8");
      context.fillStyle = gradient;
      context.fillRect(0, 0, 960, 600);
      context.fillStyle = "#ffffff";
      context.roundRect(80, 72, 800, 456, 32);
      context.fill();
      context.fillStyle = "#2c67c7";
      context.font = "600 28px Microsoft YaHei";
      context.fillText(messages.common.appName, 136, 145);
      context.fillStyle = "#20354d";
      context.font = "700 52px Microsoft YaHei";
      context.fillText(messages.focus.shareTitle, 136, 232);
      context.fillStyle = "#2867ce";
      context.font = "700 104px Microsoft YaHei";
      context.fillText(String(formatMinutes(session.focused_seconds)), 136, 360);
      context.font = "500 30px Microsoft YaHei";
      context.fillText(messages.focus.minuteShort, 275, 356);
      context.fillStyle = "#617287";
      context.font = "400 24px Microsoft YaHei";
      context.fillText(messages.focus.shareSubtitle, 136, 430);
      context.fillText(session.focus_date, 136, 474);
      const link = document.createElement("a");
      link.download = `focus-${session.focus_date}.png`;
      link.href = canvas.toDataURL("image/png");
      link.click();
    } catch {
      window.alert(messages.focus.exportFailed);
    }
  }

  return (
    <div className="focus-summary-backdrop" role="dialog" aria-modal="true" aria-labelledby="focus-summary-title">
      <section className="focus-summary-card">
        <button type="button" className="focus-icon-button focus-summary-close" onClick={onClose} aria-label={messages.focus.closeSummary}><X size={18} /></button>
        <span className="focus-summary-mark" aria-hidden="true"><Check size={24} /></span>
        <h2 id="focus-summary-title">{messages.focus.completed}</h2>
        <p>{reached ? messages.focus.completedGoal : messages.focus.completedEarly}</p>
        <div className="focus-summary-duration"><strong>{formatMinutes(session.focused_seconds)}</strong><span>{messages.focus.minuteShort}</span></div>
        <dl>
          <div><dt>{messages.focus.completedMode}</dt><dd>{session.session_type === "POMODORO" ? messages.focus.pomodoro : messages.focus.stopwatch}</dd></div>
          <div><dt>{messages.focus.completedDuration}</dt><dd>{formatClock(session.focused_seconds, true)}</dd></div>
        </dl>
        {sharing && (
          <div className="focus-share-preview">
            <small>{messages.common.appName}</small>
            <strong>{messages.focus.shareTitle}</strong>
            <span>{messages.focus.recordDuration(formatMinutes(session.focused_seconds))}</span>
            <p>{messages.focus.shareSubtitle}</p>
          </div>
        )}
        <div className="focus-summary-actions">
          <button type="button" className="focus-button focus-button--primary" onClick={onBreak}>{messages.focus.startBreak}</button>
          <button type="button" className="focus-button" onClick={onClose}>{messages.focus.continueStudy}</button>
          <button type="button" className="focus-button" onClick={() => setSharing((value) => !value)}>{messages.focus.shareResult}</button>
          {sharing && <button type="button" className="focus-button" onClick={exportCard}>{messages.focus.exportCard}</button>}
        </div>
      </section>
    </div>
  );
}

export function FocusRoom() {
  const pageRef = useRef<HTMLDivElement | null>(null);
  const nativeFullscreenActive = useRef(false);
  const focus = useFocusSession();
  const ambient = useAmbientSound();
  const [mode, setMode] = useState<FocusSessionType>("POMODORO");
  const [plannedMinutes, setPlannedMinutes] = useState(25);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [tasks, setTasks] = useState<PlanTask[]>([]);
  const [planId, setPlanId] = useState<number | null>(null);
  const [taskId, setTaskId] = useState<number | null>(null);
  const [selectionError, setSelectionError] = useState("");
  const [immersive, setImmersive] = useState(false);
  const [immersiveIdle, setImmersiveIdle] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [breakMinutes, setBreakMinutes] = useState(5);
  const [breakOpen, setBreakOpen] = useState(false);
  const [breakEndsAt, setBreakEndsAt] = useState<number | null>(null);
  const [breakNow, setBreakNow] = useState(() => Date.now());
  const effectivePlanId = focus.session?.plan_id ?? planId;
  const canAutoHide = immersive
    && !!focus.session
    && focus.session.status !== "PAUSED"
    && !toolsOpen
    && !breakOpen
    && !focus.completed;

  useEffect(() => {
    let active = true;
    listPlans()
      .then((items) => { if (active) setPlans(items.filter((plan) => plan.status === "ACTIVE")); })
      .catch(() => { if (active) setSelectionError(messages.focus.planLoadFailed); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!effectivePlanId) return;
    let active = true;
    listPlanTasks(effectivePlanId)
      .then((items) => {
        if (active) setTasks(items.filter((task) => task.status === "PENDING" || task.status === "IN_PROGRESS"));
      })
      .catch(() => { if (active) setSelectionError(messages.focus.taskLoadFailed); });
    return () => { active = false; };
  }, [effectivePlanId]);

  useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !document.fullscreenElement) {
        setToolsOpen(false);
        setImmersive(false);
      }
    }
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, []);

  useEffect(() => {
    function handleFullscreenChange() {
      const active = document.fullscreenElement === pageRef.current;
      if (active) {
        nativeFullscreenActive.current = true;
        setImmersive(true);
        return;
      }
      if (nativeFullscreenActive.current) {
        nativeFullscreenActive.current = false;
        setToolsOpen(false);
        setImmersiveIdle(false);
        setImmersive(false);
      }
    }
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  useEffect(() => {
    if (!breakEndsAt) return;
    const timer = window.setInterval(() => setBreakNow(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, [breakEndsAt]);

  useEffect(() => {
    if (!canAutoHide) return;

    let timer = window.setTimeout(() => setImmersiveIdle(true), 30_000);
    function markActive() {
      window.clearTimeout(timer);
      setImmersiveIdle(false);
      timer = window.setTimeout(() => setImmersiveIdle(true), 30_000);
    }

    window.addEventListener("pointermove", markActive, { passive: true });
    window.addEventListener("pointerdown", markActive, { passive: true });
    window.addEventListener("touchstart", markActive, { passive: true });
    window.addEventListener("keydown", markActive);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("pointermove", markActive);
      window.removeEventListener("pointerdown", markActive);
      window.removeEventListener("touchstart", markActive);
      window.removeEventListener("keydown", markActive);
    };
  }, [canAutoHide]);

  const breakRemaining = breakEndsAt ? Math.max(0, Math.ceil((breakEndsAt - breakNow) / 1000)) : 0;
  const selectedPlan = plans.find((plan) => plan.id === effectivePlanId);
  const selectedTask = tasks.find((task) => task.id === (focus.session?.task_id ?? taskId));
  const taskLabel = selectedTask?.content || selectedTask?.step_name || selectedPlan?.name || "";
  const activeMode = focus.session?.session_type ?? mode;
  const circleStyle = { "--focus-progress": `${Math.max(0.01, focus.progress) * 360}deg` } as React.CSSProperties;

  async function begin() {
    const request: FocusStart = {
      session_type: mode,
      planned_seconds: mode === "POMODORO" ? plannedMinutes * 60 : null,
      plan_id: planId,
      task_id: taskId,
    };
    await focus.begin(request);
  }

  const stats = focus.statistics?.today;
  const isPaused = focus.session?.status === "PAUSED";
  const idleActive = canAutoHide && immersiveIdle;

  async function enterImmersive() {
    setImmersiveIdle(false);
    setToolsOpen(false);
    setImmersive(true);
    try {
      await pageRef.current?.requestFullscreen();
    } catch {
      nativeFullscreenActive.current = false;
    }
  }

  const exitImmersive = useCallback(async () => {
    setImmersiveIdle(false);
    setToolsOpen(false);
    setImmersive(false);
    if (document.fullscreenElement === pageRef.current) {
      await document.exitFullscreen().catch(() => undefined);
    }
  }, []);

  useEffect(() => {
    if (!((focus.completed || breakOpen) && immersive)) return;
    const timer = window.setTimeout(() => void exitImmersive(), 0);
    return () => window.clearTimeout(timer);
  }, [breakOpen, exitImmersive, focus.completed, immersive]);

  return (
    <div ref={pageRef} className={`focus-page${immersive ? " is-immersive" : ""}${idleActive ? " is-idle" : ""}`} data-scene={ambient.visualScene}>
      <header className="focus-page-header">
        <div><h1>{messages.focus.title}</h1><p>{messages.focus.subtitle}</p></div>
      </header>

      {focus.loading ? <p className="focus-loading" role="status">{messages.focus.loading}</p> : (
        <>
          {focus.error && <div className="focus-error" role="alert"><span>{focus.error}</span><button type="button" disabled={focus.syncing} onClick={() => void focus.synchronize()}>{focus.syncing ? messages.focus.syncing : messages.focus.retrySync}</button></div>}
          <div className="focus-workbench">
            <main className="focus-timer-panel">
              <div className="focus-mode-switch" role="group" aria-label={messages.focus.modeLabel}>
                <button type="button" aria-pressed={activeMode === "POMODORO"} disabled={!!focus.session} onClick={() => setMode("POMODORO")}>{messages.focus.pomodoro}</button>
                <button type="button" aria-pressed={activeMode === "STOPWATCH"} disabled={!!focus.session} onClick={() => setMode("STOPWATCH")}>{messages.focus.stopwatch}</button>
              </div>

              <div className={`focus-ring${isPaused ? " is-paused" : ""}`} style={circleStyle}>
                <div>
                  <span>{focus.session ? (isPaused ? messages.focus.paused : messages.focus.running) : messages.focus.ready}</span>
                  <strong>{focus.session ? formatClock(focus.displaySeconds, focus.session.session_type === "STOPWATCH") : formatClock(activeMode === "POMODORO" ? plannedMinutes * 60 : 0, activeMode === "STOPWATCH")}</strong>
                  <small>{focus.session?.session_type === "STOPWATCH" ? messages.focus.focused : messages.focus.remaining}</small>
                </div>
              </div>

              {!focus.session && mode === "POMODORO" && (
                <div className="focus-duration-options" role="group" aria-label={messages.focus.plannedMinutes}>
                  {[15, 25, 45, 60].map((minutes) => <button key={minutes} type="button" aria-pressed={plannedMinutes === minutes} onClick={() => setPlannedMinutes(minutes)}>{messages.focus.minutesOption(minutes)}</button>)}
                </div>
              )}

              {!immersive && taskLabel && <p className="focus-current-label">{taskLabel}</p>}
              <div className="focus-action-area">
                {!immersive && <button type="button" className="focus-button focus-immersive-entry" onClick={() => void enterImmersive()}><Expand size={17} />{messages.focus.immersiveMode}</button>}
                <div className="focus-controls">
                  {!focus.session ? (
                    <button type="button" className="focus-button focus-button--primary focus-start" onClick={() => void begin()} disabled={focus.working}><Play size={18} fill="currentColor" />{messages.focus.start}</button>
                  ) : (
                    <>
                      <button type="button" className="focus-button focus-button--primary" onClick={() => { setImmersiveIdle(false); void (isPaused ? focus.resume() : focus.pause()); }} disabled={focus.working}>{isPaused ? <Play size={17} fill="currentColor" /> : <Pause size={17} fill="currentColor" />}{isPaused ? messages.focus.resume : messages.focus.pause}</button>
                      <button type="button" className="focus-button" onClick={() => void focus.finish()} disabled={focus.working}><Square size={16} />{messages.focus.finish}</button>
                      <button type="button" className="focus-text-action" onClick={async () => { if (!window.confirm(messages.focus.cancelConfirm)) return; await focus.cancel(); await exitImmersive(); }} disabled={focus.working}>{messages.focus.cancelSession}</button>
                    </>
                  )}
                </div>
                {immersive && <>
                  <button type="button" className="focus-button focus-immersive-exit" onClick={() => void exitImmersive()}><Minimize2 size={17} />{messages.focus.exitImmersive}</button>
                  <button type="button" className="focus-immersive-tools" onClick={() => setToolsOpen((value) => !value)} aria-label={toolsOpen ? messages.focus.closeTools : messages.focus.openTools}>{toolsOpen ? <X size={20} /> : <MoreHorizontal size={22} />}</button>
                </>}
              </div>
            </main>

            <aside className={`focus-tools${immersive && toolsOpen ? " is-open" : ""}`}>
              <section className="focus-tool-section">
                <div className="focus-section-heading"><div><h2>{messages.focus.currentTask}</h2><p>{messages.focus.currentTaskDescription}</p></div></div>
                {!focus.session ? <>
                  <label><span>{messages.focus.choosePlan}</span><select value={planId ?? ""} onChange={(event) => { const value = event.target.value; setPlanId(value ? Number(value) : null); setTaskId(null); setTasks([]); setSelectionError(""); }}><option value="">{messages.focus.independentFocus}</option>{plans.map((plan) => <option value={plan.id} key={plan.id}>{plan.name}</option>)}</select></label>
                  <label><span>{messages.focus.chooseTask}</span><select value={taskId ?? ""} disabled={!planId} onChange={(event) => setTaskId(event.target.value ? Number(event.target.value) : null)}><option value="">{messages.focus.noTask}</option>{tasks.map((task) => <option value={task.id} key={task.id}>{task.content || task.step_name}</option>)}</select></label>
                  <small>{messages.focus.taskHint}</small>
                  {selectionError && <p className="focus-inline-error" role="alert">{selectionError}</p>}
                </> : <div className="focus-linked-task"><span>{selectedPlan?.name || messages.focus.independentFocus}</span><strong>{taskLabel || messages.focus.currentTaskDescription}</strong></div>}
              </section>

              <section className="focus-tool-section">
                <div className="focus-section-heading"><div><h2>{messages.focus.environment}</h2><p>{messages.focus.environmentSubtitle}</p></div><button type="button" className="focus-sound-toggle" onClick={() => ambient.playing ? ambient.stop() : ambient.start()} aria-label={ambient.playing ? messages.focus.pauseSound : messages.focus.playSound}>{ambient.playing ? <Pause size={16} fill="currentColor" /> : <Play size={16} fill="currentColor" />}</button></div>
                <div className="focus-scenes">{SOUND_SCENES.map(({ id, label, image }) => <button type="button" key={id} aria-pressed={ambient.scene === id} onClick={() => ambient.setScene(id)}><span className="focus-scene-image" style={{ backgroundImage: `url(${image})` }} aria-hidden="true" /><span className="focus-scene-label">{label}</span></button>)}</div>
                <label className="focus-volume"><Volume2 size={17} /><span>{messages.focus.volume}</span><input type="range" min="0" max="100" value={ambient.volume} onChange={(event) => ambient.setVolume(Number(event.target.value))} /></label>
              </section>
            </aside>
          </div>

          {!immersive && <>
            <section className="focus-today" aria-labelledby="focus-today-title">
              <div><h2 id="focus-today-title">{messages.focus.todayOverview}</h2><p>{messages.focus.subtitle}</p></div>
              <dl><div><dt>{messages.focus.todayDuration}</dt><dd>{formatMinutes(stats?.focused_seconds ?? 0)}<small>{messages.focus.minuteShort}</small></dd></div><div><dt>{messages.focus.todaySessions}</dt><dd>{stats?.session_count ?? 0}<small>{messages.common.timesUnit}</small></dd></div><div><dt>{messages.focus.todayPomodoros}</dt><dd>{stats?.completed_pomodoros ?? 0}<small>{messages.common.plansUnit}</small></dd></div></dl>
            </section>
            <section className="focus-recent">
              <div className="focus-section-heading"><div><h2>{messages.focus.recentTitle}</h2></div></div>
              {!focus.history?.items.length ? <p className="focus-empty">{messages.focus.noHistory}</p> : <ul>{focus.history.items.map((item) => <li key={item.id}><span className={`focus-record-icon${item.status === "CANCELLED" ? " is-cancelled" : ""}`}>{item.status === "CANCELLED" ? <X size={15} /> : <Check size={15} />}</span><div><strong>{item.session_type === "POMODORO" ? messages.focus.pomodoro : messages.focus.stopwatch}</strong><p>{item.focus_date} · {item.status === "CANCELLED" ? messages.focus.cancelled : messages.focus.recordDuration(formatMinutes(item.focused_seconds))}</p></div><span>{item.status === "CANCELLED" ? messages.focus.cancelled : messages.focus.completedStatus}</span></li>)}</ul>}
            </section>
          </>}

        </>
      )}

      {focus.completed && !breakOpen && <FocusSummary session={focus.completed} onClose={focus.dismissCompleted} onBreak={() => { setBreakOpen(true); focus.dismissCompleted(); }} />}
      {breakOpen && (
        <div className="focus-summary-backdrop" role="dialog" aria-modal="true" aria-labelledby="focus-break-title">
          <section className="focus-summary-card focus-break-card">
            <span className="focus-summary-mark"><RotateCcw size={23} /></span><h2 id="focus-break-title">{messages.focus.breakTitle}</h2>
            {!breakEndsAt ? <><p>{messages.focus.breakMinutes}</p><div className="focus-duration-options focus-break-options"><button type="button" aria-pressed={breakMinutes === 5} onClick={() => setBreakMinutes(5)}>{messages.focus.shortBreak}</button><button type="button" aria-pressed={breakMinutes === 15} onClick={() => setBreakMinutes(15)}>{messages.focus.longBreak}</button></div><button type="button" className="focus-button focus-button--primary" onClick={() => { const startedAt = Date.now(); setBreakNow(startedAt); setBreakEndsAt(startedAt + breakMinutes * 60_000); }}>{messages.focus.beginBreak}</button></> : breakRemaining > 0 ? <><p>{messages.focus.breakRemaining}</p><strong className="focus-break-time">{formatClock(breakRemaining)}</strong><button type="button" className="focus-button focus-button--primary" onClick={() => { setBreakEndsAt(null); setBreakOpen(false); }}>{messages.focus.endBreak}</button></> : <><p>{messages.focus.breakFinished}</p><strong className="focus-break-time">00:00</strong><button type="button" className="focus-button focus-button--primary" onClick={() => { setBreakEndsAt(null); setBreakOpen(false); }}>{messages.focus.continueStudy}</button></>}
          </section>
        </div>
      )}
    </div>
  );
}
