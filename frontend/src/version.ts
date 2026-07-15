// App version — Changeset C17 §10. Single source of truth, shown as a small
// subscript next to the brand name in the header (header-bar.ts).
//
// 4 segments: MAJOR.MINOR.SPEC.CHANGESET.
//   - Bump the last segment by 1 every time a changeset is committed and published.
//   - Bump the 3rd segment by 1 (and reset the last one to 0) every time a new
//     spec is added under specs/domain/ or specs/00-engineering/.
//   - MAJOR.MINOR only change on an explicit request for a major/minor release.
//
// This is a standing project convention — see the memory file
// feedback-app-versioning.md — applied automatically, without being asked again.
export const APP_VERSION = '1.0.1.3';
