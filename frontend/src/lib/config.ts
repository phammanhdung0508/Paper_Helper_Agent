/**
 * Build-time and runtime configuration.
 *
 * Public flags must be prefixed with NEXT_PUBLIC_ so Next.js inlines them
 * into the client bundle.
 */

/**
 * If false (default), visualization generation is deferred: a tag's viz only
 * fires when the user actually clicks it. This is the production UX — it keeps
 * the user's Codex usage proportional to what they actually open, which
 * matters a lot on long documents (a 100-page PDF can carry hundreds of tags,
 * and eagerly rendering all of them would burn the usage window for scenes the
 * student never looks at).
 *
 * Set NEXT_PUBLIC_AUTO_GENERATE_VIZ="true" to opt into the eager behavior,
 * where every tag's viz is generated in parallel as soon as detection finds
 * it. Either way the user can flip this live from the Settings popover.
 *
 * The check uses `=== "true"` so any other value (or unset) defaults to the
 * lazy / click-to-generate behavior.
 */
export const AUTO_GENERATE_VIZ =
  process.env.NEXT_PUBLIC_AUTO_GENERATE_VIZ === "true";

/**
 * When the visualizer fails to compile or run a generated spec (typically
 * a SyntaxError in LLM-emitted Three.js / Canvas code), we hand the broken
 * code + the error message back to codex and ask it to regenerate. This
 * sets the maximum number of additional generation calls per tag. So the
 * total number of attempts is `1 + MAX_VIZ_GEN_RETRIES`.
 *
 * Default: 3 (i.e. up to 4 generation calls per tag).
 */
export const MAX_VIZ_GEN_RETRIES = (() => {
  const raw = process.env.NEXT_PUBLIC_MAX_VIZ_GEN_RETRIES;
  if (!raw) return 3;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 3;
})();
