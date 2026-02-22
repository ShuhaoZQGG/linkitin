#!/usr/bin/env python3
"""Debug script to test comment API with pre-flight calls and header variations."""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from linkitin import LinkitinClient
from linkitin.endpoints import COMMENT_POST, VOYAGER_BASE
from linkitin.chrome_proxy import _find_linkedin_tab_and_exec


def _extract_thread_urn(post_urn):
    if post_urn.startswith("urn:li:fsd_update:"):
        inner = post_urn.split("(", 1)[-1].rsplit(")", 1)[0]
        return inner.split(",")[0]
    return post_urn


async def main():
    async with LinkitinClient() as client:
        print("Logging in via Chrome proxy...")
        await client.login_from_browser()
        print("Authenticated\n")

        # Fetch a post
        print("=== Fetching Home Feed ===")
        feed = await client.get_feed(limit=5)
        post = None
        for p in feed:
            if "sponsored" not in p.urn.lower() and p.urn:
                post = p
                break
        if not post:
            print("No posts found")
            return

        author = f"{post.author.first_name} {post.author.last_name}" if post.author else "?"
        print(f"Post by {author}: {post.text[:100]}")
        thread_urn = _extract_thread_urn(post.urn)
        print(f"Thread URN: {thread_urn}\n")

        comment_text = "testing linkitin comment (will delete)"

        # Test 5: Call pre-flight endpoints first, then comment
        print("=== Test 5: Pre-flight calls then comment ===")
        try:
            # 1. Pre-submit friction check
            friction_url = (
                f"{VOYAGER_BASE}/graphql?includeWebMetadata=true&variables=()"
                "&queryId=voyagerFeedDashCommentPreSubmitFriction"
                ".b31c213182bef51fe7dd771542efa5e2"
            )
            resp1 = await client.session.get(friction_url)
            print(f"Friction check: {resp1.status_code}")

            # 2. Courtesy reminder
            from urllib.parse import quote
            courtesy_url = (
                f"{VOYAGER_BASE}/voyagerFeedDashCourtesyReminder"
                f"?q=courtesyReminder&text={quote(comment_text)}"
            )
            resp2 = await client.session.get(courtesy_url)
            print(f"Courtesy reminder: {resp2.status_code}")

            # 3. Now try the comment
            url = f"{COMMENT_POST}?decorationId=com.linkedin.voyager.dash.deco.social.NormComment-43"
            payload = {
                "commentary": {
                    "text": comment_text,
                    "attributesV2": [],
                    "$type": "com.linkedin.voyager.dash.common.text.TextViewModel",
                },
                "threadUrn": thread_urn,
            }
            resp3 = await client.session.post(url, json_data=payload)
            print(f"Comment: {resp3.status_code}")
            print(f"Response: {resp3.text[:500]}")
        except Exception as e:
            print(f"Error: {e}")

        # Test 6: Use raw JS with extra headers (x-li-track, x-li-lang)
        print("\n=== Test 6: Raw JS with extra headers ===")
        try:
            payload_json = json.dumps({
                "commentary": {
                    "text": comment_text,
                    "attributesV2": [],
                    "$type": "com.linkedin.voyager.dash.common.text.TextViewModel",
                },
                "threadUrn": thread_urn,
            })
            body_for_js = payload_json.replace("\\", "\\\\").replace("'", "\\'")
            path = "/voyager/api/voyagerSocialDashNormComments?decorationId=com.linkedin.voyager.dash.deco.social.NormComment-43"

            js = f"""
            var cookies = document.cookie.split('; ');
            var jsid = '';
            for (var i = 0; i < cookies.length; i++) {{
                if (cookies[i].startsWith('JSESSIONID=')) {{
                    jsid = cookies[i].substring(11).replace(/\\"/g, '');
                    break;
                }}
            }}
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '{path}', false);
            xhr.setRequestHeader('Accept', 'application/vnd.linkedin.normalized+json+2.1');
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('csrf-token', jsid);
            xhr.setRequestHeader('x-restli-protocol-version', '2.0.0');
            xhr.setRequestHeader('x-li-lang', 'en_US');
            xhr.setRequestHeader('x-li-page-instance', 'urn:li:page:feed_index_feed;' + Math.random().toString(36).substring(2));
            xhr.send('{body_for_js}');
            JSON.stringify({{status: xhr.status, body: xhr.responseText}});
            """
            raw = _find_linkedin_tab_and_exec(js.strip())
            result = json.loads(raw)
            print(f"Status: {result['status']}")
            print(f"Response: {result['body'][:500]}")
        except Exception as e:
            print(f"Error: {e}")

        # Test 7: Try to grab tscpUrl from LinkedIn's JS context
        print("\n=== Test 7: Look for tscpUrl generator ===")
        try:
            js_probe = """
            (function() {
                // Check for common LinkedIn global objects
                var info = {};
                info.hasClientApp = typeof window.__clientApp !== 'undefined';
                info.hasLiTrk = typeof window.__li_trk !== 'undefined';
                info.hasAppConfig = typeof window.__appConfig !== 'undefined';
                info.hasCsptUrl = typeof window.__csptUrl !== 'undefined';
                info.hasConfig = typeof window.__config !== 'undefined';

                // Look for TSCP-related globals
                var keys = Object.keys(window).filter(function(k) {
                    return k.toLowerCase().indexOf('tscp') >= 0
                        || k.toLowerCase().indexOf('csp') >= 0
                        || k.toLowerCase().indexOf('safety') >= 0;
                });
                info.tscpRelatedKeys = keys;

                return JSON.stringify(info);
            })();
            """
            raw = _find_linkedin_tab_and_exec(js_probe.strip())
            print(f"JS probe: {raw}")
        except Exception as e:
            print(f"Error: {e}")

        # Test 8: Intercept tscpUrl by monkey-patching fetch in Chrome
        print("\n=== Test 8: Intercept via fetch monkey-patch ===")
        try:
            # Set up interceptor
            setup_js = """
            window.__linkitin_last_comment_req = null;
            if (!window.__linkitin_orig_fetch) {
                window.__linkitin_orig_fetch = window.fetch;
                window.fetch = function() {
                    var url = arguments[0];
                    if (typeof url === 'string' && url.indexOf('NormComment') >= 0) {
                        var opts = arguments[1] || {};
                        window.__linkitin_last_comment_req = {
                            url: url,
                            method: opts.method,
                            body: opts.body,
                            headers: Object.fromEntries ? Object.fromEntries(new Headers(opts.headers || {})) : {}
                        };
                    }
                    return window.__linkitin_orig_fetch.apply(this, arguments);
                };
            }
            'interceptor installed';
            """
            raw = _find_linkedin_tab_and_exec(setup_js.strip())
            print(f"Interceptor: {raw}")
            print("Now manually post a comment in Chrome, then press Enter here...")
            input()

            check_js = """
            JSON.stringify(window.__linkitin_last_comment_req || 'no request captured');
            """
            raw = _find_linkedin_tab_and_exec(check_js.strip())
            print(f"Captured request: {raw[:2000]}")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
