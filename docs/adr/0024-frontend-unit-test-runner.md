# ADR-0024 — Frontend unit-test runner: `@angular/build:unit-test` only

- Status: Accepted
- Date: 2026-07-31
- Deciders: frontend-tech-lead, architect
- Source TZ: `Warehouse_frontend/docs/TZ-FRONTEND_VITEST_ZONELESS_FIX.md` (commit `349af0b`, branch `dev`)

## Context

`Warehouse_frontend` has carried two divergent unit-test runners:

1. Standalone `npx vitest run` via `vitest.config.ts` + `src/test-setup.ts`,
   which uses esbuild for TypeScript. esbuild performs **zero Angular
   compilation**: it does not emit `design:paramtypes` decorator
   metadata, does not register signal `input()` bindings, and does not
   inline `templateUrl`/`styleUrl` resources. It also does not type-check.
2. Official `npx ng test` via `@angular/build:unit-test` (declared in
   `angular.json`), which uses the real Angular toolchain (ngtsc +
   esbuild) and runs vitest under the hood in Angular 21. Until
   2026-07-31 this runner **failed at build time** on spec/model type
   drift (TS2353, TS2554, TS2739, TS18048, TS2741 across five spec
   files), so zero tests executed; the canonical command recorded by
   `TZ_OPERATIONS_ACCEPTANCE_PLAYWRIGHT.md` (line 586) was already
   `npx ng test --watch=false`.

Confirmed baseline (commit `e6ef250`, 2026-07-31):

- `npx vitest run` → 4 failed files / 15 failed tests (106 total),
  1 unhandled error.
- `npx ng test --watch=false` → build-time failure: 8 TS errors in
  5 spec files (see TZ §RC5).

Five distinct root causes were identified:

1. RC1 — constructor DI metadata missing (group A, 7 NG0202 fails).
2. RC2 — signal `input()` invisible to JIT (group C, 2 NG0303 fails).
3. RC3 — external `templateUrl` not resolvable (group D, 2 fails).
4. RC4 — spec-local DI setup bugs in `logging.spec.ts` (group B, 4
   fails), runner-independent (NG0203 from `new GlobalErrorHandler()`
   with `inject()` field initializers; NG0201 → unhandled error →
   `expectOne` finds no request).
5. RC5 — spec type drift, blocks the official builder outright; esbuild
   skips type-checking, so this drift is invisible to standalone vitest
   but is real drift between specs and production models.

A stop-gap layered two workaround patterns on top of the broken
standalone vitest path: `useFactory: () => new OperationsService(...)`
in `operations.service.spec.ts`, and per-component `overrideInputs` +
`Object.defineProperty` shims in four temp-items specs. Both shims
existed only because the standalone transformer could not supply the
metadata that ngtsc would.

## Decision

1. **`@angular/build:unit-test` (invoked as `npx ng test`,
   `npx ng test --watch=false`, `npm run test:unit`, or `npm test`
   in watch mode) is the single canonical unit-test runner.**
2. **`vitest.config.ts` and `src/test-setup.ts` are removed.**
   vitest and jsdom stay in `devDependencies` because the builder
   consumes them.
3. **Spec type drift (RC5) is repaired in 5 spec files.** Going forward,
   the builder type-checks specs on every run; such drift becomes a
   build error rather than silent decay.
4. **The two workaround patterns are reverted** (L4/L5):
   `useFactory` in `operations.service.spec.ts` is replaced with plain
   Angular DI through the real constructor; the `overrideInputs` /
   `Object.defineProperty` shims in four temp-items specs are replaced
   with `fixture.componentRef.setInput(...)`.
5. **`logging.spec.ts` DI setup (RC4) is rewritten** with explicit
   `DiagnosticsService` / `Router` providers and `TestBed.inject`
   instead of manual `new`.
6. **Zoneless remains the project's reality** — no `zone.js` is added
   anywhere; the discipline borrowed from approach D (explicit
   `await fixture.whenStable()` where needed) is absorbed into the
   prescribed spec fixes, not enabled via zone.

## Consequences

Positive:

- All 15 vitest-only failures close without reopening any RC1–RC3.
- Spec/model drift now fails the build on the same CI run that catches
  test failures; there is no longer a second, permissive path.
- The service spec under real DI exposes a broader class of regressions
  than the previous `useFactory` workaround (which only tested the
  manual constructor invocation).
- CI investment in vitest muscle memory stays valid — the builder runs
  vitest under the hood.

Negative / accepted tradeoffs:

- Watch-mode (`npm test`) is slower than raw `npx vitest run` because
  the builder initialises per file. Acceptable for the unit-test scope
  (16 files, 106 tests, ≈1.7 s).
- Builder pre-warm on first run takes a few seconds (`Application
  bundle generation complete` ≈ 5 s cold, ≈ 0.1 s incremental).
  Acceptable.

Rejected alternatives:

- **SWC + `emitDecoratorMetadata`** — fixes RC1 only, leaves RC2/RC3
  open because signal inputs have no decorators and `templateUrl`
  still needs the Angular resource loader.
- **`@analogjs/vitest-angular`** — duplicative of `@angular/build`,
  adds a dev-dependency whose Angular 21 / vitest 4 compatibility is
  unverified.
- **Accept zoneless and rework specs to avoid signal inputs** — does
  not address RC1–RC3 because DI metadata and template inlining are
  still needed; would require a large, behavior-equivalent production
  rewrite that is explicitly out of scope for this TZ.

## Followups

- CI workflow `.github/workflows/frontend-unit-tests.yml` runs
  `npx ng test --watch=false` on push/PR to `dev` and `main`. See
  the TZ L8 commit.
- Existing `e2e-tests.yml` is unchanged — Playwright is a separate
  runner with separate coverage.
- If the Angular team later enables a faster `application testing`
  builder, revisit only if it preserves the same compile-time drift
  gate. Do not silently fall back to a second runner.

## Evidence

| Check | Command | Result |
|---|---|---|
| Baseline reproduced (standalone vitest) | `npx vitest run` | 4 failed files / 15 failed tests |
| Baseline reproduced (official builder) | `npx ng test --watch=false` | build-time failure: 8 TS errors in 5 spec files |
| Final state | `npx ng test --watch=false` | 16/16 files, 106/106 tests pass |
| Workaround cleanup | `grep -rn 'overrideInputs\|Object.defineProperty' src/app/features/temporary-items/` | no matches |
| Workaround cleanup | `grep -n 'useFactory' src/app/core/services/operations.service.spec.ts` | no matches |
| Runner consolidation | `grep -rn 'test-setup\|vitest.config' src/ angular.json tsconfig*.json package.json` | no matches |
| Build smoke | `npm run build` | green (pre-existing SCSS budget warnings only) |
