import { initLlama, type LlamaContext } from "llama.rn";

import type { CrisisReport, ReportPriority } from "../contracts/report";
import { ensureAssetCopiedToStorage } from "../offline/assetStorage";

/**
 * Fully offline chat + report-triage assistant (Qwen2.5-1.5B-Instruct,
 * Q4_K_M GGUF, ~1GB). Runs entirely on-device via llama.rn/llama.cpp — no
 * network call, no dependency on ai-service reachability, so it keeps
 * working exactly where the mesh does: no internet at all.
 *
 * Every small (~1-2B parameter) open model has noticeably weaker Bangla
 * output than English; that is a real limitation of this size class, not a
 * bug here. See mobile-client/README.md for the honest caveat to show users.
 */

const MODEL_ASSET_PATH = "models/qwen2.5-1.5b-instruct-q4_k_m.gguf";
const MODEL_FILE_NAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf";

const STOP_WORDS = [
  "</s>",
  "<|end|>",
  "<|eot_id|>",
  "<|end_of_text|>",
  "<|im_end|>",
  "<|EOT|>",
  "<|END_OF_TURN_TOKEN|>",
  "<|end_of_turn|>",
  "<|endoftext|>",
];

const SYSTEM_PROMPT =
  "You are an offline assistant embedded in Protidhoni, a Bangladesh " +
  "crisis-response app used by people who may have no internet access. " +
  "You are not a source of emergency dispatch and cannot contact anyone. " +
  "Answer briefly and clearly, in the same language (Bangla or English) the " +
  "user wrote in. When asked which report to work on first, rely only on " +
  "the priority list given to you in context -- do not invent an ordering.";

export type AssistantStatus =
  | { state: "idle" }
  | { state: "preparing"; detail: string }
  | { state: "ready" }
  | { state: "error"; message: string };

let context: LlamaContext | null = null;
let initPromise: Promise<LlamaContext> | null = null;

async function modelFilePath(onStatus?: (status: AssistantStatus) => void): Promise<string> {
  return ensureAssetCopiedToStorage(MODEL_ASSET_PATH, MODEL_FILE_NAME, detail =>
    onStatus?.({ state: "preparing", detail }),
  );
}

/** Idempotent: concurrent callers share the same in-flight init. */
export async function getLocalAssistant(
  onStatus?: (status: AssistantStatus) => void,
): Promise<LlamaContext> {
  if (context) return context;
  if (initPromise) return initPromise;

  initPromise = (async () => {
    try {
      const path = await modelFilePath(onStatus);
      onStatus?.({ state: "preparing", detail: "Loading the offline assistant model…" });
      const loaded = await initLlama({
        model: `file://${path}`,
        use_mlock: true,
        n_ctx: 2048,
      });
      context = loaded;
      onStatus?.({ state: "ready" });
      return loaded;
    } catch (error) {
      initPromise = null;
      const message = error instanceof Error ? error.message : String(error);
      onStatus?.({ state: "error", message });
      throw error;
    }
  })();

  return initPromise;
}

export type ChatMessage = { role: "user" | "assistant"; content: string };

export async function sendChatMessage(
  history: ChatMessage[],
  onToken?: (token: string) => void,
): Promise<string> {
  const llama = await getLocalAssistant();
  const result = await llama.completion(
    {
      messages: [{ role: "system", content: SYSTEM_PROMPT }, ...history],
      n_predict: 256,
      stop: STOP_WORDS,
    },
    onToken ? data => onToken(data.token) : undefined,
  );
  return result.text.trim();
}

const PRIORITY_RANK: Record<Exclude<ReportPriority, null>, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

/**
 * The ranking itself is deterministic, not LLM-driven: a small on-device
 * model is not reliable enough to trust with safety-relevant ordering
 * decisions. The LLM's only job (in askAboutPriorities below) is to phrase
 * an answer *about* this already-computed list, the same retrieve-then-
 * describe split ai-service's classifier/chat boundary would use if this
 * ran server-side.
 */
export function prioritizeReports(reports: readonly CrisisReport[]): CrisisReport[] {
  return [...reports].sort((a, b) => {
    const rankA = a.priority ? PRIORITY_RANK[a.priority] : PRIORITY_RANK.low + 1;
    const rankB = b.priority ? PRIORITY_RANK[b.priority] : PRIORITY_RANK.low + 1;
    if (rankA !== rankB) return rankA - rankB;
    return a.created_at.localeCompare(b.created_at);
  });
}

function summarizeForPrompt(reports: readonly CrisisReport[]): string {
  if (reports.length === 0) return "(no reports queued on this device)";
  return prioritizeReports(reports)
    .slice(0, 10)
    .map((report, index) => {
      const priority = report.priority ?? "unclassified";
      const peopleCount = report.payload.people_count;
      const peopleNote = peopleCount ? `, ${peopleCount} people` : "";
      return `${index + 1}. [${priority}] ${report.type}${peopleNote}: ${report.payload.text.slice(0, 140)}`;
    })
    .join("\n");
}

/** Answers a free-text question about which local report to act on first,
 * grounded in the deterministic priority list above -- never the model's
 * own unconstrained judgment about report content. */
export async function askAboutPriorities(
  question: string,
  reports: readonly CrisisReport[],
  onToken?: (token: string) => void,
): Promise<string> {
  const context_block =
    "Locally queued reports, already sorted most urgent first:\n" + summarizeForPrompt(reports);
  return sendChatMessage(
    [
      { role: "user", content: `${context_block}\n\n${question}` },
    ],
    onToken,
  );
}

export function releaseLocalAssistant(): void {
  const active = context;
  context = null;
  initPromise = null;
  if (active) {
    active.release().catch(() => undefined);
  }
}
