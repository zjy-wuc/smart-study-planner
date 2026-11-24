"use client";

import * as AlertDialog from "@radix-ui/react-alert-dialog";
import { aiPractice as m } from "@/messages/zh-CN/ai-practice";

export function ConfirmDiscard({ onConfirm }: { onConfirm: () => void }) {
  return <AlertDialog.Root>
    <AlertDialog.Trigger type="button">{m.discard}</AlertDialog.Trigger>
    <AlertDialog.Portal>
      <AlertDialog.Overlay className="ai-practice-dialog-overlay" />
      <AlertDialog.Content className="ai-practice-dialog">
        <AlertDialog.Title>{m.discard}</AlertDialog.Title>
        <AlertDialog.Description>{m.leave}</AlertDialog.Description>
        <div className="ai-practice-dialog-actions">
          <AlertDialog.Cancel type="button">{m.keepAnswering}</AlertDialog.Cancel>
          <AlertDialog.Action type="button" className="ai-practice-dialog-danger" onClick={onConfirm}>{m.confirmDiscard}</AlertDialog.Action>
        </div>
      </AlertDialog.Content>
    </AlertDialog.Portal>
  </AlertDialog.Root>;
}
