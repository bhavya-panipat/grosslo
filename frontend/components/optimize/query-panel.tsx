"use client";

import { useState } from "react";
import { Loader2, MessageCircle, Send, Sparkles, Zap } from "lucide-react";
import CardShell from "@/components/card-shell";
import type { QueryContext, QueryResponse } from "@/lib/api-types";
import type { FormState } from "@/components/optimize/manual-entry-card";

type Message = { question: string; answer: string; aiBacked: boolean };

export default function QueryPanel({
  form,
  context,
}: {
  form: FormState;
  context: QueryContext;
}) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);

  const handleAsk = async () => {
    if (!question.trim() || loading) return;
    const q = question.trim();
    setQuestion("");
    setLoading(true);
    try {
      const res = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: q,
          ctc: form.ctc || 0,
          rent_paid: form.rentPaid || 0,
          city: form.city,
          nps_opted: form.npsOpted,
          context,
        }),
      });
      const result: QueryResponse = await res.json();
      if (!res.ok) {
        setMessages((prev) => [
          ...prev,
          { question: q, answer: result.error ?? "That question couldn't be answered — try rephrasing it.", aiBacked: false },
        ]);
        return;
      }
      setMessages((prev) => [
        ...prev,
        { question: q, answer: result.answer ?? "No answer available.", aiBacked: result.ai_backed },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { question: q, answer: "Couldn't reach the query service — try again in a moment.", aiBacked: false },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <CardShell>
      <div className="flex items-center gap-2 text-neutral-300">
        <MessageCircle className="h-4 w-4 text-gold-bright" />
        <h3 className="font-display text-lg font-semibold text-white">Ask a follow-up</h3>
      </div>

      {messages.length > 0 && (
        <div className="mt-4 max-h-[420px] space-y-4 overflow-y-auto pr-1">
          {messages.map((m, i) => (
            <div key={i} className="space-y-1.5">
              <p className="text-sm font-medium text-neutral-200">{m.question}</p>
              <div className="flex items-start gap-2 rounded-lg border border-white/[0.06] bg-black/30 p-3 text-sm text-neutral-400">
                {m.aiBacked ? (
                  <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gold-bright" />
                ) : (
                  <Zap className="mt-0.5 h-3.5 w-3.5 shrink-0 text-neutral-500" />
                )}
                <span>{m.answer}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-4 flex items-center gap-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAsk()}
          placeholder="e.g. Why does the new regime win here?"
          className="flex-1 rounded-full border border-white/10 bg-black/40 px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-gold-bright/50 focus:outline-none"
        />
        <button
          onClick={handleAsk}
          disabled={!question.trim() || loading}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white text-black transition-transform hover:scale-105 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </button>
      </div>
    </CardShell>
  );
}
