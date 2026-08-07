# vendor/

Third-party code committed on purpose, so the app has **no external runtime
dependency** and keeps working offline.

## supabase.umd.js

| | |
|---|---|
| package | `@supabase/supabase-js` |
| version | **2.58.0** (pinned) |
| build | UMD (`dist/umd/supabase.js`) — exposes `window.supabase` |
| source | `https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.58.0/dist/umd/supabase.js` |
| size | 136,992 bytes |
| sha256 | `3ae8cfec4a4715f4e67aa45fe4e7c1a40d67787629c7f10e32afd7dd836edf4e` |

`build_app.py` inlines this file into the generated page, so the service worker
caches it along with everything else and sign-in still works with no connection
to a CDN. Nothing fetches it at runtime.

### Updating it

```bash
VER=2.58.0   # bump this
curl -fsSL "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@${VER}/dist/umd/supabase.js" \
  -o vendor/supabase.umd.js
shasum -a 256 vendor/supabase.umd.js    # record the new hash in this file
python3 build_app.py
```

Check the bundle contains no `</script` sequence after updating (`grep -ci '</script'`
should print 0); `build_app.py` escapes it defensively, but a hit is worth knowing about.
