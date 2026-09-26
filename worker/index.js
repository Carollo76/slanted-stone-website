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

// Retired dated roundups → their evergreen replacements. These must live here
// rather than in a _redirects file: /blog/* is in run_worker_first, so the worker
// serves those paths via env.ASSETS.fetch(), and Cloudflare does not apply
// _redirects to requests the worker handles. A _redirects entry would be ignored
// silently and these URLs would 404.
const RETIRED = {
  "/blog/posts/spring-2026-pocono-pines-guide/": "/blog/posts/spring-in-pocono-pines/",
  "/blog/posts/april-2026-pocono-pines-guide/": "/blog/posts/spring-in-pocono-pines/",
  "/blog/posts/may-2026-pocono-pines-guide/": "/blog/posts/spring-in-pocono-pines/",
  "/blog/posts/june-2026-pocono-pines-guide/": "/blog/posts/summer-in-pocono-pines/",
};

export default {
  async fetch(request, env, ctx) {
    const { pathname } = new URL(request.url);
    // Tolerate a missing trailing slash so both forms redirect.
    const target =
      RETIRED[pathname] || RETIRED[pathname + "/"] || null;
    if (target) {
      return Response.redirect(new URL(target, request.url).toString(), 301);
    }

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
