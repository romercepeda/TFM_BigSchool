# Spec D06 — Price Levels, Alert Engine & Analysis History

**Status:** Approved
**Type:** Domain capability
**References:** Spec D02 (Portfolio Management), Spec D03 (Asset Holdings), Spec D05 (Indicator Catalog & Historical Snapshots), Spec 00b (Security Practices)

---

## 1. Purpose

Allow a user to record their analysis of an asset by defining one or more target price levels (buy or sell), preserve a complete, immutable history of every analysis they have ever made on that asset, and automatically surface when the current price has crossed any active level.

This is the spec that realizes the project's central motivation, stated by the project owner at the very start: *"que una vez yo haya analizado una acción pueda definir puntos de entrada o de venta y que eso en el tiempo no se me olvide."*

The spec covers three distinct concerns, deliberately kept separate:

1. **Active price levels** — live entities the alert engine evaluates against current prices. Editable, deletable.
2. **Alert detection** — the rule that decides when an active level is "touched" by the current price.
3. **Analysis history** — an immutable record of every level the user has ever defined, every modification, and every removal. This is what guarantees the user's past thinking is never lost, even when active levels are deleted.

---

## 2. Conceptual model

The cleanest way to understand this spec is to recognize that there are **two entities, not one**:

- A **PriceLevel** is alive: it can be created, edited, deleted, and it produces alerts when crossed.
- A **PriceLevelHistoryEntry** is a historical fact: an immutable record of an event (a level was defined, modified, marked as touched, or removed). It is never edited or deleted by the user in v1.

Every action on a PriceLevel produces a new PriceLevelHistoryEntry. The user-facing "Historial de análisis" screen reads from the history table; the alert engine reads from the active price-levels table. They have different lifecycles and different purposes.

---

## 3. `PriceLevel` entity (active levels)

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. |
| `holding_id` | UUID | Foreign key to `Holding` (per Spec D03). A price level is always associated with a specific holding in a specific portfolio. |
| `direction` | enum | `buy` \| `sell`. |
| `target_price` | NUMERIC | Price level in the asset's quote currency. Stored at full precision per Spec D04, §3.2. |
| `note` | text, nullable | Free-form user note for this level (e.g. *"Buenos resultados Q4. Espero retroceso a zona $175 antes de entrar"*). Per the project owner's decision, notes are **per-level**, not per analysis session. |
| `status` | enum | `armed` \| `touched`. See Section 5. |
| `created_at` | timestamp (UTC) | When the level was first defined. |
| `updated_at` | timestamp (UTC) | When any field of the level was last modified. |
| `touched_at` | timestamp (UTC), nullable | When the level first transitioned to `touched`. Null while `armed`. |
| `touched_at_close_price` | NUMERIC, nullable | The closing price that triggered the touch transition. Null while `armed`. |
| `touched_at_close_date` | date, nullable | The market date of that closing price. Null while `armed`. |

### 3.1 Multiplicity rules

- A holding can have **any number** of active price levels at the same time. The user explicitly asked for the ability to define multiple simultaneous levels (e.g. a laddered buy at `$170`, `$165`, `$160`, plus a sell target at `$210`) — this directly supports the analysis style of evaluating entry and exit jointly.
- There is no constraint that buy levels must be below sell levels, or any other cross-level rule. The user has full responsibility for the levels they define.
- There is no maximum number of levels per holding in v1; if a global limit is later deemed useful, it would be added via Spec 00f.

### 3.2 Editing

All fields of a PriceLevel (except `id`, `holding_id`, audit timestamps, and the touch-related fields) are editable while `status = armed`. Once `status = touched`, the level is still visible and operationally active (Section 5) but editing it is allowed only on `note`. The user cannot change the target price or direction of a touched level — to do so they create a new level and delete the touched one.

### 3.3 Deletion

A PriceLevel is **hard-deleted** when removed by the user. No `archived` state, no soft delete, no trace in this table.

However — and this is the key reconciliation between the user's two seemingly contradictory requirements — **before any modification or deletion takes effect**, the system writes a corresponding immutable entry to `PriceLevelHistoryEntry` (Section 4). Therefore the user's analysis is never lost, even though the active level disappears completely from this table.

---

## 4. `PriceLevelHistoryEntry` entity (immutable history)

This table records every event in the lifecycle of every price level the user has ever defined. Entries are append-only: never edited, never deleted by the user in v1.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. |
| `holding_id` | UUID | Foreign key to `Holding`. |
| `originating_level_id` | UUID | The `PriceLevel.id` this entry came from. Not a foreign key constraint (the level may no longer exist), but the value is preserved so that all history entries about the same level can be grouped together. |
| `event_type` | enum | `created` \| `edited` \| `touched` \| `removed`. |
| `event_at` | timestamp (UTC) | When the event occurred. |
| `direction` | enum | `buy` \| `sell`. Snapshotted at event time. |
| `target_price` | NUMERIC | Snapshotted at event time. |
| `note` | text, nullable | Snapshotted at event time. |
| `asset_price_at_event` | NUMERIC, nullable | The asset's quote-currency price at the time of the event (when known — typically the latest cached price). Useful for the historical view "el precio entonces era X". |
| `created_at` | timestamp (UTC) | When the history row itself was written. |

### 4.1 Append rules

Every state transition of a PriceLevel produces a history row. Specifically:

- **On PriceLevel creation:** one `created` row is written.
- **On PriceLevel edit:** one `edited` row is written, snapshotting the new values.
- **On automatic touch transition (alert engine):** one `touched` row is written.
- **On PriceLevel deletion:** one `removed` row is written, snapshotting the last known values, then the PriceLevel row is deleted.

The history write and the active-level write happen in the **same database transaction**. If the history write fails, the active-level change is rolled back. This is what guarantees the integrity of the project's central promise.

### 4.2 Immutability

History entries are write-once. No update or delete endpoint exists. They are not affected by deletion of the originating PriceLevel. They are affected by deletion of the parent Holding or Portfolio only through the cascading-delete rule in Section 11.

---

## 5. Alert engine

### 5.1 Status of a level

A `PriceLevel` is in exactly one of two operational states at any time:

- `armed` — the level is being monitored. The alert engine compares the daily closing price to the target on every evaluation.
- `touched` — the level's target has been crossed in the expected direction at least once since it was armed. The level remains visible and continues to be shown in the Alerts Panel and on the asset's detail view, but the alert engine **does not re-trigger** for already-touched levels. The user decides what to do with the touched level (typically: record a real purchase/sale, then delete the level; or edit the note; or simply observe).

There is no automatic "un-touching." Once a level is touched, the only way to bring it back to `armed` status is to delete it and create a new level (which will produce the appropriate history entries).

### 5.2 Crossing rule (close-vs-close)

The alert engine compares **the previous close** with **the latest close**:

- A **buy** level at `target_price` is `touched` when the **previous close** was strictly greater than `target_price` **AND** the **latest close** is less than or equal to `target_price`. (Crossing downward from above.)
- A **sell** level at `target_price` is `touched` when the **previous close** was strictly less than `target_price` **AND** the **latest close** is greater than or equal to `target_price`. (Crossing upward from below.)

The "previous close" is the close of the prior trading day for this asset; the "latest close" is the close of the most recent trading day. Both come from the market data layer (Spec D09). Crypto assets, which trade continuously, use the daily close in UTC as defined by the market data layer.

When a level's `created_at` is more recent than the previous-close date — i.e. the level was created today, after the previous close — the engine has no valid prior reference and **does not trigger** for that level on its first evaluation. It is evaluated normally from the following evaluation onward. This avoids false-positive triggers caused by levels that were defined "already on the wrong side of the current price" (a user defining a buy at `$175` when the asset already trades at `$170` should not see an immediate "touched" alert; the level becomes active for crossings observed from there on).

### 5.3 Direction of crossing

Per the project owner's explicit decision: a buy alert fires only on crossings **downward from above the target**, and a sell alert fires only on crossings **upward from below the target**. A mere touch from the same side (e.g. price falls toward but does not cross a buy target) does not trigger.

### 5.4 Limits of close-vs-close detection (v1)

The engine sees only daily closes. If the intraday price touches a level and rebounds within the same day, the engine does not detect the touch. This is a **knowingly accepted limitation** for v1, recorded explicitly here so it is not mistaken for an implementation gap. The data model preserves the option to add intraday detection later without restructuring the entities — the `touched_at_close_price` and `touched_at_close_date` fields can be supplemented (not replaced) with intraday equivalents in a future iteration.

### 5.5 When the engine runs

Per the project owner's decision, the alert engine runs as a hook in the **daily scheduled price-update job** (the same job that updates `scheduled_daily` indicators per Spec D05 §6.1). After the job updates the latest closing prices for an asset, it immediately re-evaluates all `armed` price levels for every holding that contains that asset. The evaluation is part of the same job execution; there is no separate alert-engine job in v1.

If the price-update job does not run on a given day (e.g. weekend, holiday, infrastructure outage), levels are simply not re-evaluated that day. There is no catch-up logic in v1; the next successful run evaluates against the latest available previous and current closes per Section 5.2.

### 5.6 Failure isolation

A failure to evaluate alerts for one asset must not stop the engine from evaluating others. Failures are logged with sufficient context (asset, level id, error) for diagnosis. This mirrors the failure-isolation rule in D05 §6.1.

---

## 6. Alerts Panel (UI integration)

The Alerts Panel screen (per the functional design) shows the consolidated list of `touched` price levels across all active holdings of the currently selected portfolio, plus the `armed` levels that are close to crossing — "close" being defined as within a configurable distance from the current price.

The configuration key is added in Section 12. The Alerts Panel sorts by:
1. `touched` levels first, most recently touched first.
2. `armed` levels close to crossing, sorted by proximity (smallest gap first).

`Armed` levels far from crossing are not shown in the Alerts Panel (they live only on the asset's detail view).

---

## 7. Historical analysis view (UI integration)

The Asset Detail screen's "Historial" tab lists all `PriceLevelHistoryEntry` rows for the holding, grouped by `originating_level_id`, sorted by `event_at` descending. For each grouped level the user sees:

- The full lifecycle of the level (created → edited → ... → touched? / removed?).
- The note at each event.
- The asset's price at the moment of each event (`asset_price_at_event`), which is what gives meaning to the historical record ("when I defined this buy at $175, the asset was at $190").

This is the screen that operationalizes the user's "que no se me olvide" requirement.

---

## 8. Define-levels flow

The "Definir niveles de precio" screen (UI Screen 7) allows the user to define one or more new levels in a single submission. The user's input is: zero or more buy levels (each with target price and optional note), and zero or more sell levels (each with target price and optional note).

On submission:
- For each level the user submitted, a new `PriceLevel` row is created with `status = armed`.
- For each new level, a corresponding `created` history entry is written. Per Section 4.1, these are written in the same transaction.
- The asset's current (latest known) price at the time of submission is captured as `asset_price_at_event` on every new history row.

There is no concept of an "analysis session" entity in v1. Each level is independent. Two levels created in the same submission share nothing structurally beyond having close `created_at` timestamps and the same `asset_price_at_event`. This decision follows directly from the project owner's choice that notes are per-level, not per session.

---

## 9. Define-levels from AI analysis (forward reference)

The AI analysis spec (D07 §9.1) provides a "Definir niveles a partir de este análisis" action. Functionally that action pre-fills the define-levels form with the asset's current price plus a structured note that includes the report's signal and a brief excerpt from the summary. The actual creation of levels still goes through the flow in Section 8 and produces the same history rows. The user is in full control of the final target prices — the LLM is **not** asked to suggest specific price targets in v1 (Spec D07 §13). For this reason, no special marker is needed on the resulting history rows in v1; the AI's contribution is the pre-filled note, not the price.

---

## 10. Authorization

A user may only see and modify price levels and history entries whose parent holding's portfolio belongs to them, per Spec 00b §5.

---

## 11. Cross-spec cascading

- When a `Holding` is deleted via the explicit "delete asset" action (Spec D03 §3.2, §6.3) — deleting a holding's last lot no longer deletes the holding automatically — all of its `PriceLevel` rows are deleted as part of the same transaction. **However, the corresponding `PriceLevelHistoryEntry` rows are preserved**, because the holding's deletion is itself a user action and the history of analysis on that asset remains a valid historical record. The history rows become "orphaned" from the holding (the holding no longer exists) but stay readable via their `holding_id` and `originating_level_id` for any future feature that may surface them.
- When a `Portfolio` is **archived** per Spec D02 §6, its price levels are preserved untouched but the alert engine does **not** evaluate them while the portfolio is `archived` (consistent with D03 archiving rules).
- When a `Portfolio` is **permanently deleted** per Spec D02 §8, all of its price levels **and all of their history entries** are deleted in the same cascade. This is the only mechanism by which history entries are removed from the database in v1.

This asymmetry — holding deletion preserves history, but portfolio deletion does not — is deliberate: a user who deletes a portfolio has signalled intent to remove all of that portfolio's data, including its analytical record; a user who simply stops holding an asset within a portfolio has not.

---

## 12. Configuration keys (added to Spec 00f)

This spec introduces the following new keys to the global configuration mechanism (Spec 00f):

| Key | Type | Default | Description |
|---|---|---|---|
| `alerts.near_crossing_pct` | NUMERIC (0–1) | `0.03` | A level is considered "close to crossing" — and therefore shown in the Alerts Panel as a pre-alert — when the gap between the current price and the target is within this fraction of the current price. Default 3%. |

Spec 00f is updated in lockstep with this spec.

---

## 13. Out of scope for v1

- **Intraday alert detection** (Section 5.4).
- **Notifications outside the app** (email, push, webhook). The visual indicator in the Dashboard badge and the Alerts Panel are the only surface in v1.
- **Trailing levels** (e.g. "alert me if the asset falls 10% from its recent high"). All v1 levels are absolute prices.
- **Conditional levels** (e.g. "alert me if price crosses X and RSI > 70"). Future indicator-based alerts are explicitly out of scope (per D05 §10).
- **An "analysis session" entity** that groups multiple levels with shared notes. Notes are per-level; sessions are not modeled.
- **Editing or deleting history entries by the user.** The history is immutable in v1.
- **Multi-currency target prices** (a buy level on AAPL must be expressed in USD, the asset's quote currency; not in EUR).
- **Importing a previously defined level "back to armed"** after it has been touched. The only way is to delete and recreate.

---

## 14. Rationale

The two-table design — active `PriceLevel` and immutable `PriceLevelHistoryEntry` — is the central architectural decision of this spec, and it directly reconciles two requirements the user had stated that, at first glance, conflict:

- *"quiero poder quitar niveles"* (active levels must be deletable) — satisfied by the hard-delete behavior on `PriceLevel`.
- *"que eso en el tiempo no se me olvide"* (analytical history must never be lost) — satisfied by writing immutable rows to `PriceLevelHistoryEntry` before every state change of a level.

The two responsibilities — feeding the alert engine vs. preserving the user's reasoning — have different operational characteristics (active levels are small, hot, queried constantly by the alert job; history entries are write-mostly, can grow large over years, read occasionally on the history screen) and are best kept apart.

Allowing multiple simultaneous buy/sell levels (Section 3.1) rather than capping at one of each — even though that was an option — was chosen because it serves the analytical pattern the user described: thinking through laddered entries and exits together, computing implied gain/loss across the whole structure at a glance. A single-target model would have forced an awkward workaround (overwriting and losing history mid-analysis) for what is naturally a multi-target activity.

Close-vs-close detection was chosen over intraday detection because the price data layer (the future Spec D09) will most likely deliver daily closes from a free data provider; building intraday detection on free-tier APIs is fragile, while the close-vs-close approach is robust, deterministic, and adequate for the project owner's stated swing-style use case. The accepted limitation (rebounds inside a day are missed) is documented in §5.4.

The decision to **not re-trigger an already-touched level** (Section 5.1) prevents a touched level from producing repeated alerts every day the asset closes on the wrong side of it, which would amount to noise rather than signal. Reverting a touched level to `armed` would require defining a hysteresis threshold and is disproportionate complexity for v1.
