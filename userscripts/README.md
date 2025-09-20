# Suwayomi Web UI Userscripts

This folder contains optional Greasemonkey/Tampermonkey userscripts to enhance the Suwayomi web UI locally in your browser.

## Sort by Recently Published

File: `suwayomi-sort-by-publish-date.user.js`

Adds a client-side button to sort your library grid by the most recent published chapter date (from the source), rather than the date the title was added to Suwayomi.

### How it works

- Injects a "Sort: Recently Published" button into the library toolbar
- When clicked, it parses each card for a chapter publish date element and reorders the cards in-place
- Uses `<time datetime="...">` if available, falling back to visible text

### Install

1. Install a userscript manager (e.g. Tampermonkey for Chrome/Edge, Violentmonkey for Firefox)
2. Open the raw script file in your browser and click Install: `suwayomi-sort-by-publish-date.user.js`
3. If necessary, adjust `SELECTORS` at the top of the script to match your Suwayomi UI (versions may differ)

### Notes / Limitations

- This is a client-side enhancement: it does NOT change Suwayomi's backend sorting
- If your theme or version uses different DOM structures, update `SELECTORS` accordingly
- The script looks for a publish date element inside each grid item; ensure the date is present on the card. If only visible inside the title details page, an enhancement could fetch it on demand (but that would be slower)
- Sorting is not persistent across navigations; click the button again after page changes
