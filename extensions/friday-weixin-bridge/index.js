import fs from "node:fs";
import path from "node:path";

const DEFAULT_TIMEOUT_MS = 600_000;
const WEIXIN_CHANNEL = "openclaw-weixin";

function resolveBridgeConfig() {
  const configPath = path.join(
    process.env.APPDATA ?? path.join(process.env.USERPROFILE ?? "", "AppData", "Roaming"),
    "Friday",
    "weixin-bridge.json",
  );
  try {
    if (!fs.existsSync(configPath)) return null;
    const raw = fs.readFileSync(configPath, "utf-8");
    const parsed = JSON.parse(raw);
    if (!parsed || parsed.enabled === false) return null;
    const baseUrl = String(parsed.base_url ?? "").replace(/\/$/, "");
    const token = String(parsed.token ?? "").trim();
    if (!baseUrl || !token) return null;
    return {
      baseUrl,
      token,
      timeoutMs: Number(parsed.timeout_ms ?? DEFAULT_TIMEOUT_MS) || DEFAULT_TIMEOUT_MS,
      configPath,
    };
  } catch {
    return null;
  }
}

function unavailableText(reason) {
  return reason ?? "星期五未运行或桥接未就绪。请先打开电脑上的「星期五」客户端。";
}

function resolvePeerId(event, ctx) {
  return String(
    event.senderId ??
      ctx.senderId ??
      ctx.conversationId ??
      "",
  ).trim();
}

function loadContextToken(accountId, peerId) {
  if (!accountId || !peerId) return "";
  const filePath = path.join(
    process.env.USERPROFILE ?? "",
    ".openclaw",
    "openclaw-weixin",
    "accounts",
    `${accountId}.context-tokens.json`,
  );
  try {
    if (!fs.existsSync(filePath)) return "";
    const data = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    return String(data?.[peerId] ?? "").trim();
  } catch {
    return "";
  }
}

async function forwardToFriday(api, { text, senderId, accountId, contextToken }) {
  const bridge = resolveBridgeConfig();
  if (!bridge) {
    return { handled: true, text: unavailableText() };
  }

  try {
    const resp = await fetch(`${bridge.baseUrl}/api/weixin/inbound`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Friday-Token": bridge.token,
      },
      body: JSON.stringify({
        text,
        sender_id: senderId,
        account_id: accountId,
        context_token: contextToken,
        channel: WEIXIN_CHANNEL,
      }),
      signal: AbortSignal.timeout(bridge.timeoutMs),
    });
    if (!resp.ok) {
      api.logger?.warn?.(`friday-weixin-bridge: HTTP ${resp.status}`);
      return { handled: true, text: unavailableText("星期五暂时不可用，请确认客户端已启动。") };
    }
    const data = await resp.json();
    if (!data?.handled) return;
    const replyText = String(data.reply ?? "").trim();
    // 空回复：星期五已通过 iLink 直接发微信（收到/审批/结果），此处勿再占位回复。
    if (!replyText) return { handled: true };
    return { handled: true, text: replyText };
  } catch (err) {
    api.logger?.warn?.(`friday-weixin-bridge: ${String(err)}`);
    return { handled: true, text: unavailableText() };
  }
}

export default {
  id: "friday-weixin-bridge",
  name: "Friday Weixin Bridge",
  description: "Route Weixin text commands to the Friday desktop agent",
  register(api) {
    // inbound_claim 仅对 plugin-bound 会话生效；微信普通 DM 走 before_dispatch。
    api.on(
      "before_dispatch",
      async (event, ctx) => {
        const channel = String(event.channel ?? ctx.channelId ?? "").trim();
        if (channel !== WEIXIN_CHANNEL && !channel.includes("weixin")) return;

        const text = String(event.body ?? event.content ?? "").trim();
        if (!text || text.startsWith("/")) return;

        const senderId = resolvePeerId(event, ctx);
        const accountId = String(ctx.accountId ?? "").trim();
        if (!senderId) {
          api.logger?.warn?.("friday-weixin-bridge: missing peer id");
          return { handled: true, text: "无法识别发送者（缺少 conversationId）。" };
        }

        return forwardToFriday(api, {
          text,
          senderId,
          accountId,
          contextToken: loadContextToken(accountId, senderId),
        });
      },
      { priority: 100 },
    );

    api.logger?.info?.("friday-weixin-bridge: before_dispatch hook registered");
  },
};
