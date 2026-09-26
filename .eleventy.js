const fs = require("fs");

module.exports = function(eleventyConfig) {
  // Pass through static files
  eleventyConfig.addPassthroughCopy("src/images");
  eleventyConfig.addPassthroughCopy("src/favicon.svg");
  eleventyConfig.addPassthroughCopy("src/apple-touch-icon.png");
  eleventyConfig.addPassthroughCopy("src/robots.txt");
  eleventyConfig.addPassthroughCopy("src/llms.txt");

  // Date formatting filter
  eleventyConfig.addFilter("readableDate", (dateObj) => {
    return new Date(dateObj).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  });

  // Short date filter
  eleventyConfig.addFilter("shortDate", (dateObj) => {
    return new Date(dateObj).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short'
    });
  });

  // A testimonial may only be published if consent was actually recorded. This is
  // enforced at build time rather than left to discipline: approving one without
  // permission.granted fails the build instead of quietly going live.
  eleventyConfig.on("eleventy.before", () => {
    const path = "./src/_data/testimonials.json";
    if (!fs.existsSync(path)) return;
    const data = JSON.parse(fs.readFileSync(path, "utf8"));
    const bad = (data.items || []).filter(
      (t) => t.approved === true && !(t.permission && t.permission.granted === true)
    );
    if (bad.length) {
      throw new Error(
        `Refusing to build: ${bad.length} testimonial(s) approved without recorded ` +
        `permission — ${bad.map((t) => t.id).join(", ")}. Set permission.granted ` +
        `and permission.grantedAt, or set approved to false.`
      );
    }
  });

  // "2026-08" -> "August 2026", for testimonial stay dates
  eleventyConfig.addFilter("monthLabel", (ym) => {
    if (!ym) return "";
    const [y, m] = String(ym).split("-");
    const d = new Date(Number(y), Number(m) - 1, 1);
    if (isNaN(d)) return "";
    return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long' });
  });

  // ISO date filter (for sitemap and RSS feed)
  eleventyConfig.addFilter("isoDate", (dateObj) => {
    return new Date(dateObj).toISOString();
  });

  return {
    dir: {
      input: "src",
      output: "_site",
      includes: "_includes"
    }
  };
};
