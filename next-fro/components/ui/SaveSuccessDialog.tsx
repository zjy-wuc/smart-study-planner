"use client";

import { CheckCircle2 } from "lucide-react";
import { messages } from "@/messages";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "./dialog";
import "@/components/css/SaveSuccessDialog.css";

type Props = {
  message: string | null;
  onClose: () => void;
};

export function SaveSuccessDialog({ message, onClose }: Props) {
  return (
    <Dialog open={Boolean(message)} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="save-success-dialog">
        <CheckCircle2 className="save-success-icon" size={38} aria-hidden="true" />
        <DialogHeader>
          <DialogTitle>{message}</DialogTitle>
          <DialogDescription>{messages.common.saveSuccessDescription}</DialogDescription>
        </DialogHeader>
        <button type="button" onClick={onClose}>{messages.common.continue}</button>
      </DialogContent>
    </Dialog>
  );
}
