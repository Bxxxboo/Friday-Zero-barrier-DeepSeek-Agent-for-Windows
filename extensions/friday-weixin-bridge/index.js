import fs from "node:fs";
import path from "node:path";

const DEFAULT_TIMEOUT_MS = 600_000;
/** OpenClaw openclaw.json hooks.timeoutMs 上限为 600000 */
const HOOK_TIMEOUT_MS = 600_000;
const WEIXIN_CHANNEL = "openclaw-weixin";

/** 同一条微信消息可能被多个 hook 并发触发，合并为一次 inbound 请求。 */
const inflightForwards = new Map();

function readBridgeToken(configPath, parsed) {
  const inline = String(parsed?.token ?? "").trim();
  if (inline) return inline;
  const tokenFile = String(parsed?.token_file ?? "api_token.txt").trim() || "api_token.txt";
  const tokenPath = path.join(path.dirname(configPath), tokenFile);
  try {
    if (!fs.existsSync(tokenPath)) return "";
    return fs.readFileSync(tokenPath, "utf-8").trim();
  } catch {
    return "";
  }
}

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
    const token = readBridgeToken(configPath, parsed);
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

function isWeixinChannel(event, ctx) {
  const values = [
    event?.channel,
    event?.channelId,
    ctx?.channelId,
    ctx?.messageProvider,
    event?.messageProvider,
    event?.OriginatingChannel,
    event?.Provider,
    ctx?.sessionKey,
  ];
  return values.some((value) => {
    const text = String(value ?? "").trim().toLowerCase();
    return text === WEIXIN_CHANNEL || text.includes("weixin");
  });
}

function resolvePeerId(event, ctx) {
  return String(
    event.senderId
      ?? event.conversationId
      ?? ctx.senderId
      ?? ctx.conversationId
      ?? "",
  ).trim();
}

function resolveContextToken(event, ctx, accountId, senderId) {
  const fromEvent = String(
    event.contextToken
      ?? event.context_token
      ?? ctx.contextToken
      ?? ctx.context_token
      ?? ctx.metadata?.contextToken
      ?? ctx.metadata?.context_token
      ?? "",
  ).trim();
  if (fromEvent) return fromEvent;
  return loadContextToken(accountId, senderId);
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

function saveContextToken(accountId, peerId, token) {
  if (!accountId || !peerId || !token) return;
  const filePath = path.join(
    process.env.USERPROFILE ?? "",
    ".openclaw",
    "openclaw-weixin",
    "accounts",
    `${accountId}.context-tokens.json`,
  );
  try {
    let data = {};
    if (fs.existsSync(filePath)) {
      const raw = JSON.parse(fs.readFileSync(filePath, "utf-8"));
      if (raw && typeof raw === "object") data = raw;
    }
    data[peerId] = token;
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, `${JSON.stringify(data, null, 2)}\n`, "utf-8");
  } catch {
    // Friday 侧也会持久化 context_token
  }
}

async function refreshBridgeToken(bridge) {
  try {
    const resp = await fetch(`${bridge.baseUrl}/api/auth/token`, {
      signal: AbortSignal.timeout(5000),
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    const token = String(data?.token ?? "").trim();
    if (!token) return null;
    return token;
  } catch {
    return null;
  }
}

async function postInbound(bridge, payload, token) {
  return fetch(`${bridge.baseUrl}/api/weixin/inbound`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Friday-Token": token,
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(bridge.timeoutMs),
  });
}

async function forwardToFridayOnce(api, args) {
  const key = `${args.accountId}:${args.senderId}:${args.text}`;
  const existing = inflightForwards.get(key);
  if (existing) {
    api.logger?.info?.(
      `friday-weixin-bridge: coalesce duplicate forward peer=${args.senderId.slice(0, 24)}`,
    );
    return existing;
  }
  const promise = forwardToFriday(api, args).finally(() => {
    inflightForwards.delete(key);
  });
  inflightForwards.set(key, promise);
  return promise;
}

async function forwardToFriday(api, { text, senderId, accountId, contextToken }) {
  const bridge = resolveBridgeConfig();
  if (!bridge) {
    return { text: unavailableText() };
  }

  const payload = {
    text,
    sender_id: senderId,
    peer_id: senderId,
    account_id: accountId,
    context_token: contextToken,
    channel: WEIXIN_CHANNEL,
  };

  try {
    let token = bridge.token;
    let resp = await postInbound(bridge, payload, token);
    if (resp.status === 401) {
      const fresh = await refreshBridgeToken(bridge);
      if (fresh) {
        token = fresh;
        resp = await postInbound(bridge, payload, token);
      }
    }
    if (!resp.ok) {
      api.logger?.warn?.(`friday-weixin-bridge: HTTP ${resp.status}`);
      return { text: unavailableText("星期五暂时不可用，请确认客户端已启动。") };
    }
    const data = await resp.json();
    if (!data?.handled) {
      return {
        text: unavailableText("星期五未处理此消息（可能桥接已关闭）。请打开桌面版检查「设置 → 微信桥接」。"),
      };
    }
    // 空 reply：Friday 已通过 iLink 送达；非空 reply：iLink 失败，交 OpenClaw 通道发送。
    return { text: String(data.reply ?? "").trim() };
  } catch (err) {
    api.logger?.warn?.(`friday-weixin-bridge: ${String(err)}`);
    return { text: unavailableText() };
  }
}

function extractMessageText(event) {
  return String(
    event.content ?? event.body ?? event.bodyForAgent ?? "",
  ).trim();
}

async function handleWeixinMessage(api, event, ctx) {
  const text = extractMessageText(event);
  if (!text || text.startsWith("/")) return null;

  const senderId = resolvePeerId(event, ctx);
  const accountId = String(ctx.accountId ?? event.accountId ?? "").trim();
  if (!senderId) {
    api.logger?.warn?.("friday-weixin-bridge: missing peer id");
    return { text: "无法识别发送者（缺少 conversationId）。" };
  }

  const contextToken = resolveContextToken(event, ctx, accountId, senderId);
  if (contextToken) {
    saveContextToken(accountId, senderId, contextToken);
  }

  api.logger?.info?.(
    `friday-weixin-bridge: forward peer=${senderId.slice(0, 24)} chars=${text.length}`,
  );
  return forwardToFridayOnce(api, { text, senderId, accountId, contextToken });
}

function toBeforeDispatchResult(result) {
  if (!result) return;
  return { handled: true, text: String(result.text ?? "").trim() };
}

function blockBuiltinWeixinAgent(message) {
  return {
    outcome: "block",
    reason: "friday-weixin-bridge",
    message,
  };
}

export default {
  id: "friday-weixin-bridge",
  name: "Friday Weixin Bridge",
  description: "Route Weixin text commands to the Friday desktop agent",
  register(api) {
    api.on(
      "before_dispatch",
      async (event, ctx) => {
        if (!isWeixinChannel(event, ctx)) return;
        return toBeforeDispatchResult(await handleWeixinMessage(api, event, ctx));
      },
      { priority: 110, timeoutMs: HOOK_TIMEOUT_MS },
    );

    api.on(
      "before_agent_run",
      (event, ctx) => {
        if (!isWeixinChannel(event, ctx)) return;
        if (!resolveBridgeConfig()) {
          return blockBuiltinWeixinAgent(
            "星期五桥接未配置。请打开电脑上的「星期五」，在「设置 → 微信桥接」完成连接。",
          );
        }
        return blockBuiltinWeixinAgent(
          "此微信会话应由星期五桌面版处理。若未收到回复，请在「设置 → 微信桥接」点「启动 Gateway」后重试。",
        );
      },
      { priority: 100, timeoutMs: 15_000 },
    );

    api.logger?.info?.("friday-weixin-bridge: before_dispatch registered (single inbound path)");
  },
};
