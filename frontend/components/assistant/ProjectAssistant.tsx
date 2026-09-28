"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { AssistantSource } from "@/lib/types";

type AssistantState = "closed" | "open" | "minimized" | "hidden";

interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources?: AssistantSource[];
  error?: boolean;
}

const WELCOME =
  "你好，我可以帮你了解 个体化脑机辅助控制平台的研究背景、技术路线、实验平台和系统能力。";

const QUICK_QUESTIONS = [
  "项目解决什么问题？",
  "四分类意图是什么？",
  "FBCSP 如何识别脑电？",
  "如何完成校准和同源数据回放？",
  "EEG、EOG和人工急停如何配合？",
  "3D 模拟设备如何工作？",
];

function BrainwaveIcon({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 32 32"
      className={className}
      fill="none"
    >
      <path
        d="M4 17h4l2.2-6 3.2 12 3-15 3.3 11 2.1-5 2 3H28"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M7.5 7.7A11.5 11.5 0 0 1 16 4a11.6 11.6 0 0 1 8.8 4.1M7 24a11.5 11.5 0 0 0 9 4 11.5 11.5 0 0 0 8.8-4.1"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        opacity=".55"
      />
    </svg>
  );
}

export default function ProjectAssistant() {
  const pathname = usePathname();
  const [state, setState] = useState<AssistantState>("closed");
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: 1, role: "assistant", content: WELCOME },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const nextId = useRef(2);
  const sendLock = useRef(false);
  const messageEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (state === "open") {
      messageEndRef.current?.scrollIntoView({ block: "end" });
    }
  }, [messages, sending, state]);

  useEffect(() => {
    if (state !== "open") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setState("closed");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [state]);

  const hideAssistant = () => {
    setState("hidden");
  };

  const restoreAssistant = () => {
    setState("closed");
  };

  const sendQuestion = async (rawQuestion?: string) => {
    const question = (rawQuestion ?? input).trim();
    if (!question || sendLock.current || question.length > 500) return;
    sendLock.current = true;

    const userMessage: ChatMessage = {
      id: nextId.current++,
      role: "user",
      content: question,
    };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setSending(true);

    try {
      const response = await api.askAssistant(question);
      setMessages((current) => [
        ...current,
        {
          id: nextId.current++,
          role: "assistant",
          content: response.answer,
          sources: response.sources,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: nextId.current++,
          role: "assistant",
          content: error instanceof ApiError && error.status === 401
            ? "请先进入控制工作台登录，再使用项目智答。"
            : error instanceof ApiError ? error.message : "项目知识服务暂时不可用，请稍后再试。",
          error: true,
        },
      ]);
    } finally {
      sendLock.current = false;
      setSending(false);
      window.setTimeout(() => textareaRef.current?.focus(), 0);
    }
  };

  const positionClass = pathname === "/lab" ? "bottom-3 right-3" : "bottom-5 right-4 sm:right-6";

  if (state === "hidden") {
    return (
      <button
        type="button"
        onClick={restoreAssistant}
        className="fixed right-0 top-[55%] z-[70] rounded-l-xl border border-r-0 border-cyan-400/30 bg-slate-900/95 px-2 py-3 text-[11px] font-semibold tracking-[0.12em] text-cyan-200 shadow-xl backdrop-blur transition hover:bg-slate-800"
        aria-label="重新显示 BCI 智答入口"
      >
        <span className="[writing-mode:vertical-rl]">显示智答</span>
      </button>
    );
  }

  if (state === "closed") {
    return (
      <div className={`pointer-events-none fixed z-[70] flex items-center gap-2 ${positionClass}`}>
        <button
          type="button"
          onClick={hideAssistant}
          className="pointer-events-auto flex h-8 w-8 items-center justify-center rounded-full border border-slate-700/80 bg-slate-900/95 text-xs text-slate-400 shadow-lg transition hover:border-cyan-400/40 hover:text-cyan-200"
          aria-label="隐藏 BCI 智答入口"
          title="隐藏入口"
        >
          ×
        </button>
        <button
          type="button"
          onClick={() => setState("open")}
          className="assistant-breathe pointer-events-auto flex h-14 w-14 items-center justify-center rounded-full border border-cyan-300/35 bg-[radial-gradient(circle_at_35%_25%,rgba(34,211,238,0.28),rgba(15,23,42,0.98)_62%)] text-cyan-200 shadow-[0_14px_35px_rgba(8,145,178,0.22)] transition hover:-translate-y-0.5 hover:border-cyan-300/65 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-300"
          aria-label="打开 BCI 智答项目助手"
          title="BCI 智答 · 项目助手"
        >
          <BrainwaveIcon />
        </button>
      </div>
    );
  }

  if (state === "minimized") {
    return (
      <div className={`fixed z-[70] flex items-center overflow-hidden rounded-2xl border border-cyan-400/25 bg-slate-900/95 shadow-2xl backdrop-blur ${positionClass}`}>
        <button
          type="button"
          onClick={() => setState("open")}
          className="flex items-center gap-2 px-4 py-3 text-left text-sm font-semibold text-white hover:bg-slate-800"
          aria-label="展开 BCI 智答"
        >
          <BrainwaveIcon className="h-5 w-5 text-cyan-300" />
          BCI 智答
        </button>
        <button
          type="button"
          onClick={() => setState("closed")}
          className="border-l border-slate-700 px-3 py-3 text-slate-400 hover:bg-slate-800 hover:text-white"
          aria-label="关闭聊天窗口"
        >
          ×
        </button>
      </div>
    );
  }

  return (
    <section
      role="dialog"
      aria-label="BCI 智答项目知识助手"
      className="fixed inset-x-3 bottom-3 top-[84px] z-[70] flex min-h-0 flex-col overflow-hidden rounded-2xl border border-cyan-400/25 bg-slate-950/98 shadow-[0_24px_80px_rgba(2,6,23,0.72)] backdrop-blur-xl sm:inset-auto sm:bottom-5 sm:right-6 sm:top-auto sm:h-[min(650px,calc(100vh-110px))] sm:w-[410px]"
    >
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-800 bg-slate-900/90 px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-cyan-400/25 bg-cyan-500/10 text-cyan-300">
            <BrainwaveIcon className="h-6 w-6" />
          </span>
          <div className="min-w-0">
            <h2 className="truncate text-sm font-bold text-white">BCI 智答</h2>
            <p className="text-[11px] text-slate-400">项目知识助手</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={hideAssistant}
            className="rounded-lg px-2 py-1.5 text-[11px] text-slate-400 hover:bg-slate-800 hover:text-cyan-200"
            aria-label="隐藏悬浮助手"
            title="隐藏入口"
          >
            隐藏
          </button>
          <button
            type="button"
            onClick={() => setState("minimized")}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-800 hover:text-white"
            aria-label="最小化聊天窗口"
            title="最小化"
          >
            −
          </button>
          <button
            type="button"
            onClick={() => setState("closed")}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-800 hover:text-white"
            aria-label="关闭聊天窗口"
            title="关闭"
          >
            ×
          </button>
        </div>
      </header>

      <div className="thin-scrollbar min-h-0 flex-1 overflow-y-auto px-4 py-4" aria-live="polite">
        <div className="space-y-4">
          {messages.map((message) => (
            <article
              key={message.id}
              className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div className="max-w-[88%]">
                <div
                  className={`whitespace-pre-wrap rounded-2xl px-4 py-3 text-[13px] leading-6 ${
                    message.role === "user"
                      ? "rounded-br-md bg-cyan-400 text-slate-950"
                      : message.error
                        ? "rounded-bl-md border border-rose-400/25 bg-rose-500/10 text-rose-200"
                        : "rounded-bl-md border border-slate-700/80 bg-slate-900 text-slate-200"
                  }`}
                >
                  {message.content}
                </div>
                {message.sources && message.sources.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-1.5" aria-label="参考资料">
                    <span className="py-1 text-[10px] text-slate-500">参考：</span>
                    {message.sources.map((source) => (
                      <span
                        key={`${source.title}-${source.section}`}
                        className="rounded-full border border-cyan-400/20 bg-cyan-500/6 px-2 py-1 text-[10px] text-cyan-200"
                        title={`${source.title} · ${source.section}`}
                      >
                        {source.title} · {source.section}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            </article>
          ))}

          {messages.length === 1 ? (
            <div className="flex flex-wrap gap-2 pt-1">
              {QUICK_QUESTIONS.map((question) => (
                <button
                  key={question}
                  type="button"
                  disabled={sending}
                  onClick={() => void sendQuestion(question)}
                  className="rounded-full border border-slate-700 bg-slate-900/70 px-3 py-1.5 text-left text-[11px] text-slate-300 transition hover:border-cyan-400/40 hover:text-cyan-200 disabled:opacity-50"
                >
                  {question}
                </button>
              ))}
            </div>
          ) : null}

          {sending ? (
            <div className="flex justify-start" aria-label="助手正在思考">
              <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-md border border-slate-700/80 bg-slate-900 px-4 py-3">
                <span className="assistant-dot h-1.5 w-1.5 rounded-full bg-cyan-300" />
                <span className="assistant-dot h-1.5 w-1.5 rounded-full bg-cyan-300 [animation-delay:160ms]" />
                <span className="assistant-dot h-1.5 w-1.5 rounded-full bg-cyan-300 [animation-delay:320ms]" />
              </div>
            </div>
          ) : null}
          <div ref={messageEndRef} />
        </div>
      </div>

      <div className="shrink-0 border-t border-slate-800 bg-slate-900/75 p-3">
        <div className="rounded-xl border border-slate-700 bg-slate-950/80 p-2 focus-within:border-cyan-400/50">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void sendQuestion();
              }
            }}
            disabled={sending}
            maxLength={500}
            rows={2}
            placeholder="询问项目背景、算法或使用方式…"
            className="block max-h-28 min-h-12 w-full resize-none bg-transparent px-2 py-1 text-[13px] leading-6 text-white outline-none placeholder:text-slate-600 disabled:opacity-60"
            aria-label="输入项目问题"
          />
          <div className="flex items-center justify-between gap-3 px-2 pb-1">
            <span className="text-[10px] text-slate-600">Enter 发送 · Shift+Enter 换行</span>
            <button
              type="button"
              onClick={() => void sendQuestion()}
              disabled={sending || !input.trim()}
              className="rounded-lg bg-cyan-400 px-3 py-1.5 text-[11px] font-bold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {sending ? "发送中" : "发送"}
            </button>
          </div>
        </div>
        <p className="mt-2 text-center text-[10px] text-slate-500">问题与公开知识将发送至模型服务 · 智答不能操作设备</p>
      </div>
    </section>
  );
}
