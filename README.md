# ESP32 Multi Flash Manager — Website

This branch (`gh-pages`) holds the source for the project's marketing
site, published via GitHub Pages at:

**https://somangshudas.github.io/esp32-multi-flash-manager/**

It is an orphan branch with no shared history with `main` — it contains
only the static site, not the application source. The application itself
lives on [`main`](https://github.com/SomangshuDas/esp32-multi-flash-manager/tree/main).

## Structure

```
.
├── index.html            Landing page
├── 404.html               Custom not-found page
├── css/styles.css         All styles (design tokens as CSS custom properties)
├── js/main.js              Theme switching, reveal-on-scroll, mobile nav, copy button
├── assets/
│   ├── mark.svg            App icon, reused from resources/icons/app_icon.svg on main
│   ├── og-image.png        Social preview card (1200×630)
│   ├── favicon-16.png / favicon-32.png / apple-touch-icon.png
│   └── icon-192.png / icon-512.png
├── site.webmanifest        PWA/icon manifest
├── robots.txt               Crawler rules + sitemap pointer
├── sitemap.xml               Search-engine sitemap
└── LICENSE                  Same MIT license as `main`, copied verbatim
```

## Working on it locally

No build step — it's plain HTML/CSS/JS. Preview with any static file
server, e.g.:

```bash
cd gh-pages   # this directory
python3 -m http.server 8000
# open http://localhost:8000
```

Opening `index.html` directly (`file://`) also works, except the
`fetch`-free parts only — there's nothing that requires a server, so a
plain double-click is fine too.

## Design system

Colors, spacing, and type are defined as CSS custom properties at the
top of `css/styles.css`. The palette is pulled directly from the app's
own `resources/icons/app_icon.svg` and `resources/themes/{dark,light}.qss`
on `main`, so "Light" mode on the site matches the app's actual Light
theme rather than an invented palette. If those theme files change on
`main`, update the corresponding `:root` / `[data-theme="light"]` blocks
here to match.

## Deploying changes

Any push to `gh-pages` redeploys automatically — GitHub Pages is
configured to build from this branch's root. No CI step is required for
this static site.

```bash
git checkout gh-pages
# edit files
git add -A
git commit -m "describe the change"
git push origin gh-pages
```

## Keeping content in sync with `main`

Whenever features, platform-support status, or version numbers change
on `main`, check whether this page's Highlights, FAQ, Compare table, or
Quick Start commands need the same update — nothing here regenerates
automatically from `main`.
