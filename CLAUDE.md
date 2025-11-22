# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Edtools Core** is a Frappe App that provides custom branding and educational workflows for the Edtools Educational System. It's built on top of Frappe v15 and ERPNext, replacing "Frappe"/"ERPNext" branding with "Edtools" while maintaining the original design system.

This app is part of a larger bench environment that includes:
- Frappe v15 (framework)
- ERPNext v15 (business logic)
- Education app (educational workflows)
- edtools_core (this app - custom branding)

## Architecture

### Branding Strategy

The app uses a **text-replacement approach** rather than forking/modifying core Frappe files:
- **JavaScript (`edtools.js`)**: Runtime text replacement using MutationObserver to intercept all text nodes and replace "Frappe"/"ERPNext" → "Edtools"
- **CSS (`edtools.css`)**: Hides original branding elements and injects new text via `::before`/`::after` pseudo-elements
- **Hooks (`hooks.py`)**: Registers assets globally via `app_include_js` and `app_include_css`

This approach allows updating Frappe/ERPNext without merge conflicts.

### Socket.IO External Service Integration

**Critical component**: `socketio_override.js` intercepts Frappe's Socket.IO client initialization to redirect WebSocket connections to an external Railway-hosted Socket.IO service.

**Why**: Railway limits one public port per service, so the main web app and Socket.IO server run as separate Railway services.

**Implementation details**:
- Overrides `frappe.realtime.init()` before Frappe calls it
- Replaces `get_host()` to return external URL: `https://socketio-production-ef94.up.railway.app`
- Handles HTTPS → WSS upgrade correctly (Railway terminates SSL at edge)
- See `edtools_core/public/js/socketio_override.js:10-26`

### File Structure

```
edtools_core/
├── hooks.py                    # Frappe app hooks (asset registration, website context)
├── public/
│   ├── js/
│   │   ├── edtools.js         # Runtime text replacement logic
│   │   └── socketio_override.js  # External Socket.IO connection redirect
│   └── css/
│       └── edtools.css        # Hide/replace branding via CSS
```

## Development Commands

### Local Development (Bench)

```bash
# Navigate to bench root (typically ~/frappe-bench or similar)
cd /path/to/frappe-bench

# Install the app in development mode
bench get-app /Users/soyandresalcedo/edtools-bench/apps/edtools_core
bench --site [site-name] install-app edtools_core

# Build assets after making changes to JS/CSS
bench --site [site-name] build --app edtools_core

# Clear cache (important after changing hooks.py)
bench --site [site-name] clear-cache

# Restart bench to apply changes
bench restart
```

### Deployment (Railway - edtools-sis)

The app is deployed as part of the `edtools-sis` repository which uses git submodules:

```bash
# In edtools-sis repo, update the edtools_core submodule
cd /path/to/edtools-sis
git submodule update --remote apps/edtools_core
git add apps/edtools_core
git commit -m "Update edtools_core submodule"
git push origin main
```

Railway auto-deploys on push to `main`. The `docker-entrypoint.sh` runs `bench build` during container startup.

### Making Changes to Branding

**Text replacements**: Edit `edtools_core/public/js/edtools.js` → Update `replacements` object (line 14-24)

**CSS overrides**: Edit `edtools_core/public/css/edtools.css`

**After changes**:
```bash
# Local: rebuild assets
bench build --app edtools_core --force

# Production: Push changes → update submodule → Railway auto-deploys
```

### Socket.IO Service Changes

If modifying `socketio_override.js`:

1. Test locally first (Socket.IO won't work locally without external service, but check for JS errors)
2. Commit to `edtools_core` repo
3. Update submodule in `edtools-sis`
4. Railway will rebuild and serve new bundled assets

**Common issues**:
- Browser cache: Use hard refresh (`Cmd+Shift+R`) or incognito mode
- Bundle not updated: Check Railway logs for `bench build` output
- 502 errors: Check Socket.IO service is running in Railway

## Key Configuration Files

### hooks.py

Critical sections:
- `app_include_js` (line 15-18): Loads edtools.js and socketio_override.js on every page
- `website_context` (line 207-211): Sets site-wide branding
- `brand_html` (line 215): Application name override

### Deployment Architecture

**Repository**: `soyandresalcedo/edtools_core` (this repo)
**Production**: Part of `soyandresalcedo/edtools-sis` via git submodule
**Platform**: Railway (containerized Frappe v15)

**Services**:
- `web`: Main Gunicorn app (port 8080)
- `socketio`: Separate Node.js Socket.IO server (port 9000)
- `redis`: Shared Redis for both services
- `postgres`: PostgreSQL database

The Socket.IO override is **required** for the split-service architecture to work.

## Testing

No automated tests currently. Manual testing checklist:

1. Login page shows "Edtools" branding
2. Desk shows "Edtools" in navbar/page titles
3. No "Frappe"/"ERPNext" text visible anywhere
4. Socket.IO connects without errors (check browser console)
5. Real-time features work (progress bars, notifications)

## Common Pitfalls

1. **Forgetting to rebuild assets**: JS/CSS changes won't appear until `bench build` runs
2. **Browser cache**: Production changes may not appear due to aggressive CDN/browser caching
3. **Submodule not updated**: Pushing to edtools_core alone won't deploy - must update edtools-sis submodule
4. **Socket.IO URL hardcoded**: If Railway Socket.IO service URL changes, update `socketio_override.js:15`
