BASE_URL = "https://www.linkedin.com"
VOYAGER_BASE = f"{BASE_URL}/voyager/api"

# Posts
CREATE_POST = f"{VOYAGER_BASE}/contentcreation/normShares"
COMMENT_POST = f"{VOYAGER_BASE}/voyagerSocialDashNormComments"
COMMENT_SIGNAL_QUERY_ID = "inSessionRelevanceVoyagerFeedDashClientSignal.c1c9c08097afa4e02954945e9df54091"
USER_POSTS = f"{VOYAGER_BASE}/identity/profileUpdatesV2"

# Feed
FEED_UPDATES = f"{VOYAGER_BASE}/feed/dash/feedUpdates"

# Profile
ME = f"{VOYAGER_BASE}/me"
PROFILES = f"{VOYAGER_BASE}/identity/dash/profiles"

# Search
SEARCH = f"{VOYAGER_BASE}/search/dash/clusters"

# Repost (GraphQL)
GRAPHQL = f"{VOYAGER_BASE}/graphql"
REPOST_QUERY_ID = "voyagerFeedDashReposts.a0663ae5c654123343da36617d2dbfde"
RESHARE_QUERY_ID = "voyagerContentcreationDashShares.279996efa5064c01775d5aff003d9377"

# Media
MEDIA_UPLOAD_METADATA = f"{VOYAGER_BASE}/voyagerMediaUploadMetadata"
