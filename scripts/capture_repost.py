#!/usr/bin/env python3
"""Capture the real repost payload from LinkedIn's web client.

Injects fetch + XHR interceptors into Chrome's LinkedIn tab, then waits
for you to manually click "Repost > Repost" on any post.
Captures ALL POST requests to voyager/api so we can see the real endpoint and payload.
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from linkitin.chrome_proxy import _find_linkedin_tab_and_exec


def main():
    # Intercept both fetch() and XMLHttpRequest — capture all POST to voyager/api
    inject_js = r"""
    (function() {
        window.__capturedPosts = [];

        // Intercept fetch()
        var origFetch = window.fetch;
        window.fetch = function(input, init) {
            var url = (typeof input === 'string') ? input : (input && input.url ? input.url : '');
            var method = (init && init.method) ? init.method.toUpperCase() : 'GET';
            if (method === 'POST' && url.indexOf('/voyager/api/') !== -1) {
                var body = (init && init.body) ? init.body : '';
                try { body = (typeof body === 'string') ? body : JSON.stringify(body); } catch(e) {}
                window.__capturedPosts.push({src: 'fetch', url: url, body: body});
            }
            return origFetch.apply(this, arguments);
        };

        // Intercept XHR
        var origOpen = XMLHttpRequest.prototype.open;
        var origSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.open = function(method, url) {
            this._m = method; this._u = url;
            return origOpen.apply(this, arguments);
        };
        XMLHttpRequest.prototype.send = function(body) {
            if (this._m && this._m.toUpperCase() === 'POST' && this._u && this._u.indexOf('/voyager/api/') !== -1) {
                window.__capturedPosts.push({src: 'xhr', url: this._u, body: body || ''});
            }
            return origSend.apply(this, arguments);
        };

        'interceptors installed';
    })()
    """

    print("Installing fetch + XHR interceptors in Chrome...")
    result = _find_linkedin_tab_and_exec(inject_js.strip())
    print(f"Result: {result}")

    print("\n>>> Now click 'Repost > Repost' on any LinkedIn post in Chrome.")
    print(">>> Waiting for capture (checking every 3 seconds)...\n")

    for i in range(60):
        time.sleep(3)
        check_js = "JSON.stringify(window.__capturedPosts || [])"
        raw = _find_linkedin_tab_and_exec(check_js.strip())
        try:
            captured = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if captured:
            print(f"\nCaptured {len(captured)} POST request(s):\n")
            for idx, req in enumerate(captured):
                print(f"=== Request {idx + 1} ({req.get('src', '?')}) ===")
                print(f"URL: {req['url']}")
                body = req.get("body", "")
                try:
                    parsed = json.loads(body)
                    print(f"Body:\n{json.dumps(parsed, indent=2)}")
                except (json.JSONDecodeError, TypeError):
                    print(f"Body (raw): {body[:500]}")
                print()
            return

        sys.stdout.write(f"\r  Still waiting... ({(i+1)*3}s)")
        sys.stdout.flush()

    print("\nTimeout - no POST requests captured.")


if __name__ == "__main__":
    main()
