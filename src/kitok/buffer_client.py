"""Small synchronous client for the documented Buffer GraphQL API.

Reads can retry. createPost is sent once, including on rate limiting; its caller
persists the outcome and any cooldown before another maintenance invocation.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

ENDPOINT = "https://api.buffer.com"
PLATFORMS = ("tiktok", "instagram", "youtube")
POST_STATUSES = {"draft", "error", "needs_approval", "scheduled", "sending", "sent"}
ORGANIZATIONS = """query KitokOrganizations {
  account { organizations { id name } }
}"""
CHANNELS = """query KitokChannels($input: ChannelsInput!) {
  channels(input: $input) {
    id name service isDisconnected isLocked isQueuePaused
  }
}"""
POSTS = """query KitokPosts($input: PostsInput!, $after: String) {
  posts(input: $input, first: 100, after: $after) {
    edges { node { id channelId text dueAt status } }
    pageInfo { hasNextPage endCursor }
  }
}"""
POST = """query KitokPost($input: PostInput!) {
  post(input: $input) { id channelId text dueAt status }
}"""
CREATE_POST = """mutation KitokCreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on PostActionSuccess {
      post { id channelId text dueAt status }
    }
    ... on MutationError { message }
  }
}"""


class BufferError(RuntimeError):
    def __init__(self, message, *, ambiguous=False, post=None, retry_after=0):
        super().__init__(message)
        self.ambiguous = ambiguous
        self.post = post
        self.retry_after = retry_after


class BufferMutationError(BufferError):
    pass


def select_channels(organizations, channels, organization_id="", explicit=None):
    """Never guess among multiple organizations or matching service channels."""
    org_ids = {o["id"] for o in organizations}
    if organization_id:
        if organization_id not in org_ids:
            raise BufferError("BUFFER_ORGANIZATION_ID is not accessible to this account")
    elif len(org_ids) == 1:
        organization_id = next(iter(org_ids))
    else:
        raise BufferError("Set BUFFER_ORGANIZATION_ID: expected exactly one organization")
    selected = {}
    for platform in PLATFORMS:
        matches = [c for c in channels if c["service"] == platform]
        chosen = (explicit or {}).get(platform)
        if chosen:
            matches = [c for c in matches if c["id"] == chosen]
            if not matches:
                raise BufferError(f"BUFFER_{platform.upper()}_CHANNEL_ID does not match this organization's service")
        if len(matches) > 1:
            raise BufferError(f"Multiple {platform} channels; set BUFFER_{platform.upper()}_CHANNEL_ID")
        if matches:
            selected[platform] = matches[0]
    return organization_id, selected


class BufferClient:
    def __init__(self, api_key, *, publish_enabled=False, timeout=30,
                 attempts=3, backoff=1.5, transport=None, sleep=time.sleep):
        if not api_key:
            raise BufferError("BUFFER_API_KEY is not configured")
        self._key = api_key
        self.publish_enabled = publish_enabled
        self.attempts, self.backoff, self.sleep = attempts, backoff, sleep
        self.client = httpx.Client(headers={"Authorization": f"Bearer {api_key}"},
                                   timeout=timeout, transport=transport)

    def close(self):
        self.client.close()

    def _safe(self, message):
        return str(message).replace(self._key, "[REDACTED]")[:500]

    def _retry_after(self, response):
        value = response.headers.get("Retry-After", "")
        try:
            return max(1.0, float(value))
        except ValueError:
            try:
                return max(1.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError):
                return 60.0

    def _execute(self, query, variables=None, *, mutation=False):
        if mutation and not self.publish_enabled:
            raise BufferError("Publishing disabled: set PUBLISH_ENABLED=true")
        for attempt in range(1 if mutation else self.attempts):
            try:
                response = self.client.post(ENDPOINT, json={"query": query, "variables": variables or {}})
            except httpx.HTTPError:
                if not mutation and attempt + 1 < self.attempts:
                    self.sleep(min(30, self.backoff * 2**attempt))
                    continue
                raise BufferError("Buffer network request failed; reconcile before retrying creation",
                                  ambiguous=mutation) from None
            if response.status_code == 429:
                delay = self._retry_after(response)
                if not mutation and delay <= 30 and attempt + 1 < self.attempts:
                    self.sleep(max(delay, min(30, self.backoff * 2**attempt)))
                    continue
                raise BufferError("Buffer rate limited; retry after cooldown", retry_after=delay)
            if response.status_code >= 500:
                if not mutation and attempt + 1 < self.attempts:
                    self.sleep(min(30, self.backoff * 2**attempt))
                    continue
                raise BufferError(f"Buffer HTTP {response.status_code}", ambiguous=mutation)
            if not response.is_success:
                raise BufferError(f"Buffer HTTP {response.status_code}",
                                  ambiguous=mutation and response.status_code not in {400, 401, 403, 404})
            try:
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError
            except ValueError:
                raise BufferError("Buffer returned invalid JSON", ambiguous=mutation) from None
            data = payload.get("data") or {}
            result = (data.get("createPost") or {}) if isinstance(data, dict) else {}
            if not isinstance(result, dict):
                result = {}
            if payload.get("errors"):
                errors = payload["errors"]
                codes = {str(e.get("extensions", {}).get("code", "")) for e in errors}
                limited = bool(codes & {"RATE_LIMITED", "RATE_LIMIT_EXCEEDED", "TOO_MANY_REQUESTS"})
                delay = self._retry_after(response) if limited else 0
                if limited and not mutation and delay <= 30 and attempt + 1 < self.attempts:
                    self.sleep(max(delay, min(30, self.backoff * 2**attempt)))
                    continue
                # Execution errors may follow a committed mutation. Preserve any ID.
                definite = codes and codes <= {"GRAPHQL_VALIDATION_FAILED", "GRAPHQL_PARSE_FAILED", "BAD_USER_INPUT", "UNAUTHENTICATED", "FORBIDDEN"}
                raise BufferError("Buffer GraphQL errors: " + self._safe("; ".join(e.get("message", "GraphQL error") for e in errors)),
                                  ambiguous=mutation and not definite,
                                  post=result.get("post"), retry_after=delay)
            if not isinstance(data, dict) or not data:
                raise BufferError("Buffer response has no data", ambiguous=mutation)
            return data
        raise BufferError("Buffer read retries exhausted")

    def organizations(self):
        return self._execute(ORGANIZATIONS)["account"]["organizations"]

    def channels(self, organization_id):
        return self._execute(CHANNELS, {"input": {"organizationId": organization_id}})["channels"]

    def discover(self, organization_id="", explicit=None):
        organizations = self.organizations()
        org_id, _ = select_channels(organizations, [], organization_id)
        channels = self.channels(org_id)
        _, selected = select_channels(organizations, channels, org_id, explicit)
        return org_id, channels, selected

    def posts(self, organization_id, channel_ids, statuses=None, due_at=None):
        filters = {"channelIds": list(channel_ids)}
        if statuses is not None:
            filters["status"] = list(statuses)
        if due_at is not None:
            filters["dueAt"] = due_at
        variables = {"input": {"organizationId": organization_id, "filter": filters,
                               "sort": [{"field": "dueAt", "direction": "asc"}]}, "after": None}
        posts, cursors = {}, set()
        while True:
            page = self._execute(POSTS, variables)["posts"]
            for edge in page["edges"]:
                node = edge["node"]
                posts[node["id"]] = node
            if not page["pageInfo"]["hasNextPage"]:
                return list(posts.values())
            cursor = page["pageInfo"]["endCursor"]
            if not cursor or cursor in cursors:
                raise BufferError("Buffer returned invalid pagination; queue capacity is unknown")
            cursors.add(cursor)
            variables["after"] = cursor

    def post(self, post_id):
        return self._execute(POST, {"input": {"id": post_id}})["post"]

    def create_post(self, inputs):
        result = self._execute(CREATE_POST, {"input": inputs}, mutation=True).get("createPost")
        if not isinstance(result, dict):
            raise BufferError("Buffer creation result missing", ambiguous=True)
        if result.get("__typename") != "PostActionSuccess":
            if "message" in result:
                # The typed MutationError branch proves creation failed.
                raise BufferMutationError(self._safe(result["message"]),
                                          retry_after=60 if "rate" in result["message"].lower() else 0)
            raise BufferError("Unrecognized Buffer creation result", ambiguous=True)
        post = result.get("post") or {}
        if not post.get("id"):
            raise BufferError("Buffer creation returned no post ID", ambiguous=True)
        return post
