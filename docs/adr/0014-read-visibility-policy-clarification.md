# ADR-0014: Read Visibility Policy Clarification

## Status

Proposed

## Context

`Functional and WorkLogik.md` (canonical functional requirements) states:
- «Обозреватель — может смотреть всё»
- «Кладовщик — может просматривать всё»

This mandates global read visibility for observer and storekeeper roles: they must be able to see data from all sites/sku without site-scoping restrictions.

ADR-0005 ("Token Auth And Site-Scoped Access") describes a general model where non-root access is site-scoped through `UserAccessScope` (including `can_view`). This document predates the explicit read-visibility clarification and, when interpreted literally, suggests that read access should also be site-scoped — which contradicts the canonical requirements.

The production API code already implements global read visibility for read-capable roles. Tests and documentation lagged behind and contained assertions that incorrectly expected site-scoped read behavior.

## Decision

Read visibility for observer and storekeeper roles is **global** — all sites are visible regardless of `UserAccessScope` site assignments.

- `UserAccessScope.can_view` is no longer used to restrict read access for read-capable roles.
- `UserAccessScope.can_operate` and `can_manage_catalog` remain site-scoped — they govern operational (submit/operate) and catalog management rights per site.
- `root` and `chief_storekeeper` continue to have global access across all dimensions.
- The production API already implements this behavior; this ADR formalizes the policy.

## Consequences

### Pros
- Aligns with canonical functional requirements (`Functional and WorkLogik.md`)
- Simplifies read queries: no need to filter by user scope sites
- Observer/storekeeper can see cross-site stock, reports, and asset registers
- No production code changes needed — only test and documentation alignment

### Cons
- `UserAccessScope.can_view` becomes vestigial for read access decisions in the API layer
- ADR-0005's description of site-scoped `can_view` is now partially superseded

## Alternatives Considered

### Keep site-scoped read (revert production code)
Rejected — contradicts canonical functional requirements and would break the intended UX for observer and storekeeper roles.

### Remove `can_view` entirely
Possible future simplification, but `UserAccessScope.can_view` may still serve as an administrative signal (e.g., whether a user should be granted any access to a site). Out of scope for this ADR.

## Confidence

- **Confirmed by canonical requirements** — `Functional and WorkLogik.md` is the authoritative source
- **Confirmed by production code** — API already returns global read results
- **Confirmed by test alignment** — tests now reflect global read instead of site-scoped read
