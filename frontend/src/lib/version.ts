/**
 * App version + about-page constants.
 *
 * The version is baked at build time from `package.json#version` into
 * the public env var NEXT_PUBLIC_APP_VERSION (see next.config.ts).
 * In dev / local installs the package.json version stays "0.0.0", so
 * the chip and welcome popup both render "v0.0.0" — only a CI build
 * triggered by a pushed git tag rewrites package.json to the real
 * release number ahead of `next build`.
 */

export const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? "0.0.0";

export const GITHUB_OWNER = "beltromatti";
export const GITHUB_REPO = "get-it";
export const GITHUB_URL = `https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}`;
export const GITHUB_RELEASES_API = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/releases/latest`;
export const GITHUB_RELEASES_URL = `${GITHUB_URL}/releases`;

export const FEEDBACK_EMAIL = "beltromatti@gmail.com";

export const TEAM = [
  { name: "Mattia Beltrami", affiliation: "Politecnico di Milano" },
  { name: "Matteo Impieri", affiliation: "Politecnico di Milano" },
  { name: "Filippo Difronzo", affiliation: "Politecnico di Milano" },
  { name: "Luca Feggi", affiliation: "Università di Padova" },
] as const;
