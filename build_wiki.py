"""Generate the static-HTML TOEO Asset Wiki from extracted data.

Reads from `Yu-TOEOE/assets/`:
    runs/2026-05-01_cid0.json   — enemy/NPC/monster ID dictionary
    runs/2026-05-01_cid1.json   — equipment ID dictionary
    runs/2026-05-01_tdab.json   — battle action database
    extracted/icons/<cat>/*.png — per-category icon PNGs

Writes to `Yu-TOEOE/wiki/`:
    index.html
    equipment/index.html  +  equipment/<category>.html
    beasts/index.html
    npcs/index.html
    actions/index.html
    about.html
    static/icons/<cat>/*.png   (copied from assets/extracted/icons)

No JS framework, minimal client-side JS for search/filter.
"""
from __future__ import annotations

import html
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
ASSETS = ROOT.parent / "assets"
ICONS_SRC = ASSETS / "extracted" / "icons"
ICONS_DST = ROOT / "static" / "icons"
EXTRACTED_SRC = ASSETS / "extracted"          # contains per-bundle PNG dirs
SPRITES_DST = ROOT / "static" / "sprites"     # NPC + monster sprite atlases
EQUIP_DST = ROOT / "static" / "equipment"     # equipment atlas thumbnails

CID0_PATH = ASSETS / "runs" / "2026-05-01_cid0.json"
CID1_PATH = ASSETS / "runs" / "2026-05-01_cid1.json"
TDAB_PATH = ASSETS / "runs" / "2026-05-01_tdab.json"
CRSD_PATH = ASSETS / "runs" / "2026-05-07_crsd.json"
NNTB_PATH = ASSETS / "runs" / "2026-05-07_nntb.json"
ZONES_PATH = ASSETS / "runs" / "2026-05-07_zones.json"


# ---------- Layout helpers ---------------------------------------------------

NAV_LINKS = [
    ("/index.html", "Home"),
    ("/equipment/index.html", "Equipment"),
    ("/beasts/index.html", "Beasts"),
    ("/npcs/index.html", "NPCs"),
    ("/actions/index.html", "Battle Actions"),
    ("/zones/index.html", "Zones"),
    ("/audio/index.html", "Audio"),
    ("/bundles/index.html", "Bundles"),
    ("/about.html", "About"),
]

NAV_GROUPS = [
    ("Archive", NAV_LINKS[:1]),
    ("Catalogs", NAV_LINKS[1:5]),
    ("Preservation", NAV_LINKS[5:8]),
    ("Project", NAV_LINKS[8:]),
]


def page(title: str, body: str, active: str = "", *, depth: int = 0) -> str:
    """Wrap body content in the top-nav page layout."""
    rel = "../" * depth
    nav_html = []
    side_groups = []
    for href, label in NAV_LINKS:
        cls = "active" if href == active else ""
        link = rel.rstrip("/") + href if rel else "." + href
        nav_html.append(
            f'<a class="{cls}" href="{link}">{html.escape(label)}</a>'
        )
    nav_block = "\n      ".join(nav_html)
    for group, links in NAV_GROUPS:
        items = []
        for href, label in links:
            cls = "active" if href == active else ""
            link = rel.rstrip("/") + href if rel else "." + href
            items.append(
                f'<a class="{cls}" href="{link}" data-palette-item="{html.escape(label)}" '
                f'data-search="{html.escape(label)} archive section">{html.escape(label)}</a>'
            )
        side_groups.append(
            f"""<details class="side-group" open>
        <summary>{html.escape(group)}</summary>
        <div class="side-links">
          {"".join(items)}
        </div>
      </details>"""
        )
    sidebar = "\n      ".join(side_groups)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · TOEO Asset Wiki</title>
<link rel="stylesheet" href="{rel}static/style.css">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700&family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
</head>
<body>
<header class="top-nav">
  <a class="brand" href="{rel}index.html" aria-label="Tales of Eternia Online archive home">
    <img class="brand-logo" src="{rel}static/toeo-logo.webp" alt="Tales of Eternia Online" width="178" height="50">
  </a>
  <nav class="nav-links">
      {nav_block}
  </nav>
  <div class="search-wrap">
    <button class="search-top" type="button" onclick="openPalette()" aria-label="Open search">
      <span>Search archive</span><kbd>Ctrl K</kbd>
    </button>
  </div>
</header>
<div class="site-shell">
  <aside class="sidebar">
    <div class="sidebar-card">
      <div class="sidebar-kicker">Recovered client index</div>
      {sidebar}
    </div>
  </aside>
  <main class="main">
    <div class="breadcrumb"><a href="{rel}index.html">Archive</a><span>/</span><span>{html.escape(title)}</span></div>
{body}
    <footer class="site">
      <p>Reverse-engineered asset archive of <em>Tales of Eternia Online</em> (Namco / Sigma, 2003-2007). Static structural data extracted from the recovered client; no copyrighted asset binaries are redistributed here. Numeric gameplay values (HP, levels, drops, XP) have not been confirmed in the recovered client corpus and were likely server-authoritative.</p>
      <p class="small muted">Generated by <code>build_wiki.py</code> · 7 container formats decoded: BNKD · IDTB · ICND · TDAB · CRSD · NNTB · ATDT/PKDF/CPDT</p>
    </footer>
  </main>
</div>
<div class="palette-backdrop" id="paletteBackdrop" hidden onclick="closePalette()"></div>
<section class="command-palette" id="commandPalette" hidden aria-label="Archive search">
  <div class="palette-panel">
    <div class="palette-field">
      <span class="palette-icon">⌕</span>
      <input id="paletteInput" type="search" placeholder="Search current page and archive sections..." autocomplete="off" oninput="paletteSearch(this.value)">
      <button type="button" onclick="closePalette()" aria-label="Close search">Esc</button>
    </div>
    <div class="palette-results" id="paletteResults"></div>
  </div>
</section>
<div class="image-viewer" id="imageViewer" hidden onclick="closeImageViewer()">
  <figure class="image-viewer-panel" onclick="event.stopPropagation()">
    <button class="image-viewer-close" type="button" onclick="closeImageViewer()" aria-label="Close image preview">Esc</button>
    <img id="imageViewerImg" alt="">
    <figcaption id="imageViewerCaption"></figcaption>
  </figure>
</div>
<script>
const archiveLinks = {json.dumps([{"href": (rel.rstrip("/") + href if rel else "." + href), "label": label} for href, label in NAV_LINKS])};

function globalSearch(q) {{
  q = q.trim().toLowerCase();
  const targets = document.querySelectorAll('[data-search], [data-name], [data-id]');
  for (const t of targets) {{
    const haystack = (t.dataset.search || t.dataset.name || '' + (t.dataset.id || '') || t.textContent || '').toLowerCase();
    t.style.display = (!q || haystack.includes(q)) ? '' : 'none';
  }}
}}

function openPalette() {{
  document.getElementById('paletteBackdrop').hidden = false;
  document.getElementById('commandPalette').hidden = false;
  const input = document.getElementById('paletteInput');
  input.value = '';
  paletteSearch('');
  input.focus();
}}

function closePalette() {{
  document.getElementById('paletteBackdrop').hidden = true;
  document.getElementById('commandPalette').hidden = true;
}}

function paletteSearch(q) {{
  q = q.trim().toLowerCase();
  globalSearch(q);
  const pageItems = Array.from(document.querySelectorAll('.cat-card, .npc-card, .icon-cell, .action-card, .zone-card, .audio-cell'))
    .map((el) => {{
      const title = (el.querySelector('.name, .npc-name, .id, .zone-id, .a-name') || el).textContent.trim();
      const meta = (el.querySelector('.meta, .npc-id, .zone-group, .a-sub') || {{ textContent: '' }}).textContent.trim();
      const text = (el.dataset.search || el.dataset.name || el.textContent || '').trim();
      return {{ title, meta, text }};
    }})
    .filter((item) => !q || item.text.toLowerCase().includes(q))
    .slice(0, 6);
  const linkItems = archiveLinks
    .filter((item) => !q || item.label.toLowerCase().includes(q))
    .map((item) => `<a class="palette-result" href="${{item.href}}"><span>${{item.label}}</span><small>Archive section</small></a>`);
  const localItems = pageItems
    .map((item) => `<button class="palette-result" type="button" onclick="closePalette()"><span>${{item.title}}</span><small>${{item.meta || 'Current page match'}}</small></button>`);
  document.getElementById('paletteResults').innerHTML = [...linkItems, ...localItems].join('') || '<div class="palette-empty">No matches in this page.</div>';
}}

function openImageViewer(img) {{
  const viewer = document.getElementById('imageViewer');
  const viewerImg = document.getElementById('imageViewerImg');
  const caption = document.getElementById('imageViewerCaption');
  const cell = img.closest('.icon-cell, .npc-card');
  const label = cell ? (cell.querySelector('.name, .npc-name, .id') || cell).textContent.trim() : (img.alt || 'Asset preview');
  const source = cell ? cell.querySelector('.asset-source')?.textContent.trim() : '';
  viewerImg.src = img.currentSrc || img.src;
  viewerImg.alt = img.alt || label;
  caption.textContent = source ? `${{label}} · ${{source}}` : label;
  viewer.hidden = false;
  document.body.classList.add('viewer-open');
}}

function closeImageViewer() {{
  const viewer = document.getElementById('imageViewer');
  const viewerImg = document.getElementById('imageViewerImg');
  viewer.hidden = true;
  viewerImg.removeAttribute('src');
  document.body.classList.remove('viewer-open');
}}

document.addEventListener('click', (ev) => {{
  const img = ev.target.closest('.icon-cell img, .npc-card img');
  if (!img || !img.getAttribute('src')) return;
  ev.preventDefault();
  openImageViewer(img);
}});

document.addEventListener('keydown', (ev) => {{
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'k') {{
    ev.preventDefault();
    openPalette();
  }}
  if (ev.key === 'Escape') {{
    closePalette();
    closeImageViewer();
  }}
}});
</script>
</body>
</html>"""


# ---------- Data loading -----------------------------------------------------

def load_data():
    cid0 = {int(k): v for k, v in json.load(open(CID0_PATH)).items()}
    cid1 = {int(k): v for k, v in json.load(open(CID1_PATH)).items()}
    tdab = json.load(open(TDAB_PATH))
    crsd = json.load(open(CRSD_PATH)) if CRSD_PATH.exists() else None
    nntb = json.load(open(NNTB_PATH)) if NNTB_PATH.exists() else None
    zones = json.load(open(ZONES_PATH)) if ZONES_PATH.exists() else None
    return cid0, cid1, tdab, crsd, nntb, zones


def write_html(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def category_for_cid1_id(name: str) -> str:
    """Bucket cid1 names into wiki category groups."""
    if name.startswith("ID_SWORD"): return "Sword"
    if name.startswith("ID_HAT"): return "Hat"
    if name.startswith("ID_SHIELD"): return "Shield"
    if name.startswith("ID_BODY_A"): return "Body A-set"
    if name.startswith("ID_BODY_B"): return "Body B-set"
    if name.startswith("ID_BODY_C"): return "Body C-set"
    if name.startswith("ID_BODY_D"): return "Body D-set"
    if name.startswith("ID_BODY_E"): return "Body E-set"
    if name.startswith("ID_BODY_F"): return "Body F-set"
    if name.startswith("ID_BODY_G"): return "Body G-set"
    if name.startswith("ID_BODY_M_U") or name.startswith("ID_BODY_L_U"): return "Body undergarment"
    if name.startswith("ID_LEATHER_CLOTHES"): return "Clothes"
    if name.startswith("ID_LEATHER_BOOTS"): return "Boots"
    if name.startswith("ID_LEATHER_GLOVES"): return "Gloves"
    if name.startswith("ID_GLOVES"): return "Gloves"
    if name.startswith("ID_BOOTS"): return "Boots"
    if name.startswith("ID_CLOTHES"): return "Clothes"
    if name.startswith("ID_ROBE"): return "Robe"
    if name.startswith("ID_FACE"): return "Face"
    if name.startswith("ID_HAIR"): return "Hair"
    if name.startswith("ID_EYE"): return "Eye"
    if name.startswith("ID_SKIN"): return "Skin"
    if name.startswith("ID_BODYCHG"): return "Body change"
    if name.startswith("ID_RIDE"): return "Mount"
    if name in ("ID_NONE", "ID_BASE", "ID_BODY", "ID_BASE_WEAPON"): return "Meta"
    return "Other"


def category_for_cid0_id(rid: int, name: str) -> str:
    if name in ("NONE", "MALE", "FEMALE"): return "Gender"
    if 1200 <= rid <= 1225: return "Monster taxonomy"
    if name.startswith("E"): return "Enemy class"
    if name.startswith("NN"): return "NPC family"
    if name.startswith("NM"): return "NM family"
    if name.startswith("MO"): return "Mount/mob"
    if name.startswith("ZMK"): return "Boss"
    if name.startswith("KD"): return "KD-class"
    if name.startswith("NE"): return "NE-class"
    if name.startswith("FO"): return "FO-class"
    return "Other"


# ---------- Index ------------------------------------------------------------

def _hero_parade_sprites() -> str:
    """Build the HTML for the homepage's animated sprite parade.

    Picks a curated mix of NN / NM / enemy / NE sprites that already exist in
    `wiki/static/sprites/`, duplicates the list once so the CSS marquee can loop
    seamlessly (-50% translateX), and emits the parade markup. The selection is
    deliberately spaced through each family to give visual variety.
    """
    bases = []
    for sub in ("nn", "nm", "e", "ne"):
        d = SPRITES_DST / sub
        if not d.exists():
            continue
        files = sorted(d.glob("*.png"))
        # Pick spaced samples from each family for variety — not a random
        # shuffle (we want stable output across rebuilds).
        if sub == "nn":
            picks = files[::18]            # 10 from 180 → every 18th
        elif sub == "nm":
            picks = files[::6]             # 9 from 54
        elif sub == "e":
            picks = files[::12]            # 13 from 155
        else:                              # ne
            picks = files[:]               # 2 of 2 bosses
        for p in picks:
            bases.append((sub, p.name, p.stem))

    # Build sprite cells. Duplicate list so the marquee animation can loop
    # without any visible "snap" at the wrap boundary.
    def _cell(sub, fname, stem):
        return (
            f'<div class="sprite" title="{html.escape(stem)}">'
            f'<img src="static/sprites/{sub}/{fname}" '
            f'alt="{html.escape(stem)}" loading="lazy">'
            f'</div>'
        )

    cells = [_cell(*b) for b in bases]
    track = "\n      ".join(cells + cells)  # double-up for seamless wrap

    return f"""
<div class="hero-parade" aria-hidden="true">
  <div class="hero-parade-track">
      {track}
  </div>
</div>"""


def build_index(cid0, cid1, tdab):
    n_actions = tdab["action_count"]
    n_parts = sum(len(a["parts"]) for a in tdab["actions"])

    # Aggregate stats
    n_equip = len(cid1)
    n_enemies = sum(1 for n in cid0.values() if n.startswith("E"))
    n_npcs = sum(1 for n in cid0.values() if n.startswith("NN"))
    icon_total = 3125

    parade = _hero_parade_sprites()

    body = f"""
<section class="hero archive-hero">
  <div class="hero-copy">
    <div class="subtitle">Reverse-engineered MMO preservation archive</div>
    <h1>Tales of Eternia Online</h1>
    <p class="lede">An offline-extracted reference for Namco's discontinued MMO: equipment, enemy classes, NPC atlases, battle-action scripts, maps, audio, and container-format research preserved from the original client.</p>
  </div>
  <div class="hero-ledger" aria-label="Archive status">
    <span class="ledger-label">Recovered corpus</span>
    <strong>7 decoded container families</strong>
    <span>BNKD / IDTB / ICND / TDAB / CRSD / NNTB / ATDT</span>
  </div>
</section>

{parade}

<div class="stat-grid">
  <div class="stat"><span class="num">{icon_total:,}</span><span class="label">Item icons</span></div>
  <div class="stat"><span class="num">{n_equip:,}</span><span class="label">Equipment IDs</span></div>
  <div class="stat"><span class="num">{n_enemies:,}</span><span class="label">Enemy classes</span></div>
  <div class="stat"><span class="num">{n_npcs}</span><span class="label">NPC entries</span></div>
  <div class="stat"><span class="num">{n_actions:,}</span><span class="label">Battle actions</span></div>
  <div class="stat"><span class="num">{n_parts:,}</span><span class="label">Action parts</span></div>
  <div class="stat"><span class="num">27,498</span><span class="label">Texture atlases</span></div>
  <div class="stat"><span class="num">50</span><span class="label">Zones with minimaps</span></div>
  <div class="stat"><span class="num">7</span><span class="label">Container formats RE'd</span></div>
</div>

<h2>Browse the archive</h2>

<div class="cat-grid">
  <a class="cat-card" href="equipment/index.html" data-search="equipment sword hat shield body gloves boots accessory symbolic ids icons">
    <span class="name">Equipment</span>
    <div class="meta">{n_equip:,} symbolic IDs · 24 categories<br>Sword, Hat, Shield, Body, Gloves, Boots, Accessory…</div>
  </a>
  <a class="cat-card" href="beasts/index.html" data-search="beasts enemies monsters behavior taxonomy slime dragon mimic elemental">
    <span class="name">Beasts</span>
    <div class="meta">{n_enemies:,} enemy classes · 26-class behavior taxonomy<br>SLIME, DRAGON, MIMIC, ELEMENTAL, …</div>
  </a>
  <a class="cat-card" href="npcs/index.html" data-search="npcs nn family townfolk vendors quest-givers sprites">
    <span class="name">NPCs</span>
    <div class="meta">{n_npcs} NPC entries · NN family<br>Townfolk, vendors, quest-givers</div>
  </a>
  <a class="cat-card" href="actions/index.html" data-search="battle actions tdab animation sound effects movement scripts timelines">
    <span class="name">Battle Actions</span>
    <div class="meta">{n_actions:,} actions · {n_parts:,} parts<br>Animation tracks, sound triggers, effect refs</div>
  </a>
  <a class="cat-card" href="zones/index.html" data-search="zones maps minimaps rasheans mints barole inferia dungeons">
    <span class="name">Zones</span>
    <div class="meta">50 main maps · 93 minimap cells<br>Rasheans, Mints, Barole, Inferia field, dungeons…</div>
  </a>
  <a class="cat-card" href="audio/index.html" data-search="audio music sound effects environmentals tracks">
    <span class="name">Audio</span>
    <div class="meta">Music · sound effects · environmentals<br>Track names that double as zone-name index</div>
  </a>
  <a class="cat-card" href="bundles/index.html" data-search="asset bundles crsd nntb registrations resource aliases atd cpd">
    <span class="name">Asset Bundles</span>
    <div class="meta">460 entity registrations · CRSD<br>id → name → .atd / .cpd resource files</div>
  </a>
</div>

<h2>About this archive</h2>

<div class="note">
  <strong>Structural archive of what shipped in the recovered client.</strong> Seven container formats fully decoded, every static asset surfaced. <em>Combat numerics</em> (HP, levels, damage, drops, XP) have not been found in the recovered client corpus and were likely server-authoritative on Sigma's now-dark servers. See <a href="about.html">About</a> for the full breakdown of what's recoverable and why.
</div>

<table class="data">
  <thead><tr><th>Container</th><th>Files</th><th>Status</th><th>What it gave us</th></tr></thead>
  <tbody>
    <tr><td>BNKD</td><td class="mono">2789</td><td>✅ end-to-end</td><td>27 498 texture PNGs (NPC bodies, environments, atlases)</td></tr>
    <tr><td>IDTB</td><td class="mono">2</td><td>✅ end-to-end</td><td>Symbolic-name registries for everything</td></tr>
    <tr><td>ICND</td><td class="mono">1</td><td>✅ end-to-end</td><td>3 125 64×64 item icons in 34 categories</td></tr>
    <tr><td>TDAB</td><td class="mono">1</td><td>✅ end-to-end</td><td>1 668 battle-action scripts (anim+sound+effect+move)</td></tr>
    <tr><td>CRSD</td><td class="mono">1</td><td>✅ end-to-end</td><td>460-row character / asset registry: id → symbolic name → <code>.atd</code> + <code>.cpd</code> filenames + type code</td></tr>
    <tr><td>NNTB</td><td class="mono">1</td><td>✅ end-to-end</td><td>290-entry resource-alias map (5 zone-mark variants share one bundle)</td></tr>
    <tr><td>MAPI / MAPD</td><td class="mono">312</td><td>✅ minimap atlases extracted</td><td>50 main maps · 93 minimap cells rendered as PNGs</td></tr>
    <tr><td>ATDT/PKDF/CPDT</td><td class="mono">990</td><td>✅ format decoded</td><td>Content-hash manifests (negative result — no stats data)</td></tr>
    <tr><td>SMS2</td><td class="mono">3</td><td>🟡 untouched (optional)</td><td><span class="dim">Japanese item / skill name strings — translator exists in main-arc</span></td></tr>
    <tr><td>AMD</td><td class="mono">28</td><td>❌ untouched</td><td><span class="dim">Smallest sibling-bundle group — completionist target</span></td></tr>
  </tbody>
</table>
"""
    return page("Home", body, "/index.html", depth=0)


# ---------- Equipment --------------------------------------------------------

def build_equipment(cid1: dict[int, str]):
    by_cat: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for rid, name in cid1.items():
        by_cat[category_for_cid1_id(name)].append((rid, name))
    for cat in by_cat:
        by_cat[cat].sort()

    # ICND categories (for icon fallback) — bucket by ICND folder name based on cid1 category.
    cat_to_icnd = {
        "Sword": "Weapon", "Hat": "Head", "Shield": "Shield",
        "Body A-set": "BODY_A", "Body B-set": "BODY_B", "Body C-set": "BODY_C",
        "Body D-set": "BODY_D", "Body E-set": "BODY_E", "Body F-set": "BODY_F",
        "Body G-set": "BODY_G", "Body undergarment": "Body",
        "Gloves": "Body", "Boots": "Body",
        "Clothes": "Body", "Robe": "Body",
        "Face": "Body", "Hair": "Body", "Eye": "Body", "Skin": "Body",
        "Body change": "Body", "Mount": "Accessory", "Meta": "Body", "Other": "other",
    }

    # ---- Overview page ----
    cat_cards = []
    sample_icons = sorted_icons_by_category()
    for cat, items in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        slug = cat_slug(cat)
        thumbs = []
        icnd_cat = cat_to_icnd.get(cat, "Body")
        for slot in (sample_icons.get(icnd_cat, [])[:6]):
            thumbs.append(f'<img src="../static/icons/{html.escape(icnd_cat)}/{slot:05}.png" alt="">')
        thumb_html = "".join(thumbs)
        cat_cards.append(f"""
        <a class="cat-card" href="{slug}.html">
          <span class="name">{html.escape(cat)}</span>
          <div class="meta">{len(items):,} entries</div>
          <div class="preview">{thumb_html}</div>
        </a>""")

    overview_body = f"""
<h1>Equipment</h1>
<p class="dim">Everything wieldable, wearable, or equippable in TOEO. {sum(len(v) for v in by_cat.values()):,} symbolic IDs across {len(by_cat)} categories, joined to {sum(len(v) for v in sample_icons.values()):,} icon thumbnails where available.</p>

<div class="cat-grid">
  {''.join(cat_cards)}
</div>

<div class="note">
  Equipment IDs (e.g. <code>ID_SWORD_186C</code>) are the engine's symbolic handles. Numeric stats and English names are in different files (<code>btlact.dat</code> and <code>toeomsg*_jp.sms</code>) — those JOINs are partially-pending. See <a href="../about.html">About</a>.
</div>
"""
    out = ROOT / "equipment" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_html(out, page("Equipment", overview_body, "/equipment/index.html", depth=1))

    # ---- Per-category pages ----
    for cat, items in by_cat.items():
        slug = cat_slug(cat)
        icnd_cat = cat_to_icnd.get(cat, "Body")
        icon_dir = f"../static/icons/{icnd_cat}"

        cells = []
        slots = sample_icons.get(icnd_cat, [])
        for i, (rid, name) in enumerate(items):
            visual = equipment_visual_for(name)
            if visual:
                img_html = (
                    f'<img class="asset-thumb" src="../{visual["url"]}" '
                    f'alt="{html.escape(name)} recovered asset" loading="lazy">'
                    f'<span class="asset-source mono">{html.escape(visual["source"])}</span>'
                )
            elif i < len(slots):
                img_html = f'<img src="{icon_dir}/{slots[i]:05}.png" alt="" loading="lazy">'
            else:
                img_html = '<img alt="" style="opacity:.15">'
            cells.append(f"""
            <div class="icon-cell">
              {img_html}
              <span class="id mono">{rid}</span>
              <span class="name">{html.escape(name)}</span>
            </div>""")

        body = f"""
<p class="muted"><a href="index.html">← all categories</a></p>
<h1>{html.escape(cat)}</h1>
<p class="dim">{len(items):,} entries.</p>

<div class="search">
  <input type="text" placeholder="Filter by ID or symbolic name…" oninput="filterGrid(this)">
</div>

<div class="icon-grid" id="grid">
  {''.join(cells)}
</div>

<script>
function filterGrid(input) {{
  const q = input.value.trim().toLowerCase();
  for (const cell of document.querySelectorAll('#grid .icon-cell')) {{
    const t = cell.textContent.toLowerCase();
    cell.style.display = (!q || t.includes(q)) ? '' : 'none';
  }}
}}
</script>
"""
        outpath = ROOT / "equipment" / f"{slug}.html"
        write_html(outpath, page(cat, body, "/equipment/index.html", depth=1))


def cat_slug(cat: str) -> str:
    return cat.lower().replace(" ", "-").replace("(", "").replace(")", "").replace("/", "-")


def sorted_icons_by_category() -> dict[str, list[int]]:
    """Walk extracted/icons/<cat>/ and return sorted slot indices per category."""
    result: dict[str, list[int]] = {}
    if not ICONS_SRC.exists():
        return result
    for cat_dir in ICONS_SRC.iterdir():
        if cat_dir.is_dir():
            slots = sorted(int(p.stem) for p in cat_dir.glob("*.png"))
            result[cat_dir.name] = slots
    return result


def equipment_visual_for(name: str) -> dict[str, str] | None:
    """Return a copied wiki URL for the closest recovered equipment atlas.

    `cid1.idt` has finer-grained symbolic variants than the authored BNKD
    folders. For example, `ID_BODY_A000..A000L` share the battle-body atlas
    `B_body_a_m_00` / `B_body_a_l_00`; the suffix variants are palette or
    runtime composition choices. The wiki surfaces the recovered source atlas
    and keeps the exact symbolic ID beside it.
    """
    candidates = equipment_visual_candidates(name)
    for folder in candidates:
        src_dir = EXTRACTED_SRC / folder
        if not src_dir.is_dir():
            continue
        pngs = sorted(src_dir.glob("*.png"))
        if not pngs:
            continue
        src = pngs[0]
        dest = EQUIP_DST / folder / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or src.stat().st_mtime > dest.stat().st_mtime:
            shutil.copy2(src, dest)
        return {"url": f"static/equipment/{folder}/{src.name}", "source": folder}
    return None


def equipment_visual_candidates(name: str) -> list[str]:
    body = re.match(r"ID_BODY_([A-G])(\d{3})", name)
    if body:
        group = body.group(1).lower()
        idx = int(body.group(2))
        return [f"B_body_{group}_m_{idx:02d}", f"B_body_{group}_l_{idx:02d}"]

    under = re.match(r"ID_BODY_([ML])_U(\d{3})", name)
    if under:
        # Undergarment IDs are runtime-composited; the closest recovered
        # standalone body atlas is the matching early body slot.
        sex = "m" if under.group(1) == "M" else "l"
        idx = int(under.group(2))
        return [f"B_body_a_{sex}_{idx:02d}"]

    head = re.match(r"ID_HAT_(\d{3})", name)
    if head:
        idx = int(head.group(1))
        return [f"B_hat_{idx:03d}"]

    hair = re.match(r"ID_HAIR(\d+)", name)
    if hair:
        idx = int(hair.group(1)) - 1
        return [
            f"ml00_hair_{idx:02d}", f"ms00_hair_{idx:02d}",
            f"fl00_hair_{idx:02d}", f"fs00_hair_{idx:02d}",
        ]

    face = re.match(r"ID_FACE(\d)_(\d+)", name)
    if face:
        family = int(face.group(1))
        return [f"ml{family:02d}_face_00", f"ms{family:02d}_face_00", f"fl{family:02d}_face_00", f"fs{family:02d}_face_00"]

    eye = re.match(r"ID_EYE(\d+)", name)
    if eye:
        idx = int(eye.group(1)) - 1
        eye_names = ["nor", "tar", "tur"]
        if idx < len(eye_names):
            suffix = eye_names[idx]
            return [f"ml00_eye_{suffix}", f"ms00_eye_{suffix}", f"fl00_eye_{suffix}", f"fs00_eye_{suffix}"]

    bodychg = re.match(r"ID_BODYCHG(\d+)", name)
    if bodychg:
        idx = int(bodychg.group(1)) - 1
        return [f"B_body_a_m_{idx:02d}", f"B_body_a_l_{idx:02d}"]

    if name in ("ID_BODY", "ID_BASE"):
        return ["B_body_a_m_00", "B_body_a_l_00"]
    if name == "ID_BASE_WEAPON":
        return ["B_sword_000"]

    return []


# ---------- Beasts -----------------------------------------------------------

def _enemy_sprite_for(name: str) -> Path | None:
    """Map a cid0 enemy entry like 'E000' or 'E000A' to its extracted bundle sprite.

    The atlas dir is `e<XXX>_b/`; letter-variants share the same atlas.
    Returns the largest PNG in the dir, or None if no extract.
    """
    if not name.startswith("E") or len(name) < 4:
        return None
    # Strip optional trailing letter variant (E000A, E001B, …)
    digits = ""
    for c in name[1:]:
        if c.isdigit():
            digits += c
        else:
            break
    if not digits:
        return None
    idx = int(digits)
    # Try `e<XXX>_b` first, then a few common variant suffixes.
    for variant in ("_b", "_a", ""):
        d = EXTRACTED_SRC / f"e{idx:03d}{variant}"
        if d.is_dir():
            pngs = sorted(d.glob("*.png"))
            if pngs:
                return max(pngs, key=lambda p: p.stat().st_size)
    return None


def _named_entity_sprite_for(name: str) -> Path | None:
    """Map a cid0 NE entry like 'NE001' to its boss sprite atlas.

    Three known sources, in priority order: M_NE### (full rig), B_NE###_01 (battle frames).
    """
    if not name.startswith("NE"):
        return None
    digits = "".join(c for c in name if c.isdigit())
    if not digits:
        return None
    idx = int(digits)
    candidates = [
        EXTRACTED_SRC / f"M_NE{idx:03d}",
        EXTRACTED_SRC / f"B_NE{idx:03d}_01",
        EXTRACTED_SRC / f"B_NE{idx:03d}_02",
    ]
    for d in candidates:
        if d.is_dir():
            pngs = sorted(d.glob("*.png"))
            if pngs:
                return max(pngs, key=lambda p: p.stat().st_size)
    return None


def build_beasts(cid0: dict[int, str]):
    by_cat: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for rid, name in cid0.items():
        by_cat[category_for_cid0_id(rid, name)].append((rid, name))
    for cat in by_cat:
        by_cat[cat].sort()

    taxonomy = by_cat.get("Monster taxonomy", [])
    enemies = by_cat.get("Enemy class", [])
    ne_class = by_cat.get("NE-class", [])
    mo_class = by_cat.get("Mount/mob", [])
    boss = by_cat.get("Boss", [])

    # ------ Enemy sprite cards (only entries with extracted sprites) ------
    enemy_cards_with_sprite = []
    enemy_cards_no_sprite = []
    enemy_sprite_count = 0
    for rid, name in enemies:
        src = _enemy_sprite_for(name)
        if src is None:
            enemy_cards_no_sprite.append((rid, name))
            continue
        sprite_url = _copy_sprite(src, "e", name)
        if sprite_url is None:
            enemy_cards_no_sprite.append((rid, name))
            continue
        enemy_sprite_count += 1
        enemy_cards_with_sprite.append(f"""
        <div class="npc-card" data-name="{html.escape(name)}" data-id="{rid}">
          <a href="../{sprite_url}" target="_blank">
            <img src="../{sprite_url}" alt="{html.escape(name)} sprite" loading="lazy">
          </a>
          <div class="npc-meta">
            <span class="npc-name mono">{html.escape(name)}</span>
            <span class="npc-id mono dim">id {rid}</span>
          </div>
        </div>""")

    # ------ NE / boss cards ------
    ne_cards = []
    ne_with_sprite = 0
    for rid, name in ne_class:
        src = _named_entity_sprite_for(name)
        sprite_url = _copy_sprite(src, "ne", name) if src else None
        if sprite_url:
            ne_with_sprite += 1
            img_html = (
                f'<a href="../{sprite_url}" target="_blank">'
                f'<img src="../{sprite_url}" alt="{html.escape(name)} sprite" loading="lazy"></a>'
            )
        else:
            img_html = '<div class="no-sprite">no sprite</div>'
        ne_cards.append(f"""
        <div class="npc-card" data-name="{html.escape(name)}" data-id="{rid}">
          {img_html}
          <div class="npc-meta">
            <span class="npc-name mono">{html.escape(name)}</span>
            <span class="npc-id mono dim">id {rid}</span>
          </div>
        </div>""")

    # ------ Taxonomy (no sprites — these are behavior-class enums) ------
    taxonomy_cards = []
    for rid, name in taxonomy:
        gloss = {
            "HITODE": "Starfish",
            "KAME": "Turtle",
            "TAKO": "Octopus",
            "MIMIC": "Mimic (treasure ambush)",
            "TWOWALKBEAST": "Bipedal beast",
            "FOURWALKBEAST": "Quadruped beast",
            "SUBSPECIES_MAN": "Humanoid subspecies",
            "MAGICBOT": "Constructed magic-driven foe",
            "INSECTSMALL": "Small insect",
            "INSECTLARGE": "Large insect",
            "INSECTFLY": "Flying insect",
            "LARGEPLANT": "Large plant",
        }.get(name, name.title().replace("_", " "))
        taxonomy_cards.append(f"""
        <div class="cat-card">
          <span class="name">{html.escape(name)}</span>
          <div class="meta">id {rid} · {html.escape(gloss)}</div>
        </div>""")

    body = f"""
<h1>Beasts</h1>
<p class="dim">{sum(len(v) for v in by_cat.values()):,} entries from <code>cid0.idt</code>. The catalog includes the engine's 26-class behavior taxonomy, every enemy class with an authored sprite atlas, and the named-entity (NE) story bosses.</p>

<div class="stat-grid">
  <div class="stat"><span class="num">{len(enemies):,}</span><span class="label">Enemy slots reserved</span></div>
  <div class="stat"><span class="num">{enemy_sprite_count}</span><span class="label">Enemy sprites authored</span></div>
  <div class="stat"><span class="num">{len(ne_class)}</span><span class="label">Named entities</span></div>
  <div class="stat"><span class="num">{len(taxonomy)}</span><span class="label">Behavior classes</span></div>
</div>

<h2>Named-entity bosses <span class="muted" style="font-size:.7em">{ne_with_sprite} of {len(ne_class)} with sprite</span></h2>
<p class="dim">Storyline characters with full multi-pose battle rigs. Sprites are sourced from <code>M_NE###</code> (full pose sheet) or <code>B_NE###_01</code> (battle frames) bundles.</p>
<div class="npc-grid">
{''.join(ne_cards)}
</div>

<h2>Behavior taxonomy <span class="muted" style="font-size:.7em">26 classes</span></h2>
<p class="dim">Hardcoded class-name strings at IDs 1200–1225 in <code>cid0.idt</code>. The server's spawn/pathing/attack logic keys on these labels — they decide whether something walks on legs, slithers, swims, or floats.</p>
<div class="cat-grid">
  {''.join(taxonomy_cards)}
</div>

<h2>Enemy classes <span class="muted" style="font-size:.7em">{enemy_sprite_count} authored sprites of {len(enemies):,} reserved slots</span></h2>
<p class="dim">Enemy bundles use the naming pattern <code>e&lt;XXX&gt;_b.bnd</code>. Letter-suffix variants (E000A, E000B, …) share the same atlas — they're palette/equipment swaps the engine renders at runtime.</p>

<div class="search">
  <input type="text" placeholder="Filter by ID or symbolic name…" oninput="beastFilter(this)">
</div>
<div class="npc-grid" id="enemy-grid">
{''.join(enemy_cards_with_sprite)}
</div>

<div class="note">
  Of the 5 000 reserved <code>E####</code> slots, only ~150 have authored bundle sprites. The remaining {len(enemies) - enemy_sprite_count:,} entries are content-team placeholders — Sigma planned more enemies than shipped. The full ID list (slots without sprites) follows below.
</div>

<details>
<summary class="dim" style="cursor:pointer; padding:0.5em 0;">Show {len(enemy_cards_no_sprite):,} reserved slots without sprites…</summary>
<table class="data" id="enemy-rest-tbl" style="margin-top:1em">
  <thead><tr><th>ID</th><th>Symbolic name</th></tr></thead>
  <tbody>
{''.join(f"<tr><td class='mono'>{rid}</td><td class='mono'>{html.escape(n)}</td></tr>" for rid, n in enemy_cards_no_sprite[:500])}
  </tbody>
</table>
<p class="dim" style="font-size:.85em">(showing first 500 of {len(enemy_cards_no_sprite):,})</p>
</details>

<h2>Other categories</h2>
<table class="data">
  <thead><tr><th>Category</th><th>Count</th></tr></thead>
  <tbody>
    {''.join(f"<tr><td>{html.escape(c)}</td><td class='mono'>{len(v):,}</td></tr>" for c, v in sorted(by_cat.items()) if c not in ('Enemy class', 'Monster taxonomy', 'NE-class'))}
  </tbody>
</table>

<script>
function beastFilter(input) {{
  const q = input.value.trim().toLowerCase();
  for (const c of document.querySelectorAll('#enemy-grid .npc-card')) {{
    const t = (c.dataset.name + ' ' + c.dataset.id).toLowerCase();
    c.style.display = (!q || t.includes(q)) ? '' : 'none';
  }}
}}
</script>
"""
    out = ROOT / "beasts" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_html(out, page("Beasts", body, "/beasts/index.html", depth=1))
    print(f"  enemy sprites: {enemy_sprite_count}/{len(enemies):,} - NE bosses: {ne_with_sprite}/{len(ne_class)}")


# ---------- NPCs -------------------------------------------------------------

def _collect_sprite_thumb(prefix: str, idx: int) -> Path | None:
    """Return the path of the first/best PNG in the extracted bundle dir for prefix+idx.

    `prefix` is like 'NN' or 'NM'. The cid0 IDs `NN001` -> bundle `NN001`. Some
    bundles use 1-padded names (NN1.bnd) so try both.
    """
    candidates = [
        EXTRACTED_SRC / f"{prefix}{idx:03d}",
        EXTRACTED_SRC / f"{prefix}{idx:03d}A",  # NM051A etc.
        EXTRACTED_SRC / f"{prefix}{idx}",
    ]
    for d in candidates:
        if d.is_dir():
            pngs = sorted(d.glob("*.png"))
            if pngs:
                # Prefer the largest file (richest atlas)
                return max(pngs, key=lambda p: p.stat().st_size)
    return None


def _copy_sprite(src: Path, sprite_dest_subdir: str, dest_name: str) -> str | None:
    """Copy `src` PNG into wiki/static/sprites/<subdir>/<dest_name>.png.

    Returns the relative path (from wiki root) or None on failure.
    """
    if src is None or not src.exists():
        return None
    dest_dir = SPRITES_DST / sprite_dest_subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{dest_name}.png"
    if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
        shutil.copyfile(src, dest)
    return f"static/sprites/{sprite_dest_subdir}/{dest_name}.png"


def build_npcs(cid0: dict[int, str]):
    """NPC page now renders the actual sprite atlas for each entry."""

    nn = sorted([(rid, name) for rid, name in cid0.items() if name.startswith("NN")])
    nm = sorted([(rid, name) for rid, name in cid0.items() if name.startswith("NM")])

    def _gather(prefix: str, entries: list[tuple[int, str]]):
        cards = []
        with_sprite = without_sprite = 0
        for rid, name in entries:
            # Symbolic name e.g. "NN001" — extract the numeric tail.
            try:
                idx = int("".join(c for c in name if c.isdigit()))
            except ValueError:
                idx = 0
            src = _collect_sprite_thumb(prefix, idx)
            sprite_url = _copy_sprite(src, prefix.lower(), name) if src else None
            if sprite_url:
                with_sprite += 1
                img_html = (
                    f'<a href="../{sprite_url}" target="_blank">'
                    f'<img src="../{sprite_url}" alt="{html.escape(name)} sprite" loading="lazy"></a>'
                )
            else:
                without_sprite += 1
                img_html = '<div class="no-sprite">no sprite</div>'
            cards.append(f"""
            <div class="npc-card" data-name="{html.escape(name)}" data-id="{rid}">
              {img_html}
              <div class="npc-meta">
                <span class="npc-name mono">{html.escape(name)}</span>
                <span class="npc-id mono dim">id {rid}</span>
              </div>
            </div>""")
        return cards, with_sprite, without_sprite

    nn_cards, nn_with, nn_without = _gather("NN", nn)
    nm_cards, nm_with, nm_without = _gather("NM", nm)

    body = f"""
<h1>NPCs</h1>
<p class="dim">{len(nn) + len(nm):,} NPC entries from <code>cid0.idt</code> with sprite atlases extracted from the corresponding <code>.bnd</code> bundles. Each thumbnail shows the NPC's full 8-direction walk cycle plus pose variants — the same atlas the engine streams to the renderer.</p>

<div class="stat-grid">
  <div class="stat"><span class="num">{len(nn)}</span><span class="label">NN entries</span></div>
  <div class="stat"><span class="num">{nn_with}</span><span class="label">with sprite</span></div>
  <div class="stat"><span class="num">{len(nm)}</span><span class="label">NM entries</span></div>
  <div class="stat"><span class="num">{nm_with}</span><span class="label">with sprite</span></div>
</div>

<div class="search">
  <input type="text" placeholder="Filter by ID or symbolic name…" oninput="npcFilter(this)">
</div>

<h2>NN family — townfolk, vendors, quest-givers <span class="muted" style="font-size:.7em">{len(nn)} entries</span></h2>
<div class="npc-grid" id="npc-nn">
{''.join(nn_cards)}
</div>

<h2>NM family <span class="muted" style="font-size:.7em">{len(nm)} entries</span></h2>
<div class="npc-grid" id="npc-nm">
{''.join(nm_cards)}
</div>

<div class="note">
  Sprites are full atlases — typically 8 walking directions stacked vertically. Click any sprite to view at native size. English / Japanese display names, dialog, and shop inventories live in <code>toeomsg*_jp.sms</code> and the help <code>.bcv</code> files; that JOIN to these IDs is the next pending step.
</div>

<script>
function npcFilter(input) {{
  const q = input.value.trim().toLowerCase();
  for (const c of document.querySelectorAll('.npc-card')) {{
    const t = (c.dataset.name + ' ' + c.dataset.id).toLowerCase();
    c.style.display = (!q || t.includes(q)) ? '' : 'none';
  }}
}}
</script>
"""
    out = ROOT / "npcs" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_html(out, page("NPCs", body, "/npcs/index.html", depth=1))
    print(f"  NN: {nn_with}/{len(nn)} sprites - NM: {nm_with}/{len(nm)} sprites")


# ---------- Actions ----------------------------------------------------------

def _resolve_timeline(parts):
    """Resolve absolute (start,end) frame times for each part, handling triggers transitively.

    Triggers reference other parts by index. start_trig_index = 0xFFFFFFFF means
    'no trigger, fires immediately'. Otherwise the part starts when the referenced
    part starts, plus start_trig_time offset. Same for end.
    """
    NONE = 0xFFFFFFFF
    n = len(parts)
    starts = [None] * n
    ends = [None] * n

    def res_start(i, depth=0):
        if starts[i] is not None: return starts[i]
        if depth > 8: return 0   # cycle guard
        f = parts[i]["fields"]
        sti = f.get("start_trig_index", NONE)
        sto = f.get("start_trig_time", 0)
        if sti == NONE or sti >= n:
            s = 0
        else:
            s = res_start(sti, depth + 1) + sto
        starts[i] = max(0, s)
        return starts[i]

    def res_end(i, depth=0):
        if ends[i] is not None: return ends[i]
        if depth > 8: return res_start(i) + 8
        f = parts[i]["fields"]
        s = res_start(i)
        eti = f.get("end_trig_index", NONE)
        eto = f.get("end_trig_time", 0)
        end_time = f.get("end_time", 0)
        if eti != NONE and eti < n:
            e = res_end(eti, depth + 1) + eto
        elif end_time > 0:
            e = s + end_time
        else:
            e = s + 8   # default tick width if no duration info
        ends[i] = max(s + 1, e)  # at least 1 frame visible
        return ends[i]

    for i in range(n):
        res_start(i)
        res_end(i)
    return starts, ends


def _timeline_html(parts):
    """Build the timeline HTML for one action."""
    if not parts:
        return ""
    starts, ends = _resolve_timeline(parts)
    max_t = max(ends) if ends else 1
    # Round max_t up to nearest 30 for nicer ticks
    scale_max = max(30, ((max_t + 29) // 30) * 30)

    track_html = []
    for i, p in enumerate(parts):
        pf = p["fields"]
        tn = pf.get("type_name", "?")
        s = starts[i]
        e = ends[i]
        left_pct = (s / scale_max) * 100
        width_pct = max(1.5, ((e - s) / scale_max) * 100)
        # Label: prefer name fields
        label = pf.get("anim_name") or pf.get("sound_name")
        if not label:
            if tn == "effect":
                label = f"effect#{pf.get('effect_id', pf.get('index', '?'))}"
            elif tn == "move":
                mv = pf.get("move_move", [0, 0])
                label = f"move({mv[0]:.0f},{mv[1]:.0f})" if any(mv) else "move"
            else:
                label = tn
        title = f"part #{i} · {tn} · t={s}..{e} ({e-s} frames)"
        track_html.append(
            f'<div class="track"><div class="bar t-{tn}" '
            f'style="left:{left_pct:.2f}%; width:{width_pct:.2f}%;" '
            f'title="{html.escape(title)}">{html.escape(str(label))}</div></div>'
        )

    # Time scale ticks every 30 frames
    ticks = []
    step = 30
    t = 0
    while t <= scale_max:
        pct = (t / scale_max) * 100
        ticks.append(f'<span class="tick" style="left:{pct:.2f}%">{t}</span>')
        t += step

    legend = """<div class="legend">
      <span><span class="swatch t-anim"></span>anim</span>
      <span><span class="swatch t-sound"></span>sound</span>
      <span><span class="swatch t-effect"></span>effect</span>
      <span><span class="swatch t-move"></span>move</span>
      <span class="muted">frames →</span>
    </div>"""

    return f"""<div class="timeline">
      {''.join(track_html)}
      <div class="scale">{''.join(ticks)}</div>
      {legend}
    </div>"""


def build_actions(tdab):
    actions = tdab["actions"]
    n = len(actions)

    # Build action cards for the first 80 (more makes the page heavy).
    cards = []
    for a in actions[:80]:
        af = a["fields"]
        rid = af.get("id", "?")
        flag = af.get("flag", 0)
        parts = a["parts"]
        n_parts = len(parts)

        # Per-part text breakdown (compact)
        rows = []
        haystack = [str(rid)]
        for i, p in enumerate(parts):
            pf = p["fields"]
            tn = pf.get("type_name", "?")
            details = []
            for k in ("anim_name", "sound_name", "effect_id", "effect_range", "end_time"):
                v = pf.get(k)
                if v not in (None, "", 0, 0.0, "0"):
                    details.append(f"{k}={html.escape(str(v))}")
                    if isinstance(v, str): haystack.append(v.lower())
            haystack.append(tn)
            rows.append(
                f'<div class="row"><span class="pn">{tn}</span>'
                f'<span class="pd">{" · ".join(details) or "<span class=muted>(no payload)</span>"}</span></div>'
            )

        timeline = _timeline_html(parts) if parts else '<div class="dim small">no parts</div>'

        cards.append(f"""
        <div class="action-card" data-search="{html.escape(' '.join(haystack))}">
          <div class="head">
            <span class="id">action {rid}</span>
            <span class="meta">flag={flag} · {n_parts} part{'s' if n_parts != 1 else ''}</span>
          </div>
          {timeline}
          <div class="parts-table">{''.join(rows)}</div>
        </div>""")

    # Aggregate vocabulary
    type_counter = Counter()
    anim_set = set()
    sound_set = set()
    for a in actions:
        for p in a["parts"]:
            tn = p["fields"].get("type_name")
            if tn: type_counter[tn] += 1
            an = p["fields"].get("anim_name")
            if an: anim_set.add(an)
            sn = p["fields"].get("sound_name")
            if sn: sound_set.add(sn)

    type_pills = " ".join(
        f'<span class="tag t-{t}">{t} · {c:,}</span>' for t, c in type_counter.most_common()
    )

    body = f"""
<h1>Battle Actions</h1>
<p class="dim">{n:,} action scripts decoded from <code>btlact.dat</code> (TDAB chunk-stream). Each action is a sequence of typed <em>parts</em> — discrete trigger frames for animation, sound, visual effect, or movement. The format is Namco's frame-by-frame event-track model.</p>

<div class="stat-grid">
  <div class="stat"><span class="num">{n:,}</span><span class="label">Actions</span></div>
  <div class="stat"><span class="num">{sum(type_counter.values()):,}</span><span class="label">Total parts</span></div>
  <div class="stat"><span class="num">{len(anim_set)}</span><span class="label">Unique animations</span></div>
  <div class="stat"><span class="num">{len(sound_set)}</span><span class="label">Unique sounds</span></div>
</div>

<h2>Part-type distribution</h2>
<p>{type_pills}</p>

<h2>Animation vocabulary <span class="muted" style="font-size:.7em">{len(anim_set)} unique tokens</span></h2>
<p class="dim mono">{html.escape(', '.join(sorted(anim_set)))}</p>

<h2>Sound vocabulary <span class="muted" style="font-size:.7em">{len(sound_set)} unique tokens</span></h2>
<p class="dim mono">{html.escape(', '.join(sorted(sound_set)))}</p>

<h2>Action timelines <span class="muted" style="font-size:.7em">first 80 of {n:,}</span></h2>
<p class="dim">Each card is one combat script. The horizontal bars are <em>parts</em> — discrete frame-track events for animation, sound, effect, or movement — placed on a frame timeline (30-frame ticks; the engine runs the game world at 60 fps so a tick ≈ 0.5 s). Trigger relationships between parts are resolved transitively: a part that "starts when part 0 ends" is positioned accordingly. The text rows below each timeline show every part's named payload.</p>

<div class="search">
  <input type="text" placeholder="Filter actions by id, anim name, sound name, effect…" oninput="actFilter(this)">
</div>

<div id="actions">
{''.join(cards)}
</div>

<div class="note">
  Action IDs span <code>1..90 001 610</code> in clusters: 39 generic baseline actions (1–99), 277 NPC/enemy combat scripts (100k–1M), and a 1 325-action <strong>main-character combo bank</strong> in the <code>90001xxx</code> namespace (matches the <code>B_ATTACK1_*</code> / <code>B_SPECIAL_*</code> animation vocabulary). The equipment ↔ action JOIN — which weapon plays which combo — is not in CRSD (we checked); it likely lives inside TDAB itself as an unsurfaced per-action owner field, or in a <code>.cpd</code> manifest of the right row count.
</div>

<script>
function actFilter(input) {{
  const q = input.value.trim().toLowerCase();
  for (const c of document.querySelectorAll('#actions .action-card')) {{
    const haystack = (c.dataset.search || c.textContent).toLowerCase();
    c.style.display = (!q || haystack.includes(q)) ? '' : 'none';
  }}
}}
</script>
"""
    out = ROOT / "actions" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_html(out, page("Battle Actions", body, "/actions/index.html", depth=1))


# ---------- About ------------------------------------------------------------

def build_about():
    body = """
<h1>About this archive</h1>

<p class="lede">
A static reference for the assets that shipped in <em>Tales of Eternia Online</em>'s PC client. The MMO ran 2003–2007 in Japan, operated by Namco's MMO partner ISAO Corporation. Servers are dark, but the client's asset binaries yield to careful reverse engineering — every container format used by the engine has now been decoded, and what's here is the complete <strong>structural archive</strong> of what the client carried.
</p>

<h2>What this archive contains</h2>
<ul>
  <li><strong>Equipment</strong> — 2 722 symbolic IDs across 24 categories, joined to icon thumbnails where authored</li>
  <li><strong>Beasts</strong> — 4 804 enemy slots (155 with authored sprite atlases) plus 26 behavior taxonomy classes and the named-entity bosses</li>
  <li><strong>NPCs</strong> — 180 NPCs (NN family) with 8-directional sprite atlases, plus 54 neighbour-models</li>
  <li><strong>Battle Actions</strong> — 1 668 frame-by-frame combat scripts (anim / sound / effect / movement timelines)</li>
  <li><strong>Zones</strong> — 50 main maps plus 93 minimap cells, 256×256 PNGs extracted from the client's map bundles</li>
  <li><strong>Asset Bundles</strong> — 460-row character/asset registry: id → name → <code>.atd</code> + <code>.cpd</code> resource files; plus 5 zone-mark resource aliases</li>
</ul>

<h2>What this archive does NOT contain — and why</h2>

<p>The most-asked question for a game wiki is "how much HP does this monster have?" The honest answer is: <strong>we have not found confirmed authoritative stat or drop tables in the recovered client corpus</strong>. TOEO was an MMO, so values such as HP, damage, EXP, drops, and reward logic were likely controlled by the live server rather than stored as static client assets.</p>

<table class="data" style="max-width: 56em">
  <thead><tr><th>Data category</th><th>Where it lived</th><th>Recoverable?</th></tr></thead>
  <tbody>
    <tr><td>Models, textures, animations, UI, sounds</td><td>On the disc / patcher</td><td>✅ Recovered (this archive)</td></tr>
    <tr><td>Symbolic names, item icons, asset registry</td><td>Patched in post-launch (<code>cid0.idt</code>, <code>crsid.crs</code>, <code>icon_item.icd</code>, …)</td><td>✅ Recovered (this archive)</td></tr>
    <tr><td>Map geometry, zone identity</td><td>On the disc (<code>.mpi</code> / <code>.mpd</code> / minimap <code>.bnd</code>)</td><td>✅ Recovered (this archive)</td></tr>
    <tr><td>Mob HP / level / damage formulas</td><td>Sigma's authoritative servers</td><td>❌ Lost when servers shut down 2007</td></tr>
    <tr><td>Drop tables / shop tables / XP curves</td><td>Sigma's authoritative servers</td><td>❌ Lost when servers shut down 2007</td></tr>
    <tr><td>Spawn locations / aggro ranges / behavior parameters</td><td>Sigma's authoritative servers</td><td>❌ Lost when servers shut down 2007</td></tr>
    <tr><td>Localized English item / skill / monster names</td><td>JP-only game; English wiki names are inferred from Tales franchise lore where applicable</td><td>⚠️ Partial — cross-referenced from <em>Tales of Eternia</em> canon</td></tr>
  </tbody>
</table>

<p>This is the universal structural property of MMO archaeology: live-server numbers die with the servers. The client only ever held the <em>presentation</em> layer; combat math, drop chances, and progression curves were computed server-side as an anti-cheat necessity. We checked the launch-day ISO, the post-patch installed tree, the patcher infrastructure URLs (<code>patch.toeo.jp</code>, no Wayback Machine snapshots), and the publisher's hosting partner records — confirmed: no source remains.</p>

<h2>Container formats decoded</h2>
<p>Seven formal container families and one shared engine library, all RE'd from the original client:</p>
<ul>
  <li><strong>BNKD</strong> — texture bundles. 2 789 files → 27 498 PNGs via Namco's LzComp2 + A1R5G5B5 / palette8 pipeline.</li>
  <li><strong>IDTB</strong> — symbolic-ID dictionary. <code>cid0.idt</code> (5 097 entries) + <code>cid1.idt</code> (2 722 entries). Namco-Blowfish (LE-swap), key <code>"idtable text"</code>.</li>
  <li><strong>ICND</strong> — icon registry. 3 125 authored 64×64 icons across 34 categories.</li>
  <li><strong>TDAB</strong> — battle-action database. 1 668 actions × 6 779 parts of frame-track data. Built on Namco's <code>Sys_CChunkFile.cpp</code> typed-stream serializer.</li>
  <li><strong>CRSD</strong> — character/asset registry. 460 entity rows (id, name, atd, cpd, type). Per-record Blowfish, key <code>"crs text"</code>.</li>
  <li><strong>NNTB</strong> — resource-alias map. 290 entries; the 5 non-identity aliases declare zone-mark bundle sharing. Per-record Blowfish, key <code>"nntable text"</code>.</li>
  <li><strong>ATDT / PKDF / CPDT</strong> — content-hash manifest family (990 files); structural shape decoded, contents are integrity manifests not gameplay data.</li>
  <li><strong>Sys_CChunkFile</strong> — the chunk-stream library itself, now available as a generic Python reader (<code>cchunkfile.py</code>).</li>
</ul>

<h2>Method notes</h2>
<p>Static analysis leveraged the Namco engine's verbose assertion strings: every <code>Source/Sys_*.cpp</code> path leaks a library name. Decompiler output, disassembly, and corpus-wide validation were combined to recover container headers, record layouts, pointer relocation rules, compression paths, and encrypted table structures. Runtime probing was used only where static structure was not enough to explain protocol behavior.</p>

<h2>Legal</h2>
<p class="muted">Asset binaries (texture data, audio, copyrighted content) are <strong>not redistributed</strong>. This archive consists of:</p>
<ul class="muted">
  <li>Reverse-engineered file-format documentation and decoders</li>
  <li>Derived data tables (symbolic IDs, action timing schemas, vocabulary lists, asset registries)</li>
  <li>Icons and minimaps rendered from the user's locally-extracted client copy at build time</li>
</ul>
<p class="muted">Run <code>python3 build_wiki.py</code> against your own copy of the client to populate the visual assets. Tales of Eternia Online © Namco Bandai 2003–2007 / ISAO Corporation.</p>
"""
    out = ROOT / "about.html"
    write_html(out, page("About", body, "/about.html", depth=0))


# ---------- Bundles (CRSD + NNTB) -------------------------------------------

TYPE_LABELS = {
    0: "Sentinel / PC variant",
    1: "Enemy / base PC",
    2: "Field object",
    3: "Zone-mark",
    4: "NPC / monster taxonomy / special",
}

def _bundle_family(name: str) -> str:
    if name == "NONE": return "Sentinel"
    if name.startswith("PC"): return "Player character"
    if name.startswith("ZMK"): return "Zone-mark"
    if name.startswith("NN"): return "NPC"
    if name.startswith("NM"): return "Neighbour-model"
    if name.startswith("MO"): return "Mount / mob"
    if name.startswith("KD"): return "KD-class"
    if name.startswith("NE"): return "NE-class"
    if name.startswith("FO"): return "Field-object"
    if name.startswith("E") and name[1:].split("_")[0].isdigit(): return "Enemy slot"
    return "Behavior taxonomy"


def build_bundles(crsd, nntb):
    if crsd is None:
        print("  (no CRSD JSON — skipping bundles page)")
        return
    rows = crsd["rows"]
    by_family: dict[str, list] = defaultdict(list)
    for r in rows:
        by_family[_bundle_family(r["name"])].append(r)
    for fam in by_family:
        by_family[fam].sort(key=lambda r: r["id"])

    type_hist = Counter(r["type"] for r in rows)

    # NNTB aliases callout
    aliases_html = ""
    if nntb is not None:
        non_id = nntb["non_identity_aliases"]
        if non_id:
            alias_rows = "".join(
                f"<tr><td class='mono'>{html.escape(a['name'])}</td><td class='mono'>→</td><td class='mono'>{html.escape(a['resource_alias'])}</td></tr>"
                for a in non_id
            )
            aliases_html = f"""
<h2>Resource aliases <span class="muted" style="font-size:.7em">from <code>cty2rs.nnt</code> (NNTB)</span></h2>
<p class="dim">NNTB is a 290-entry canonicalization map declaring which logical entity names share an asset bundle. {len(nntb['aliases']) - len(non_id)} entries are identity (name → self); the {len(non_id)} non-identity aliases below are the engine's bundle-sharing optimization for visually-identical zone-mark variants.</p>
<table class="data" style="max-width:30em">
  <thead><tr><th>Logical name</th><th></th><th>Loads bundle</th></tr></thead>
  <tbody>
    {alias_rows}
  </tbody>
</table>
"""

    # Family sections
    family_order = [
        "Player character", "Enemy slot", "Behavior taxonomy", "NPC",
        "Neighbour-model", "Mount / mob", "NE-class", "KD-class",
        "Zone-mark", "Field-object", "Sentinel",
    ]
    family_sections = []
    for fam in family_order:
        items = by_family.get(fam, [])
        if not items:
            continue
        body_rows = "".join(
            f"<tr>"
            f"<td class='mono'>{r['id']}</td>"
            f"<td class='mono'>{html.escape(r['name'])}</td>"
            f"<td class='mono dim'>{html.escape(r['dir'])}/{html.escape(r['atd']) if r['atd'] else '<em>—</em>'}</td>"
            f"<td class='mono dim'>{html.escape(r['cpd']) if r['cpd'] else '<em>—</em>'}</td>"
            f"<td class='mono'>{r['type']}</td>"
            f"</tr>"
            for r in items
        )
        family_sections.append(f"""
<h2>{html.escape(fam)} <span class="muted" style="font-size:.7em">{len(items)} entries</span></h2>
<table class="data">
  <thead><tr><th>id</th><th>Symbolic name</th><th>.atd (skeleton/anim)</th><th>.cpd (mesh)</th><th>type</th></tr></thead>
  <tbody>
    {body_rows}
  </tbody>
</table>
""")

    type_legend_rows = "".join(
        f"<tr><td class='mono'>{t}</td><td>{html.escape(TYPE_LABELS.get(t,'?'))}</td><td class='mono'>{c}</td></tr>"
        for t, c in sorted(type_hist.items())
    )

    body = f"""
<h1>Asset Bundles</h1>
<p class="dim">{len(rows)} entity registrations from <code>crsid.crs</code> (CRSD). Each row is the loader's contract for materializing one playable, enemy, NPC, or special object: an integer id, a symbolic name, and the <code>.atd</code> (skeleton + animation tracks) and <code>.cpd</code> (mesh / part-data) files to load from <code>resource/</code>.</p>

<div class="stat-grid">
  <div class="stat"><span class="num">{len(rows)}</span><span class="label">CRSD rows</span></div>
  <div class="stat"><span class="num">{type_hist.get(1,0) + type_hist.get(0,0):,}</span><span class="label">PCs + enemy slots (type 0/1)</span></div>
  <div class="stat"><span class="num">{type_hist.get(4,0):,}</span><span class="label">NPCs / monsters (type 4)</span></div>
  <div class="stat"><span class="num">{crsd['index_count']}</span><span class="label">Unique ids</span></div>
</div>

<div class="note">
  <strong>How CRSD slots into the engine.</strong> When the server tells the client to spawn an entity, it sends an integer id from this table. The loader looks up the row, gets the symbolic name (e.g. <code>NN046</code>), and loads <code>resource/{{atd}}</code> for the skeleton + animation tracks plus <code>{{cpd}}</code> for the mesh. NNTB (below) inserts a name-canonicalization step in front of this lookup so that variants like <code>ZMK_S01..ZMK_S05</code> all resolve to one shared bundle.
</div>

<h2>Type legend</h2>
<table class="data" style="max-width:32em">
  <thead><tr><th>type_code</th><th>Meaning</th><th>Count</th></tr></thead>
  <tbody>
    {type_legend_rows}
  </tbody>
</table>

{aliases_html}

{''.join(family_sections)}

<div class="note">
  Format spec: <code>Yu-TOEOE/assets/specs/crsd_format.md</code> (header layout, validator pseudocode, cipher: per-record Blowfish-ECB + LE-swap, key=<code>"crs text"</code>; integrity: stock SHA-1). Sibling NNTB spec at <code>specs/nntb_format.md</code>. Decoded Track A Session 6, 2026-05-07.
</div>
"""
    out = ROOT / "bundles" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_html(out, page("Asset Bundles", body, "/bundles/index.html", depth=1))
    print(f"  CRSD: {len(rows)} rows across {len([f for f in family_order if by_family.get(f)])} families - NNTB aliases: {len(nntb['non_identity_aliases']) if nntb else 0}")


# ---------- Zones (NEW) ------------------------------------------------------

def build_zones(zones):
    if zones is None:
        print("  (no zones JSON — skipping zones page)")
        return

    main_zones = zones["mpi_zones"]
    minimaps = zones["minimap_cells"]
    groups = zones["groups"]
    known_places = zones["known_place_names_from_bgm"]

    # Group minimaps (the things with actual images) by region label
    mm_by_group: dict[str, list] = defaultdict(list)
    for m in minimaps:
        mm_by_group[m["group_label"]].append(m)
    # Group main zone IDs by region label (for sidebar reference list)
    main_by_group: dict[str, list] = defaultdict(list)
    for z in main_zones:
        main_by_group[z["group_label"]].append(z["zone_id"])

    minimap_dir = ROOT / "static" / "minimaps"
    available = set(p.stem for p in minimap_dir.glob("*.png")) if minimap_dir.exists() else set()

    def mm_card(mm_id: str, group_label: str):
        if mm_id in available:
            img = f'<img src="../static/minimaps/{mm_id}.png" alt="" loading="lazy">'
            frame_class = ""
        else:
            img = '<span>no minimap</span>'
            frame_class = " empty"
        return f"""
        <div class="zone-card" data-search="{html.escape(mm_id + ' ' + group_label)}">
          <div class="map-frame{frame_class}">{img}</div>
          <div class="zone-meta">
            <div class="zone-id">{html.escape(mm_id)}</div>
            <div class="zone-group">{html.escape(group_label)}</div>
          </div>
        </div>"""

    # Per-region sections — show minimap cells (real images) + the .mpi IDs that share the same prefix
    region_sections = []
    for label in sorted(set(list(mm_by_group.keys()) + list(main_by_group.keys()))):
        mm_list = mm_by_group.get(label, [])
        main_list = main_by_group.get(label, [])
        cards = "".join(mm_card(m["minimap_id"], label) for m in mm_list)
        main_html = ""
        if main_list:
            ids_html = " ".join(f'<code>{mid}</code>' for mid in main_list)
            main_html = f'<p class="dim small">Associated <code>.mpi</code> main maps in this region: {ids_html}</p>'
        if not (cards or main_list):
            continue
        region_sections.append(f"""
<h3>{html.escape(label)} <span class="muted small">{len(mm_list)} minimap cell{"s" if len(mm_list)!=1 else ""}{f" · {len(main_list)} main maps" if main_list else ""}</span></h3>
{main_html}
<div class="zone-grid">{cards}</div>""")

    # Known place names callout
    known_html = ""
    if known_places:
        rows = "".join(f"<li>{html.escape(p)}</li>" for p in known_places)
        known_html = f"""
<h2>Recovered place names</h2>
<div class="note">
  Each music file in <code>resource/MSC_*.dat</code> is named for the zone or scene where it plays. Cross-referenced against <em>Tales of Eternia</em> lore (the parallel worlds <strong>Inferia</strong> and <strong>Celestia</strong>), these names map onto the Tales franchise's familiar geography. The disc shipped no table linking these names to numeric zone IDs — that mapping requires play-testing.
</div>
<ul style="columns:2; column-gap:2rem; max-width:52em; margin-top:.5rem;">
{rows}
</ul>"""

    body = f"""
<h1>Zones</h1>
<p class="dim">Every world location TOEO shipped with: <strong>{len(minimaps)} minimap cells</strong> (256×256 BNKD-extracted PNGs from <code>map/minimap/*.bnd</code>) plus <strong>{len(main_zones)} main map files</strong> (<code>.mpi</code> zone-level geometry). Minimap cells are the visual atlas; the <code>.mpi</code> files contain the playable geometry.</p>

<div class="stat-grid">
  <div class="stat"><span class="num">{len(minimaps)}</span><span class="label">Minimap cells</span></div>
  <div class="stat"><span class="num">{len(main_zones)}</span><span class="label">Main map files</span></div>
  <div class="stat"><span class="num">{len(groups)}</span><span class="label">Region groups</span></div>
  <div class="stat"><span class="num">{len(known_places)}</span><span class="label">Named places</span></div>
</div>

<div class="note">
  <strong>About zone identity.</strong> Numeric IDs (e.g. <code>1120101</code>) follow Sigma's internal region-encoding scheme. The disc shipped no name table linking IDs to playable place names — that mapping requires play-testing the live regions. Below, zones are grouped by their 3-digit prefix as a best-guess continent / region cluster.
</div>

{known_html}

<h2>Region atlas <span class="muted" style="font-size:.7em">all minimap cells · grouped by region prefix</span></h2>
{''.join(region_sections)}
"""
    out = ROOT / "zones" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_html(out, page("Zones", body, "/zones/index.html", depth=1))
    print(f"  zones: {len(minimaps)} minimap cells + {len(main_zones)} .mpi maps across {len(groups)} groups")


# ---------- Audio catalog ----------------------------------------------------

# Hand-curated English glosses for the Tales-of-Eternia-derived BGM track names.
# These are speculative-but-reasonable readings based on the parent franchise's
# established geography (Inferia / Celestia, Rasheans, Mints, Barole, Inferia
# Castle, etc.). Anything we cannot confidently identify is left blank.
MSC_GLOSS = {
    "MAIN_TITLE":           "Main title theme",
    "RASHAN":               "Rasheans (Inferia starting town)",
    "MINTS":                "Mints (town)",
    "MT_MINTS":             "Mt. Mints (mountain area)",
    "BAROLE":               "Barole (town)",
    "MORUL":                "Morul",
    "INFERIER_FIELD":       "Inferia overworld field",
    "INFERIER_CASTLE":      "Inferia Castle",
    "FARROWS_RUINS":        "Farrow's Ruins",
    "DRAGON_ROCK_MOUNTAI":  "Dragon Rock Mountain",
    "TEMPTATION_FOREST":    "Temptation Forest",
    "WATIE_STREAM":         "Watie Stream",
    "REGULUS_TEMPLE":       "Regulus Temple",
    "SEYFERT_CHURCH":       "Seyfert Church (faith of Seyfert)",
    "LEM_THEME":            "Lem character theme",
    "BAR":                  "Bar / tavern interior",
    "PORT":                 "Port",
    "SHIP":                 "Aboard ship",
    "INFERIA_BATTLE":       "Inferia battle BGM",
    "MIDDLE_BOSS1":         "Mid-boss battle 1",
    "MIDDLE_BOSS2":         "Mid-boss battle 2",
    "CRISIS":               "Crisis / urgent scene",
    "HURRY_UP":             "Tense / chase",
    "DISCOURAGE":           "Discouragement / loss",
    "EASYGOING":            "Lighthearted / casual",
    "CARD_GAME":            "Card minigame",
    "MINIGAME1":            "Minigame 1",
    "MINIGAME2":            "Minigame 2",
    "ORGEL_1":              "Music box (orgel)",
}

BATTLE_AUDIO_GROUPS = [
    (
        "Character battle voices",
        "Short combat voice clips used by the client battle-voice system. The recovered examples are generic battle lines; arte-name callouts such as Majinken / Demon Fang have not been recovered.",
        ["BC003_0011", "BC003_0111"],
    ),
    (
        "Weapon swings and effort sounds",
        "Likely combat effort, swing, strike, down, and impact cues from the regular SE pool.",
        [
            "SE_SLASH1", "SE_SLASH2", "SE_SLASH3",
            "SE_SWING_WIDE1", "SE_SWING_WIDE2",
            "SE_THRUST1", "SE_THRUST2", "SE_THRUST3",
            "SE_KICK1", "SE_KICK2", "SE_KICK3",
            "SE_BLOW1", "SE_BLOW2", "SE_BLOW3",
            "SE_UNARI", "SE_UNARI2", "SE_DOWN", "SE_ENE_HIT",
        ],
    ),
]


def _audio_inventory():
    """Walk toeo/data/resource/ and bucket audio .dat files by filename prefix."""
    res_candidates = [
        ROOT.parents[1] / "toeo" / "data" / "resource",
        Path("/mnt/c/Users/songs/Desktop/project/toeo/data/resource"),
    ]
    buckets: dict[str, list[tuple[str, int]]] = {
        "Music (MSC_)":           [],
        "Battle voices (BC_)":     [],
        "Sound effects (SE_)":    [],
        "Environmental (ENV_)":   [],
        "Jingles":                [],
        "Other audio":            [],
    }
    res = next((p for p in res_candidates if p.exists()), None)
    if res is None:
        return _audio_inventory_from_static()
    for p in sorted(res.glob("*.dat")):
        n = p.name
        sz = p.stat().st_size
        if n.startswith("MSC_"):
            buckets["Music (MSC_)"].append((n, sz))
        elif n.startswith("BC"):
            buckets["Battle voices (BC_)"].append((n, sz))
        elif n.startswith("SE_"):
            buckets["Sound effects (SE_)"].append((n, sz))
        elif n.startswith("ENV_"):
            buckets["Environmental (ENV_)"].append((n, sz))
        elif n.startswith("JINGLE_"):
            buckets["Jingles"].append((n, sz))
    return buckets


def _audio_inventory_from_static():
    """Fallback for GitHub Pages rebuilds where source .dat files are absent."""
    audio_root = ROOT / "static" / "audio"
    buckets: dict[str, list[tuple[str, int]]] = {
        "Music (MSC_)":           [],
        "Battle voices (BC_)":     [],
        "Sound effects (SE_)":    [],
        "Environmental (ENV_)":   [],
        "Jingles":                [],
        "Other audio":            [],
    }
    if not audio_root.exists():
        return buckets
    static_to_bucket = {
        "music": "Music (MSC_)",
        "voice": "Battle voices (BC_)",
        "se": "Sound effects (SE_)",
        "env": "Environmental (ENV_)",
        "jingle": "Jingles",
    }
    for subdir, bucket in static_to_bucket.items():
        d = audio_root / subdir
        if not d.exists():
            continue
        for p in sorted(d.iterdir()):
            if not p.is_file():
                continue
            buckets[bucket].append((f"{p.stem}.dat", p.stat().st_size))
    return buckets


def build_audio_catalog():
    buckets = _audio_inventory()
    total = sum(len(v) for v in buckets.values())
    if total == 0:
        print("  (no audio dir found — skipping audio catalog)")
        return

    def fmt_kb(b): return f"{b/1024:.1f} KB" if b < 1024*1024 else f"{b/1024/1024:.1f} MB"

    # Map category → (audio subdir, file extension) for the playable links
    cat_to_audio = {
        "Music (MSC_)":           ("music", "ogg"),
        "Battle voices (BC_)":     ("voice", "wav"),
        "Sound effects (SE_)":    ("se",    "wav"),
        "Environmental (ENV_)":   ("env",   "ogg"),
        "Jingles":                ("jingle","wav"),
    }
    audio_root = ROOT / "static" / "audio"

    size_by_stem = {n[:-4]: sz for files in buckets.values() for n, sz in files}

    def audio_button(stem, subdir, ext):
        audio_path = audio_root / subdir / f"{stem}.{ext}"
        if not audio_path.exists():
            return "", 0
        src = f"../static/audio/{subdir}/{stem}.{ext}"
        return (
            f'<audio preload="none" src="{html.escape(src)}"></audio>'
            f'<button class="play-btn" type="button" '
            f'onclick="togglePlay(this)" aria-label="Play {html.escape(stem)}">'
            f'<span class="play-icon">▶</span></button>'
        ), 1

    combat_sections = []
    combat_play_count = 0
    for title, note, stems in BATTLE_AUDIO_GROUPS:
        cells = []
        for stem in stems:
            subdir, ext = ("voice", "wav") if stem.startswith("BC") else ("se", "wav")
            btn_html, playable = audio_button(stem, subdir, ext)
            combat_play_count += playable
            sz = size_by_stem.get(stem)
            sub_html = f'<span class="a-sub muted">{fmt_kb(sz) if sz else "referenced cue"}</span>'
            cells.append(f"""
            <div class="audio-cell combat-audio" data-search="{html.escape((stem + ' ' + title).lower())}">
              <div class="a-row">
                {btn_html}
                <div class="a-text">
                  <span class="a-name">{html.escape(stem)}</span>
                  {sub_html}
                </div>
              </div>
            </div>""")
        combat_sections.append(f"""
<h3>{html.escape(title)} <span class="muted" style="font-size:.72em">{len(stems)} cue{'s' if len(stems)!=1 else ''}</span></h3>
<p class="dim">{html.escape(note)}</p>
<div class="audio-grid audio-grid-compact">{''.join(cells)}</div>""")

    sections = []
    play_count = 0
    for cat, files in buckets.items():
        if not files: continue
        subdir, ext = cat_to_audio.get(cat, (None, None))
        cells = []
        for n, sz in files:
            stem = n[:-4]
            parts = stem.split("_", 1)
            sub = parts[1] if len(parts) > 1 else stem
            gloss = MSC_GLOSS.get(sub) if cat.startswith("Music") else None
            sub_html = (
                f'<span class="a-sub">{html.escape(gloss)}</span>' if gloss
                else f'<span class="a-sub muted">{fmt_kb(sz)}</span>'
            )
            # Playable link if file exists in static dir
            audio_html = ""
            if subdir:
                audio_html, playable = audio_button(stem, subdir, ext)
                play_count += playable
            cells.append(f"""
            <div class="audio-cell" data-search="{html.escape(stem.lower())}">
              <div class="a-row">
                {audio_html}
                <div class="a-text">
                  <span class="a-name">{html.escape(stem)}</span>
                  {sub_html}
                </div>
              </div>
            </div>""")
        sections.append(f"""
<h2>{html.escape(cat)} <span class="muted" style="font-size:.7em">{len(files)} file{'s' if len(files)!=1 else ''}</span></h2>
<div class="audio-grid">{''.join(cells)}</div>""")

    body = f"""
<h1>Audio</h1>
<p class="dim">{total} audio files shipped on the original disc, stored as <code>resource/*.dat</code> (filename extension is opaque; contents are stock <strong>WAV</strong> for SE/jingles and <strong>WMA / ASF</strong> for music + environmentals). Filenames are descriptive English tokens — Sigma's sound team's internal names — and many double as a place-name index for zones with no other identifying string in the client. Click ▶ to listen; music tracks were transcoded to OGG for browser playback.</p>

<div class="stat-grid">
  <div class="stat"><span class="num">{len(buckets["Music (MSC_)"])}</span><span class="label">Music tracks</span></div>
  <div class="stat"><span class="num">{len(buckets["Battle voices (BC_)"])}</span><span class="label">Battle voices</span></div>
  <div class="stat"><span class="num">{len(buckets["Sound effects (SE_)"])}</span><span class="label">Sound effects</span></div>
  <div class="stat"><span class="num">{len(buckets["Environmental (ENV_)"])}</span><span class="label">Environmental</span></div>
  <div class="stat"><span class="num">{len(buckets["Jingles"])}</span><span class="label">Jingles / stingers</span></div>
</div>

<div class="note">
  <strong>Music names = zone names.</strong> Each <code>MSC_*.dat</code> track plays in a specific area or scene; cross-referenced with <em>Tales of Eternia</em> franchise lore where the parent game's geography (Inferia / Celestia / Rasheans / Mints / Barole) matches verbatim. Glosses below are best-effort readings; areas without a confident match show the raw token.
</div>

<div class="audio-toolbar">
  <input type="search" class="search-inline" placeholder="Filter by name…" oninput="audioFilter(this.value)">
  <button class="stop-all" type="button" onclick="stopAll()">⏹ Stop all</button>
</div>

<h2>Combat voice and weapon audio <span class="muted" style="font-size:.7em">{sum(len(g[2]) for g in BATTLE_AUDIO_GROUPS)} curated cues</span></h2>
<div class="note">
  <strong>Player combat audio.</strong> The recovered <code>BC*</code> files are generic character battle voices, not confirmed arte-name callouts. Swing, thrust, kick, blow, down, and hit cues come from the regular <code>SE_*</code> sound-effect pool.
</div>
{''.join(combat_sections)}

{''.join(sections)}

<script>
function audioFilter(q) {{
  q = q.trim().toLowerCase();
  for (const c of document.querySelectorAll('.audio-cell')) {{
    const t = (c.dataset.search || c.textContent).toLowerCase();
    c.style.display = (!q || t.includes(q)) ? '' : 'none';
  }}
}}
let _currentAudio = null;
function togglePlay(btn) {{
  const cell = btn.closest('.audio-cell');
  const audio = cell.querySelector('audio');
  if (!audio) return;
  if (_currentAudio && _currentAudio !== audio) {{
    _currentAudio.pause();
    _currentAudio.currentTime = 0;
    const otherBtn = _currentAudio.parentNode.querySelector('.play-btn');
    if (otherBtn) {{ otherBtn.classList.remove('playing'); otherBtn.querySelector('.play-icon').textContent = '▶'; }}
  }}
  if (audio.paused) {{
    audio.play();
    btn.classList.add('playing');
    btn.querySelector('.play-icon').textContent = '❚❚';
    _currentAudio = audio;
    audio.onended = () => {{
      btn.classList.remove('playing');
      btn.querySelector('.play-icon').textContent = '▶';
      _currentAudio = null;
    }};
  }} else {{
    audio.pause();
    btn.classList.remove('playing');
    btn.querySelector('.play-icon').textContent = '▶';
  }}
}}
function stopAll() {{
  for (const a of document.querySelectorAll('audio')) {{ a.pause(); a.currentTime = 0; }}
  for (const b of document.querySelectorAll('.play-btn.playing')) {{
    b.classList.remove('playing');
    b.querySelector('.play-icon').textContent = '▶';
  }}
  _currentAudio = null;
}}
</script>
"""
    out = ROOT / "audio" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_html(out, page("Audio", body, "/audio/index.html", depth=1))
    print(f"  audio: {len(buckets['Music (MSC_)'])} music - {len(buckets['Battle voices (BC_)'])} voice - {len(buckets['Sound effects (SE_)'])} SE - {len(buckets['Environmental (ENV_)'])} env - {len(buckets['Jingles'])} jingles  ({play_count + combat_play_count} playable including curated)")


# ---------- Icon copy --------------------------------------------------------

def copy_icons():
    """Copy extracted icons into the wiki static dir.

    Icons are referenced by per-category folder + slot number (e.g. Weapon/00000.png).
    Total ~3125 PNGs, ~11 MB.
    """
    if not ICONS_SRC.exists():
        print(f"  (no icon source at {ICONS_SRC} — skipping)")
        return 0
    if ICONS_DST.exists():
        shutil.rmtree(ICONS_DST)
    shutil.copytree(ICONS_SRC, ICONS_DST)
    n = sum(1 for _ in ICONS_DST.rglob("*.png"))
    print(f"  copied {n} icons -> {ICONS_DST.relative_to(ROOT)}")
    return n


# ---------- Main -------------------------------------------------------------

def main():
    print(f"# Building TOEO Asset Wiki at {ROOT}")
    print(f"  reading data from {ASSETS}")

    cid0, cid1, tdab, crsd, nntb, zones = load_data()
    crsd_n = len(crsd['rows']) if crsd else 0
    zones_n = len(zones['mpi_zones']) if zones else 0
    print(f"  cid0={len(cid0)} ids - cid1={len(cid1)} ids - tdab={tdab['action_count']} actions - crsd={crsd_n} rows - zones={zones_n}")

    print("\n[1/9] copying icons…")
    copy_icons()

    print("[2/9] index.html")
    write_html(ROOT / "index.html", build_index(cid0, cid1, tdab))

    print("[3/9] equipment/")
    build_equipment(cid1)

    print("[4/9] beasts/")
    build_beasts(cid0)

    print("[5/9] npcs/")
    build_npcs(cid0)

    print("[6/9] actions/ + about.html")
    build_actions(tdab)
    build_about()

    print("[7/9] bundles/")
    build_bundles(crsd, nntb)

    print("[8/9] zones/")
    build_zones(zones)

    print("[9/9] audio/")
    build_audio_catalog()

    # Sanity report
    pages = list(ROOT.rglob("*.html"))
    print(f"\n  generated {len(pages)} HTML pages")
    total_bytes = sum(p.stat().st_size for p in pages)
    print(f"  total HTML size: {total_bytes/1024:.1f} KB")
    print(f"  open: file://{ROOT.resolve()}/index.html")


if __name__ == "__main__":
    main()
