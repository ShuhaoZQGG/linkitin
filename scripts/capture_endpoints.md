# Capturing LinkedIn Voyager API Endpoints

This guide explains how to capture the exact request format used by LinkedIn's
internal Voyager API, which is needed to verify and update the linkit library.

## Setup

1. Open Chrome and navigate to [linkedin.com](https://www.linkedin.com).
2. Make sure you are logged in.
3. Open Chrome DevTools: press **F12** (or **Cmd+Option+I** on Mac).
4. Go to the **Network** tab.
5. In the filter bar, type `voyager` to only show Voyager API requests.
6. Check the **Preserve log** checkbox so requests are not cleared on navigation.

## Capturing Endpoints

### Create Post (normShares)

1. Click the "Start a post" button on the feed.
2. Type some text content and click **Post**.
3. In the Network tab, find the request to `normShares`.
4. Click it and note:
   - **Request URL**: should match `CREATE_POST` in `endpoints.py`
   - **Request Method**: POST
   - **Request Payload**: the JSON body structure
   - **Request Headers**: especially `csrf-token`, `x-li-track`

### Feed Updates

1. Scroll through your home feed.
2. Look for requests to `feedUpdates` or `feed/dash/feedUpdates`.
3. Note the query parameters: `q`, `count`, etc.
4. Examine the response to understand the entity-reference format.

### Profile / User Posts

1. Navigate to your own profile.
2. Look for requests to `profileUpdatesV2` or `identity/profileUpdatesV2`.
3. Note the `profileUrn`, `q=memberShareFeed` parameters.

### Search

1. Use the LinkedIn search bar to search for content.
2. Look for requests to `search/dash/clusters`.
3. Note the `keywords`, `origin`, `q` parameters.
4. Filter results by CONTENT type.

### Image Upload

1. Create a post and attach an image.
2. Look for the two-step upload process:
   - First: POST to `voyagerMediaUploadMetadata?action=upload` to register the upload
   - Second: PUT to the returned upload URL (look for `singleUploadUrl` in the response) with the binary image data

## Response Format

Voyager responses use a complex entity-reference format:

```json
{
  "data": { ... },
  "included": [
    {
      "$type": "com.linkedin.voyager.feed.render.UpdateV2",
      "urn": "urn:li:activity:...",
      ...
    },
    ...
  ],
  "paging": {
    "count": 10,
    "start": 0,
    "total": 100
  }
}
```

Key points:
- Main data is often in `included[]` array
- Entities reference each other by URN
- The `$type` field indicates the entity type
- Posts appear as `UpdateV2` or `Activity` types
- Social metadata (likes, comments) may be in separate `SocialDetail` entities
- Author info is in `MiniProfile` entities

## Headers Required

Every Voyager request needs these headers:

```
csrf-token: <JSESSIONID value without quotes>
x-li-lang: en_US
x-li-track: <JSON browser fingerprint>
x-restli-protocol-version: 2.0.0
User-Agent: <realistic browser UA>
Cookie: li_at=<session>; JSESSIONID="<token>"
```
