# ADR-0010: Token Ownership and Injection

## Status
Proposed

## Date
2026-05-16

## Context

`Warehouse_client_core` needs user and device tokens to authenticate with SyncServer. Secrets cannot be stored, logged, or hardcoded by the Rust core.

Stakeholders:
- **Platform secure storage** (Android Keystore, Windows DPAPI) owns persistent secret storage.
- **Rust core** must never persist raw token secrets in SQLite or log files.
- **CLI/test profiles** need a mechanism to inject tokens for development.

## Decision

### Ownership

- **Platform layer** (Kotlin/C# host) owns secret persistence and lifecycle.
- **Rust core** receives tokens through a bind/callback mechanism, stores only a SHA-256 hash of the user token for identity refresh verification.
- **Device token** is handled the same way as user token — the host provides it at bind time.

### Token injection

```rust
pub trait TokenProvider: Send + Sync {
    fn get_user_token(&self) -> Option<String>;
    fn get_device_token(&self) -> Option<String>;
}
```

- `CoreFacade::bind_token_provider(provider: Box<dyn TokenProvider>)` registers the provider.
- Core calls `get_user_token()` before each user-authenticated HTTP request.
- Core calls `get_device_token()` before each device-authenticated request.
- Provider may return `None` → core raises `CoreError::Unauthenticated`.

### CLI / Test tokens

- CLI reads tokens from environment variables only: `WHC_USER_TOKEN`, `WHC_DEVICE_TOKEN`.
- CLI's `TokenProvider` checks env vars at call time, not at bind time (supports hot-reload).
- No token values appear in CLI args, config files, or command history.

### Cache vs secrets

- Core caches identity metadata (user_id, role, name, available sites) in SQLite `auth_context` table.
- Core does NOT cache the raw user/device token in SQLite.
- Identity hash is stored for stale-detection only.

### Logging prohibition

- Any log line containing a full token UUID is a bug.
- Core logs `user:<hash_prefix>` instead of `user:<token>` for identity correlation.
- CI contract tests verify no token values in diagnostic output.

## Consequences

- Host platform owns security; core uses a narrow injection API.
- Environment variable approach for CLI is consistent with CI/CD best practices.
- Token hash in SQLite is a hint, not an auth mechanism — compromise of SQLite does not leak tokens.
- Provider pattern makes testing easy: `StaticTokenProvider { token: "test-token" }`.
- Platform change (e.g., from DPAPI to macOS Keychain) does not affect core.

## Confidence
**High** — pattern used by many production SDKs (e.g., Stripe, AWS SDKs).
