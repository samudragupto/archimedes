"use client";

import { useRef, useState } from "react";
import { Loader2, Send, X } from "lucide-react";
import { ModelBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { streamChat } from "@/lib/api";
import type { ProjectAggregate } from "@/lib/types";

interface ChatTurn {
  role: "user" | "assistant";
  text: string;
  meta?: string;
}

const SUGGESTIONS = [
  "What are the hard deadlines I must not miss?",
  "Does my draft satisfy the page limit?",
  "Suggest stronger evaluation metrics for the grant.",
];

/**
 * Writing assistant: SSE-streamed chat backed by the project's own context
 * (requirements, findings, draft). When Nemotron Nano decides the question
 * needs the live web, the API runs a Tavily round first and the answer cites
 * it as [W1], [W2]…
 */
export function ChatPanel({
  aggregate,
  token,
  onClose,
}: {
  aggregate: ProjectAggregate;
  token: string;
  onClose: () => void;
}) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  async function send(message: string) {
    const text = message.trim();
    if (!text || streaming) return;
    setInput("");
    setTurns((prev) => [...prev, { role: "user", text }, { role: "assistant", text: "" }]);
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamChat(token, aggregate.id, text, (frame) => {
        setTurns((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (frame.delta !== undefined) {
            next[next.length - 1] = { ...last, text: last.text + frame.delta };
          }
          if (frame.done) {
            const bits = [
              frame.model ? `answered by ${frame.model.split("/").pop()}` : null,
              typeof frame.tokens_in === "number" && typeof frame.tokens_out === "number" ? `${frame.tokens_in}→${frame.tokens_out} tok` : null,
              frame.needs_web ? "live web round used" : null,
            ].filter(Boolean);
            next[next.length - 1] = { ...last, meta: bits.join(" · ") || undefined };
          }
          return next;
        });
      }, controller.signal);
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setTurns((prev) => {
          const next = [...prev];
          next[next.length - 1] = { ...next[next.length - 1], text: "The assistant could not answer just now — is the API server running?" };
          return next;
        });
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  return (
    <Card className="flex h-[34rem] flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              Writing assistant
              <ModelBadge modelUsed="nano" />
            </CardTitle>
            <CardDescription>Answers grounded in this project — asks Tavily when needed.</CardDescription>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close assistant">
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col gap-3">
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          {turns.length === 0 && (
            <div className="space-y-2 pt-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => void send(s)}
                  className="w-full rounded-md border bg-card px-3 py-2 text-left text-sm text-muted-foreground transition-colors hover:bg-secondary"
                >
                  {s}
                </button>
              ))}
            </div>
          )}
          {turns.map((turn, i) => (
            <div
              key={i}
              className={
                turn.role === "user"
                  ? "ml-6 rounded-lg rounded-br-sm bg-primary px-3 py-2 text-sm text-primary-foreground"
                  : "mr-2 whitespace-pre-wrap rounded-lg rounded-bl-sm border bg-card px-3 py-2 text-sm"
              }
            >
              {turn.text || (streaming && i === turns.length - 1 ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "")}
              {turn.meta && <p className="mt-1.5 font-sans text-[11px] text-muted-foreground">{turn.meta}</p>}
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <Textarea
            aria-label="Message the writing assistant"
            rows={2}
            placeholder="Ask about the solicitation, your draft, or the research…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(input);
              }
            }}
          />
          <Button size="icon" onClick={() => void send(input)} disabled={streaming || !input.trim()} aria-label="Send">
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
