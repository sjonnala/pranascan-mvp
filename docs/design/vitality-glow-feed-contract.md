# Vitality Glow Feed Contract

## Purpose

The current Circle experience is assembled from three unrelated resources:

- `GET /api/v1/social/connections`
- `GET /api/v1/business/vitality-streak`
- `GET /api/v1/scans/sessions/history`

That is enough to resemble the Stitch prototype, but not enough to behave like
it. The missing piece is a first-class social feed contract owned by
`service-core`.

This document defines the backend contract needed for the full Vitality Glow
feed:

- real timeline items
- explicit scan-share posts
- system-generated milestone items
- reactions
- comments
- circle summary data
- user preferences and discovery hooks

## Current Baseline

As of April 5, 2026, `service-core` already owns:

- social connections at `/api/v1/social/connections`
- vitality streaks at `/api/v1/business/vitality-streak`
- scan history and completed scan results

What does not exist yet:

- a feed timeline resource
- a share-a-scan post resource
- feed reactions
- feed comments
- unread activity counts
- discovery/search for new circle members
- social privacy/preferences specific to feed sharing

## Ownership

`service-core` must own this contract end-to-end.

Reasons:

- the feed is user-facing product state
- it depends on auth, privacy policy, and connection graph checks
- it should fan out from persisted scan results and streak records already owned by `service-core`
- `service-intelligence` should not become a product-facing social API

`service-intelligence` remains unchanged for this feature. It only continues to
produce completed scan outputs that may later be shared by `service-core`.

## Product Behaviors This Contract Must Unlock

The backend contract must support all of the following:

1. A user can explicitly share a completed scan into their circle feed.
2. The feed can show system-generated streak and connection milestones.
3. Accepted connections can react to a post and comment on it.
4. The mobile app can render a rich feed card without joining multiple APIs.
5. The backend can enforce privacy and audience rules centrally.
6. The feed remains immutable enough for social history even if source metrics
   are later recalculated.

## Privacy And Wellness Constraints

The feed contract must preserve the same guardrails as the rest of PranaPulse:

- no diagnostic terminology
- no raw video, raw audio, raw frame traces, or raw waveform data
- no public/global feed; audience is limited to the current user plus accepted
  connections
- scan shares are opt-in, not automatic by default
- a scan share stores an immutable snapshot of the shareable content at the time
  of posting
- exact wellness indicator values are only included when the author chooses to
  share them

## Primary Resources

### `SocialCircleSummary`

Returned to power the Circle hero area and summary chips.

```json
{
  "activeConnectionCount": 4,
  "pendingInviteCount": 1,
  "unreadFeedCount": 3,
  "latestActivityAt": "2026-04-05T18:22:09Z",
  "membersPreview": [
    {
      "id": "9d0e8f4f-3f61-43b6-b7eb-c4f2ce4f7fa1",
      "displayName": "Aarav",
      "avatarUrl": null,
      "lastActivityAt": "2026-04-05T18:22:09Z"
    }
  ]
}
```

### `SocialFeedPost`

Canonical feed item returned by timeline APIs.

```json
{
  "id": "f7c13d9b-8c6f-4c7f-8f1d-f61a9b53b5f8",
  "postType": "scan_share",
  "audience": "connections",
  "author": {
    "id": "1a4c3b1a-77f4-4d15-b3aa-b36df65d1b54",
    "displayName": "Satish",
    "avatarUrl": null
  },
  "source": {
    "sessionId": "8bbd9d08-fdd0-4f6e-a955-b6908f08b2cf",
    "scanType": "standard",
    "sharedAt": "2026-04-05T18:22:09Z"
  },
  "display": {
    "tone": "sage",
    "headline": "Shared a Daily Glow check-in",
    "body": "Recovery rhythm felt steadier than the previous window.",
    "sharedMetrics": [
      { "key": "hrBpm", "label": "HR", "value": "72", "unit": "bpm" },
      { "key": "hrvMs", "label": "HRV", "value": "45", "unit": "ms" }
    ]
  },
  "reactionSummary": [
    { "reactionType": "acknowledge", "count": 2, "reactedByViewer": true },
    { "reactionType": "celebrate", "count": 1, "reactedByViewer": false }
  ],
  "commentCount": 3,
  "latestComments": [
    {
      "id": "5359d0e0-96bc-4418-aa68-cf418a2a27ea",
      "author": {
        "id": "9d0e8f4f-3f61-43b6-b7eb-c4f2ce4f7fa1",
        "displayName": "Aarav",
        "avatarUrl": null
      },
      "text": "Looking steady today.",
      "createdAt": "2026-04-05T18:25:11Z",
      "updatedAt": "2026-04-05T18:25:11Z"
    }
  ],
  "viewerState": {
    "canReact": true,
    "canComment": true,
    "canDelete": true,
    "canEdit": false
  },
  "createdAt": "2026-04-05T18:22:09Z",
  "updatedAt": "2026-04-05T18:25:11Z"
}
```

### Supported `postType` Values

- `scan_share`
- `streak_milestone`
- `connection_joined`
- `reflection_note`

### Supported `audience` Values

- `connections`
- `selected_connections`
- `private`

### Supported `reactionType` Values

- `acknowledge`
- `celebrate`
- `support`

## REST Endpoints

### Keep Existing Endpoints

These stay as-is and remain part of the social contract:

- `GET /api/v1/social/connections`
- `POST /api/v1/social/connections`
- `POST /api/v1/social/connections/{connectionId}/accept`
- `POST /api/v1/social/connections/{connectionId}/decline`

### New Endpoints Required

#### `GET /api/v1/social/circle/summary`

Returns a stitched summary for Circle hero/header rendering.

Query params:

- none

Response:

- `SocialCircleSummary`

#### `GET /api/v1/social/feed`

Returns the main Vitality Glow timeline.

Query params:

- `cursor` optional opaque pagination cursor
- `limit` optional, default `20`, max `50`
- `scope` optional: `all`, `connections`, `self`
- `postType` optional repeated filter

Response:

```json
{
  "items": [],
  "nextCursor": "eyJjcmVhdGVkQXQiOiIyMDI2LTA0LTA1VDE4OjIyOjA5WiIsImlkIjoiLi4uIn0=",
  "hasMore": true
}
```

Ordering:

- reverse chronological by `createdAt`
- stable tiebreaker by `id`

#### `GET /api/v1/social/feed/{postId}`

Returns one fully expanded feed post.

#### `POST /api/v1/social/feed/posts`

Creates a user-authored post.

This must support two v1 creation paths:

1. explicit scan share from Results
2. manual reflection note

Request:

```json
{
  "postType": "scan_share",
  "audience": "connections",
  "sessionId": "8bbd9d08-fdd0-4f6e-a955-b6908f08b2cf",
  "text": "Felt calmer after this scan.",
  "shareMode": "selected_metrics",
  "sharedMetricKeys": ["hrBpm", "hrvMs"]
}
```

Rules:

- `sessionId` is required for `scan_share`
- `sessionId` must belong to the authenticated user
- the source session must be `completed`
- `sharedMetricKeys` must be valid for the source scan type
- `selected_connections` requires `targetConnectionIds`

#### `DELETE /api/v1/social/feed/{postId}`

Soft-deletes a user-owned post.

Rules:

- only the author may delete
- backend should retain a tombstone or `deletedAt` for moderation/audit safety

#### `POST /api/v1/social/feed/{postId}/reactions`

Upserts the viewer's reaction for a post.

Request:

```json
{
  "reactionType": "acknowledge"
}
```

Rules:

- exactly one active reaction per user per post in v1
- posting a new reaction replaces the previous one

#### `DELETE /api/v1/social/feed/{postId}/reactions/mine`

Removes the viewer's current reaction from a post.

#### `GET /api/v1/social/feed/{postId}/comments`

Returns paginated comments for a post.

Query params:

- `cursor` optional
- `limit` optional, default `20`, max `50`

Response:

```json
{
  "items": [],
  "nextCursor": null,
  "hasMore": false
}
```

#### `POST /api/v1/social/feed/{postId}/comments`

Creates a top-level comment.

Request:

```json
{
  "text": "Looking steady today."
}
```

Rules:

- top-level comments only in v1
- maximum length should be `280`

#### `PATCH /api/v1/social/feed/comments/{commentId}`

Allows comment editing by the comment author.

Request:

```json
{
  "text": "Looking steady today. Nice rhythm."
}
```

#### `DELETE /api/v1/social/feed/comments/{commentId}`

Soft-deletes a user-owned comment.

#### `GET /api/v1/social/discovery/users`

Required to power "Add to circle" from the prototype.

Query params:

- `q` required search string
- `limit` optional, default `10`, max `20`

Response item:

```json
{
  "id": "d6e86eb3-8314-4f25-8c64-ef2e6a7e4b2b",
  "displayName": "Priya",
  "avatarUrl": null,
  "connectionStatus": null
}
```

#### `GET /api/v1/social/preferences`

Returns viewer feed/privacy settings.

#### `PUT /api/v1/social/preferences`

Updates viewer feed/privacy settings.

Request:

```json
{
  "defaultShareAudience": "private",
  "defaultShareMode": "summary_only",
  "allowComments": true,
  "allowReactions": true,
  "autoShareMilestones": false
}
```

## Server-Side Behavior Rules

### 1. Feed Visibility

A viewer can see:

- their own posts
- posts authored by users with an `ACCEPTED` social connection

A viewer cannot see:

- posts from `PENDING` or `DECLINED` users
- posts with `selected_connections` audience unless they are explicitly listed

### 2. Scan Share Snapshotting

`scan_share` posts must snapshot the share payload at creation time.

That snapshot should include:

- `scanType`
- `qualityScore`
- optional `sharedMetrics`
- server-generated `headline` and `body`
- author-authored optional caption text

It must not resolve live against the current scan result on every feed read.

### 3. Milestone Generation

The backend may create system-generated posts for:

- `streak_milestone`
- `connection_joined`

Those posts should still use the same `SocialFeedPost` response shape.

### 4. Unread Tracking

Unread count is required for Circle summary.

Minimum contract:

- the backend tracks per-user last-seen feed position
- `GET /api/v1/social/circle/summary` returns `unreadFeedCount`

If a dedicated read marker endpoint is preferred, use:

- `POST /api/v1/social/feed/read-marker`

Request:

```json
{
  "lastSeenPostId": "f7c13d9b-8c6f-4c7f-8f1d-f61a9b53b5f8"
}
```

### 5. Validation Limits

Recommended v1 limits:

- post text max length: `500`
- comment text max length: `280`
- `selected_connections` target count max: `10`
- `limit` max for feed/comments: `50`

## Persistence Expectations

The contract does not require a specific schema layout, but the backend will be
much easier to implement and page efficiently if `service-core` adds at least
these tables:

- `social_feed_posts`
- `social_feed_post_reactions`
- `social_feed_post_comments`
- `social_feed_preferences`
- `social_feed_read_markers`

Recommended `social_feed_posts` columns:

- `id`
- `author_user_id`
- `post_type`
- `audience`
- `source_session_id` nullable
- `source_connection_id` nullable
- `text`
- `display_headline`
- `display_body`
- `display_tone`
- `shared_metrics_json`
- `target_connection_ids_json` nullable
- `created_at`
- `updated_at`
- `deleted_at` nullable

Recommended indexes:

- `(author_user_id, created_at desc)`
- `(created_at desc, id desc)`
- reaction uniqueness on `(post_id, user_id)`
- comment lookup on `(post_id, created_at asc)`

## Mobile Mapping

The contract above maps directly to the current and planned mobile UI:

- Circle header:
  - `GET /api/v1/social/circle/summary`
  - `GET /api/v1/social/connections`
- Feed list:
  - `GET /api/v1/social/feed`
- Share from Results:
  - `POST /api/v1/social/feed/posts`
- Acknowledge / Celebrate / Support:
  - `POST /api/v1/social/feed/{postId}/reactions`
  - `DELETE /api/v1/social/feed/{postId}/reactions/mine`
- Comment drawer / detail sheet:
  - `GET /api/v1/social/feed/{postId}/comments`
  - `POST /api/v1/social/feed/{postId}/comments`
- Add to circle search:
  - `GET /api/v1/social/discovery/users`

## Out Of Scope For V1

These are reasonable extensions later, but should not block the first
production-grade Vitality Glow feed:

- nested comments
- push-notification delivery preferences
- user blocking/reporting workflows
- media attachments
- public profiles
- non-connection group feeds
- algorithmic ranking beyond reverse-chronological ordering

## Recommended Delivery Order

1. `GET /social/circle/summary`
2. `GET /social/feed`
3. `POST /social/feed/posts` for `scan_share`
4. reactions
5. comments
6. discovery + preferences

That order gives mobile a real Circle timeline quickly while keeping the API
surface incremental.
