// OmniRiff brand kit: the pixel mark, the wordmark and the icon set, as string grids.
// Rules are in BRAND_SPEC.md (section 6, pixel art). One cell is one pixel; nothing here
// is drawn with curves. The page calls OmniBrand.mount() to fill <i data-icon>, <span data-logo>.
//
//   node dashboard/brand.js --export     rewrites dashboard/brand/*.svg from these grids
'use strict';

(function (root) {
  // '#' body, 'o' eye (ink), '+' glint (paper), '.' empty
  const MARK = [
    '...####..####...',
    '..############..',
    '.##############.',
    '################',
    '################',
    '####o+####o+####',
    '####oo####oo####',
    '.###oo####oo###.',
    '.###oo####oo###.',
    '################',
    '################',
    '################',
    '################',
    '.##############.',
    '..############..',
    '...####..####...',
  ];

  // wordmark glyphs, 7 rows, 2-cell stems
  const GLYPHS = {
    O: ['.####.', '##..##', '##..##', '##..##', '##..##', '##..##', '.####.'],
    M: ['##...##', '###.###', '#######', '##.#.##', '##...##', '##...##', '##...##'],
    N: ['##..##', '###.##', '###.##', '######', '##.###', '##.###', '##..##'],
    I: ['##', '##', '##', '##', '##', '##', '##'],
    R: ['#####.', '##..##', '##..##', '#####.', '##.##.', '##..##', '##..##'],
    F: ['######', '##....', '##....', '#####.', '##....', '##....', '##....'],
  };

  // 8x8 icons, one per module or input
  const ICONS = {
    loop: ['.####.#.', '#....##.', '#...###.', '#......#', '#......#', '#......#', '.######.', '........'],
    tone: ['........', '.##.....', '#..#...#', '#..#...#', '....#..#', '....#..#', '.....##.', '........'],
    hand: ['..#.#...', '..#.#.#.', '#.#.#.#.', '#.#####.', '#######.', '.######.', '.#####..', '..###...'],
    coach: ['.##..##.', '########', '#.##.###', '#.##.###', '########', '########', '########', '.##..##.'],
    pedal: ['........', '..####..', '.######.', '.######.', '..####..', '########', '#......#', '########'],
    cam: ['........', '#####...', '#####.##', '########', '########', '#####.##', '#####...', '........'],
  };

  function rects(grid, colors, ox, oy, s) {
    let out = '';
    grid.forEach((row, y) => {
      // merge horizontal runs of the same cell type into one rect
      for (let x = 0; x < row.length;) {
        const ch = row[x];
        let n = 1;
        while (x + n < row.length && row[x + n] === ch) n++;
        if (colors[ch]) out += `<rect x="${ox + x * s}" y="${oy + y * s}" width="${n * s}" height="${s}" fill="${colors[ch]}"/>`;
        x += n;
      }
    });
    return out;
  }
  const svg = (w, h, body, label) =>
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" shape-rendering="crispEdges"` +
    (label ? ` role="img" aria-label="${label}"` : ' aria-hidden="true"') + `>${body}</svg>`;

  const PAL = { pink: '#FF5CCB', ink: '#0B0B10', paper: '#ECE9F5' };
  const markColors = (p) => ({ '#': p.pink, o: p.ink, '+': p.paper });

  function mark(p = PAL) { return svg(16, 16, rects(MARK, markColors(p), 0, 0, 1), 'OmniRiff'); }

  function wordmarkBody(text, p, ox, oy, s) {
    let x = ox, out = '';
    for (let i = 0; i < text.length; i++) {
      const g = GLYPHS[text[i]];
      out += rects(g, { '#': i < 4 ? p.paper : p.pink }, x, oy, s);
      x += (g[0].length + 1) * s;
    }
    return [out, x - s];
  }
  // lockup: mark (16 cells) + 3 cells of air + wordmark (7 rows, vertically centred, 1 cell = 1 unit)
  function logo(p = PAL) {
    const [w, endX] = wordmarkBody('OMNIRIFF', p, 20, 4, 1);
    return svg(endX, 16, rects(MARK, markColors(p), 0, 0, 1) + w, 'OmniRiff');
  }
  function wordmark(p = PAL) {
    const [w, endX] = wordmarkBody('OMNIRIFF', p, 0, 0, 1);
    return svg(endX, 7, w, 'OmniRiff');
  }
  function icon(name) {
    const g = ICONS[name];
    return g ? svg(8, 8, rects(g, { '#': 'currentColor' }, 0, 0, 1)) : '';
  }

  // browser: fill placeholders. Sizes are set in CSS and must be whole multiples of the grid.
  function mount(scope) {
    const d = scope || document;
    d.querySelectorAll('[data-icon]').forEach((el) => { el.innerHTML = icon(el.dataset.icon); });
    d.querySelectorAll('[data-logo]').forEach((el) => {
      el.innerHTML = el.dataset.logo === 'mark' ? mark() : el.dataset.logo === 'wordmark' ? wordmark() : logo();
    });
  }

  const api = { MARK, GLYPHS, ICONS, PAL, mark, logo, wordmark, icon, mount };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
    if (require.main === module && process.argv.includes('--export')) {
      const fs = require('fs'), path = require('path');
      const dir = path.join(__dirname, 'brand');
      fs.mkdirSync(dir, { recursive: true });
      const onPink = { pink: PAL.ink, ink: PAL.pink, paper: PAL.pink };
      const tile = (inner, bg) =>
        `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" shape-rendering="crispEdges" role="img" aria-label="OmniRiff">` +
        `<rect width="24" height="24" fill="${bg}"/>${inner}</svg>`;
      const files = {
        'mark.svg': mark(),
        'logo.svg': logo(),
        'wordmark.svg': wordmark(),
        'logo-on-light.svg': logo({ pink: PAL.pink, ink: PAL.ink, paper: PAL.ink }),
        'favicon.svg': tile(rects(MARK, markColors(PAL), 4, 4, 1), PAL.ink),
        'app-icon.svg': tile(rects(MARK, markColors(onPink), 4, 4, 1), PAL.pink),
      };
      for (const [name, body] of Object.entries(files)) fs.writeFileSync(path.join(dir, name), body + '\n');
      console.log('wrote', Object.keys(files).join(', '), 'to', dir);
    }
  } else {
    root.OmniBrand = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
