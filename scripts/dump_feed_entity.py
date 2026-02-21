#!/usr/bin/env python3
"""Dump raw feed entity data to find where urn:li:share: URNs live."""
import json
import re
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from linkit.chrome_data import _find_linkedin_tab_and_exec, _wait_for_page_data


def main():
    # Force a hard reload to get fresh <code> data stores
    print("Hard-reloading /feed/ ...")
    _find_linkedin_tab_and_exec(
        "window.location.href = 'https://www.linkedin.com/feed/?_t=' + Date.now(); 'ok';"
    )
    time.sleep(6)
    _wait_for_page_data(max_wait=15.0)

    # Extract all entities from <code> stores
    js = (
        "var c=document.querySelectorAll('code[id^=\"bpr-guid-\"]');"
        "var a=[];"
        "for(var i=0;i<c.length;i++){"
        "try{var d=JSON.parse(c[i].textContent);"
        "if(d.included)for(var j=0;j<d.included.length;j++)a.push(d.included[j]);"
        "}catch(e){}}"
        "JSON.stringify({n:a.length});"
    )
    raw = _find_linkedin_tab_and_exec(js)
    count_data = json.loads(raw)
    print(f"Found {count_data['n']} entities\n")

    if count_data['n'] == 0:
        print("No entities found. Trying to dump all <code> text...")
        js2 = (
            "var c=document.querySelectorAll('code[id^=\"bpr-guid-\"]');"
            "var r=[];"
            "for(var i=0;i<Math.min(c.length,3);i++) r.push(c[i].textContent.substring(0,500));"
            "JSON.stringify(r);"
        )
        raw2 = _find_linkedin_tab_and_exec(js2)
        print(raw2[:2000])
        return

    # Get the first Update entity and search for share URNs
    # Do this in chunks to avoid AppleScript size limits
    js3 = """
    var c=document.querySelectorAll('code[id^="bpr-guid-"]');
    var all=[];
    for(var i=0;i<c.length;i++){
        try{var d=JSON.parse(c[i].textContent);
        if(d.included) for(var j=0;j<d.included.length;j++) all.push(d.included[j]);
        }catch(e){}
    }
    // Find first non-sponsored Update
    var upd=null;
    for(var i=0;i<all.length;i++){
        var t=all[i].$type||'';
        var u=all[i].entityUrn||'';
        if(t.indexOf('Update')>=0 && u.indexOf('sponsored')<0 && u.indexOf('fsd_update')>=0){
            upd=all[i]; break;
        }
    }
    if(!upd) { JSON.stringify({error:'no update found'}); }
    else {
        // Dump the update entity keys and search for share URNs
        var shareUrns=[];
        var updStr=JSON.stringify(upd);
        var re=/urn:li:share:\\d+/g;
        var m;
        while((m=re.exec(updStr))!==null) shareUrns.push(m[0]);

        // Also search ALL entities for share URNs
        var allShareUrns=[];
        for(var i=0;i<all.length;i++){
            var s=JSON.stringify(all[i]);
            var re2=/urn:li:share:\\d+/g;
            while((m=re2.exec(s))!==null){
                if(allShareUrns.indexOf(m[0])<0) allShareUrns.push(m[0]);
            }
        }

        JSON.stringify({
            urn: upd.entityUrn,
            keys: Object.keys(upd),
            shareUrnsInUpdate: shareUrns,
            allShareUrns: allShareUrns.slice(0,20),
            updateSnippet: updStr.substring(0,2000)
        });
    }
    """
    raw3 = _find_linkedin_tab_and_exec(js3.strip())
    try:
        result = json.loads(raw3)
    except json.JSONDecodeError:
        print(f"Parse error: {raw3[:500]}")
        return

    if "error" in result:
        print(f"Error: {result['error']}")
        return

    print(f"Update URN: {result['urn']}")
    print(f"Keys: {result['keys']}")
    print(f"Share URNs in this update: {result['shareUrnsInUpdate']}")
    print(f"All share URNs in feed data: {result['allShareUrns']}")
    print(f"\nUpdate snippet:\n{result['updateSnippet']}")


if __name__ == "__main__":
    main()
