/**
 * Edge instrumentation for slantedstone.com.
 *
 * The site is a static Eleventy build served from the ASSETS binding. This worker
 * sits in front of it purely to observe: it records which AI crawlers fetch which
 * pages, and which AI assistants send human referrals. It never modifies a response.
 *
 * Logging is deliberately fire-and-forget via ctx.waitUntil so it cannot add latency
 * to, or fail, an asset response.
 */

// Substring => canonical operator name. Matched case-insensitively against User-Agent.
// Order matters: more specific tokens first (Claude-SearchBot before ClaudeBot).
const AI_CRAWLERS = [
  ["oai-searchbot", "openai"],
  ["chatgpt-user", "openai"],
  ["gptbot", "openai"],
  ["claude-searchbot", "anthropic"],
  ["claude-user", "anthropic"],
  ["claudebot", "anthropic"],
  ["perplexity-user", "perplexity"],
  ["perplexitybot", "perplexity"],
  ["google-extended", "google"],
  ["googlebot", "google"],
  ["bingbot", "bing"],
  ["applebot", "apple"],
  ["amazonbot", "amazon"],
  ["bytespider", "bytedance"],
  ["ccbot", "commoncrawl"],
  ["meta-externalagent", "meta"],
];

// Referrer hostnames that indicate a human arrived from an AI assistant.
const AI_REFERRERS = {
  "chatgpt.com": "openai",
  "chat.openai.com": "openai",
  "www.perplexity.ai": "perplexity",
  "perplexity.ai": "perplexity",
  "claude.ai": "anthropic",
  "gemini.google.com": "google",
  "copilot.microsoft.com": "microsoft",
};

function identifyCrawler(userAgent) {
  const ua = userAgent.toLowerCase();
  for (const [token, operator] of AI_CRAWLERS) {
    if (ua.includes(token)) return operator;
  }
  return null;
}

function identifyReferrer(referer) {
  if (!referer) return null;
  let host;
  try {
    host = new URL(referer).hostname.toLowerCase();
  } catch {
    return null; // malformed Referer header — ignore rather than throw
  }
  return AI_REFERRERS[host] || null;
}

export default {
  async fetch(request, env, ctx) {
    const response = env.ASSETS.fetch(request);

    // Analytics Engine may be unbound (local dev, or before the dataset exists).
    // Skip silently rather than breaking the site.
    if (env.CRAWLER_LOG) {
      try {
        const url = new URL(request.url);
        const operator = identifyCrawler(request.headers.get("user-agent") || "");
        const referrerOperator = operator
          ? null
          : identifyReferrer(request.headers.get("referer"));

        if (operator || referrerOperator) {
          ctx.waitUntil(
            Promise.resolve().then(() =>
              env.CRAWLER_LOG.writeDataPoint({
                // index1 is the sampling key — keep cardinality low.
                indexes: [operator || referrerOperator],
                blobs: [
                  operator ? "crawl" : "referral",
                  operator || referrerOperator,
                  url.pathname,
                  request.headers.get("cf-ipcountry") || "unknown",
                ],
                doubles: [1],
              })
            )
          );
        }
      } catch {
        // Never let instrumentation affect the response.
      }
    }

    return response;
  },
};
