// ==UserScript==
// @name         Suwayomi: Sort by Recently Published
// @namespace    https://github.com/TaliesinDS/MangaDex
// @version      0.1.0
// @description  Adds a client-side sort for entries based on most recent published chapter date (from source), not DB added date
// @author       You
// @match        http://*/
// @match        http://*/*
// @match        https://*/
// @match        https://*/*
// @grant        none
// @license      MIT
// ==/UserScript==

(function() {
  'use strict';

  // Configuration: adjust these selectors per Suwayomi UI version
  const SELECTORS = {
    gridItems: '[data-testid="library-grid"] .MuiGrid2-root',
    titleLink: 'a[href*="/manga/"]',
    chapterDate: '[data-testid="chapter-date"], [class*="ChapterDate"], time',
    toolbar: '[data-testid="library-toolbar"], header, .MuiToolbar-root'
  };

  function parseDate(text) {
    // Try various formats; fallback to Date.parse
    if (!text) return null;
    // Common relative strings or localized: ignore here
    const d = new Date(text);
    return isNaN(d.getTime()) ? null : d;
  }

  function extractItemInfo(el) {
    const titleEl = el.querySelector(SELECTORS.titleLink);
    const dateEl = el.querySelector(SELECTORS.chapterDate);
    const dateText = dateEl?.getAttribute('datetime') || dateEl?.textContent?.trim() || '';
    const date = parseDate(dateText);
    return {
      el,
      title: titleEl?.textContent?.trim() || '',
      date: date || new Date(0)
    };
  }

  function sortGridByPublishDate(desc = true) {
    const grid = document.querySelector(SELECTORS.gridItems)?.parentElement;
    if (!grid) return;
    const items = Array.from(document.querySelectorAll(SELECTORS.gridItems));
    const infos = items.map(extractItemInfo);
    infos.sort((a,b) => (b.date - a.date) * (desc ? 1 : -1));
    // Re-append in sorted order
    for (const info of infos) {
      grid.appendChild(info.el);
    }
  }

  function injectButton() {
    const bar = document.querySelector(SELECTORS.toolbar);
    if (!bar || bar.__suwayomiSortInjected) return;
    bar.__suwayomiSortInjected = true;

    const btn = document.createElement('button');
    btn.textContent = 'Sort: Recently Published';
    btn.style.marginLeft = '12px';
    btn.onclick = () => sortGridByPublishDate(true);
    bar.appendChild(btn);
  }

  const mo = new MutationObserver(() => {
    injectButton();
  });
  mo.observe(document.documentElement, { childList: true, subtree: true });

  // Initial
  injectButton();
})();
