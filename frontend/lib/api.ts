import type {
  AnalyzeResponse,
  AssistantChatResponse,
  DemoSignalsResponse,
  HealthResponse,
} from "./types";

const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? ""
).replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 15000,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      credentials: "include",
      headers: { ...Object.fromEntries(new Headers(init?.headers).entries()), "X-BCI-Request": "1" },
      signal: controller.signal,
    });
  } catch (error) {
    const errorName =
      typeof error === "object" && error !== null && "name" in error
        ? String(error.name)
        : "";
    throw new ApiError(
      0,
      errorName === "AbortError"
        ? "后端响应超时，请稍后重试。"
        : "无法连接后端服务，请检查服务状态或网络配置后重试。",
    );
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    let detail = `请求失败（HTTP ${response.status}）`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // 忽略非 JSON 错误响应
    }
    throw new ApiError(response.status, detail);
  }

  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/v1/health"),

  demoSignals: (trialCount = 8) =>
    request<DemoSignalsResponse>(
      `/api/v1/demo/signals?trial_count=${trialCount}`,
    ),

  analyze: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    form.append("sampling_rate_hz", "250");
    form.append("unit", "uV");
    return request<AnalyzeResponse>(
      "/api/v1/analyze",
      { method: "POST", body: form },
      30000,
    );
  },

  askAssistant: (question: string) =>
    request<AssistantChatResponse>(
      "/api/v1/assistant/chat",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      },
      50000,
    ),
};
