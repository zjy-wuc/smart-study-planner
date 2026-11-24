"use client";

import * as AlertDialog from "@radix-ui/react-alert-dialog";
import { aiPractice as m } from "@/messages/zh-CN/ai-practice";

export function ConfirmDelete({ disabled, onConfirm }: { disabled: boolean; onConfirm: () => void }) {
  return <AlertDialog.Root>
    <AlertDialog.Trigger type="button" disabled={disabled}>{m.delete}</AlertDialog.Trigger>
    <AlertDialog.Portal>
      <AlertDialog.Overlay className="ai-practice-dialog-overlay" />
      <AlertDialog.Content className="ai-practice-dialog">
        <AlertDialog.Title>{m.delete}</AlertDialog.Title>
        <AlertDialog.Description>{m.deleteConfirm}</AlertDialog.Description>
        <div className="ai-practice-dialog-actions">
          <AlertDialog.Cancel type="button">{m.cancelDelete}</AlertDialog.Cancel>
          <AlertDialog.Action type="button" className="ai-practice-dialog-danger" onClick={onConfirm}>{m.confirmDelete}</AlertDialog.Action>
        </div>
      </AlertDialog.Content>
    </AlertDialog.Portal>
  </AlertDialog.Root>;
}
