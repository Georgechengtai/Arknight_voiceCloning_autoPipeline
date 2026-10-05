// 劇情畫面渲染器。只讀 schedule.json（pipeline/render/schedule.py 產生），不自己算節奏。
// window.renderer.load(schedule, base) → Promise；window.renderer.seek(t_ms) 同步畫出該時刻的畫面。
// seek 是確定性的：先把「這一刻畫面上有什麼」算成一個純資料的狀態，再照狀態畫；
// 狀態與上一次相同時不重畫並回傳 false，呼叫端可以沿用上一張截圖。
(function () {
  "use strict";
  const R = (window.renderer = { schedule: null, missing: [] });
  let S, canvas, ctx, K, W, H, FONT;
  let lastKey = null;
  const images = {};
  const layouts = new Map();

  const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);
  const lerp = (a, b, k) => a + (b - a) * k;
  const r3 = (v) => Math.round(v * 1000) / 1000;
  const r2 = (v) => Math.round(v * 100) / 100;
  const r4 = (v) => Math.round(v * 10000) / 10000;
  const progress = (t, t0, dur) => (dur > 0 ? clamp01((t - t0) / dur) : t >= t0 ? 1 : 0);
  const lastAt = (list, t, key) => {
    let hit = null;
    for (const it of list) {
      if ((key ? it[key] : it.t) <= t) hit = it;
      else break;
    }
    return hit;
  };

  R.load = async function (schedule, base) {
    S = R.schedule = schedule;
    base = base || "/";
    canvas = document.getElementById("stage");
    canvas.width = W = S.width;
    canvas.height = H = S.height;
    ctx = canvas.getContext("2d");
    K = S.width / S.coord.w;
    FONT = S.style.fonts.map((f) => (f.includes(" ") ? `"${f}"` : f)).join(", ");
    lastKey = null;
    layouts.clear();

    const srcs = new Set();
    const L = S.layers;
    for (const b of L.backgrounds.concat(L.images)) if (b.src) srcs.add(b.src);
    for (const sp of L.sprites) for (const im of sp.images) if (im.src) srcs.add(im.src);
    await Promise.all(
      [...srcs].map(async (src) => {
        const img = new Image();
        img.src = base + src;
        try {
          await img.decode();
          images[src] = img;
        } catch (e) {
          R.missing.push(src);
        }
      })
    );
    if (document.fonts && document.fonts.load) {
      await document.fonts.load(`24px ${FONT}`, "明日方舟");
      await document.fonts.ready;
    }
    R.seek(0);
    return true;
  };

  // ── 某一刻的畫面狀態（純資料） ──

  function layerState(list, t) {
    const cur = lastAt(list, t);
    if (!cur || !cur.key) return null;
    let v = [cur.x, cur.y, cur.xscale, cur.yscale];
    const tw = lastAt(cur.tweens, t);
    if (tw) {
      const k = progress(t, tw.t, tw.dur);
      v = tw.from.map((f, n) => lerp(f, tw.to[n], k));
    }
    return { key: cur.key, src: images[cur.src] ? cur.src : null, a: r3(progress(t, cur.t, cur.fade)),
             x: r2(v[0]), y: r2(v[1]), sx: r4(v[2]), sy: r4(v[3]) };
  }

  function spriteState(sp, t) {
    if (t < sp.t0 || t >= sp.t1) return null;
    let a = progress(t, sp.t0, sp.fade_in);
    if (sp.fade_out > 0) a *= clamp01((sp.t1 - t) / sp.fade_out);
    const al = lastAt(sp.alphas, t);
    if (al) a *= lerp(al.from, al.to, progress(t, al.t, al.dur));
    let dx = 0, dy = 0;
    const mv = lastAt(sp.moves, t);
    if (mv) {
      const k = progress(t, mv.t, mv.dur);
      dx = lerp(mv.from[0], mv.to[0], k);
      dy = lerp(mv.from[1], mv.to[1], k);
    }
    for (const sh of sp.shakes) {
      const tau = t - sh.t;
      if (tau >= 0 && tau < sh.dur) dx += sh.power * Math.sin(Math.PI * sh.times * (tau / sh.dur) * 0.37 + 1);
    }
    const im = lastAt(sp.images, t);
    const lit = lastAt(sp.lit.map((p) => ({ t: p[0], on: p[1] })), t);
    if (a <= 0) return null;
    return { name: im.name, src: images[im.src] ? im.src : null, x: r2(sp.x + dx), cy: r2(sp.cy - dy),
             size: sp.size, a: r3(a), dim: lit && !lit.on ? S.style.dim_brightness : 1 };
  }

  function typed(text, t, t0, charS, from) {
    const total = Array.from(text).length;
    if (!(charS > 0)) return total;
    return Math.min(total, (from || 0) + Math.floor((t - t0) / charS + 1e-6) + 1);
  }

  function stateAt(t) {
    const L = S.layers;
    if (S.intro && t < S.intro.dur) {
      const f = S.intro.fade;
      return { intro: r3(f > 0 ? Math.min(clamp01(t / f), clamp01((S.intro.dur - t) / f)) : 1) };
    }
    const st = {};
    let cx = 0, cy = 0, amp = 0;
    for (const sh of L.shakes) {
      const tau = t - sh.t;
      if (tau < 0 || tau >= sh.dur) continue;
      const decay = sh.fadeout ? 1 - tau / sh.dur : 1;
      const w = 2 * Math.PI * sh.vibrato * 0.37 * tau;
      cx += sh.xs * decay * Math.sin(w + 1);
      cy += sh.ys * decay * Math.sin(w * 1.31 + 2);
      amp = Math.max(amp, Math.max(sh.xs, sh.ys) * decay);
    }
    st.cam = [r2(cx), r2(cy), r2(amp)];
    st.bg = layerState(L.backgrounds, t);
    st.img = layerState(L.images, t);
    // 立繪站得近、會互相遮到：壓暗的先畫，正在說話（亮）的畫在上面
    st.sprites = L.sprites.map((sp) => spriteState(sp, t)).filter(Boolean)
      .sort((a, b) => (a.dim < 1 ? 0 : 1) - (b.dim < 1 ? 0 : 1));

    const b = lastAt(L.blockers, t);
    st.blocker = b ? b.from.map((f, n) => r3(lerp(f, b.to[n], progress(t, b.t, b.dur)))) : [0, 0, 0, 0];

    st.texts = [];
    for (const s of L.stickers.concat(L.subtitles)) {
      if (t < s.t0 || t >= s.t1) continue;
      const a = s.fade_out > 0 ? clamp01((s.t1 - t) / s.fade_out) : 1;
      st.texts.push({ text: s.text, n: typed(s.text, t, s.t0, s.char_s), a: r3(a), x: s.x, y: s.y,
                      width: s.width, size: s.size, align: s.alignment });
    }
    const d = L.dialogs.find((x) => t >= x.t0 && t < x.t1);
    st.dialog = d ? { name: d.name, text: d.text, n: typed(d.text, t, d.t0, d.char_s, d.type_from) } : null;
    return st;
  }

  R.stateAt = (tMs) => stateAt(tMs / 1000);

  R.seek = function (tMs) {
    const st = stateAt(tMs / 1000);
    const key = JSON.stringify(st);
    if (key === lastKey) return false;
    lastKey = key;
    draw(st);
    return true;
  };

  // ── 畫 ──

  function font(px, weight) {
    ctx.font = `${weight || 400} ${px}px ${FONT}`;
  }

  // 逐字斷行（中文）；行首不放收尾的標點
  const NO_LINE_START = "，。！？、；：”’）》」』…—";
  function layout(text, px, width) {
    const key = `${px}|${width}|${text}`;
    let lines = layouts.get(key);
    if (lines) return lines;
    font(px);
    lines = [];
    for (const para of text.split("\n")) {
      let cur = "";
      for (const ch of Array.from(para)) {
        if (cur && ctx.measureText(cur + ch).width > width && !NO_LINE_START.includes(ch)) {
          lines.push(cur);
          cur = ch;
        } else cur += ch;
      }
      lines.push(cur);
    }
    lines = lines.map((s) => ({ s, w: ctx.measureText(s).width, n: Array.from(s).length }));
    layouts.set(key, lines);
    return lines;
  }

  function drawText(text, n, x, y, width, px, lineH, align, color) {
    const lines = layout(text, px, width);
    font(px);
    ctx.fillStyle = color;
    ctx.textBaseline = "top";
    ctx.textAlign = "left";
    let left = n;
    lines.forEach((ln, k) => {
      if (left <= 0) return;
      const x0 = align === "center" ? x + (width - ln.w) / 2 : align === "right" ? x + width - ln.w : x;
      const s = left >= ln.n ? ln.s : Array.from(ln.s).slice(0, left).join("");
      ctx.fillText(s, x0, y + k * lineH);
      left -= ln.n;
    });
  }

  function hue(s) {
    let h = 0;
    for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360;
    return h;
  }

  function drawLayer(ly, cam, kind) {
    const cw = S.coord.w, ch = S.coord.h;
    const img = ly.src && images[ly.src];
    const iw = img ? img.naturalWidth : cw, ih = img ? img.naturalHeight : ch;
    const fit = Math.max(cw / iw, ch / ih) * (1 + (2 * cam[2]) / ch);   // 鋪滿畫面；震動時略放大，不露黑邊
    ctx.save();
    ctx.globalAlpha = ly.a;
    ctx.translate(cw / 2 + ly.x + cam[0], ch / 2 - ly.y + cam[1]);
    ctx.scale(fit * ly.sx, fit * ly.sy);
    if (img) ctx.drawImage(img, -iw / 2, -ih / 2);
    else {
      // 缺素材：色塊＋文字佔位
      ctx.fillStyle = `hsl(${hue(ly.key)}, 22%, ${kind === "背景" ? 20 : 28}%)`;
      ctx.fillRect(-iw / 2, -ih / 2, iw, ih);
      font(20);
      ctx.fillStyle = "rgba(255,255,255,0.55)";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(`${kind}（缺素材）：${ly.key}`, 0, kind === "背景" ? -ih / 2 + 40 : 0);
    }
    ctx.restore();
  }

  function drawSprite(sp, cam) {
    const img = sp.src && images[sp.src];
    const x = sp.x + cam[0], top = sp.cy - sp.size / 2 + cam[1];
    ctx.save();
    ctx.globalAlpha = sp.a;
    if (img) {
      if (sp.dim < 1) ctx.filter = `brightness(${sp.dim})`;
      ctx.drawImage(img, x - sp.size / 2, top, sp.size, sp.size);
    } else {
      const w = sp.size * 0.3, l = sp.dim < 1 ? 26 : 42;
      ctx.fillStyle = `hsla(${hue(sp.name.split("#")[0])}, 35%, ${l}%, 0.85)`;
      ctx.fillRect(x - w / 2, Math.max(top, 40), w, S.coord.h);
      font(18);
      ctx.fillStyle = "rgba(255,255,255,0.8)";
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillText("立繪（缺素材）", x, Math.max(top, 40) + 16);
      ctx.fillText(sp.name, x, Math.max(top, 40) + 42);
    }
    ctx.restore();
  }

  function draw(st) {
    const cw = S.coord.w, ch = S.coord.h;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.filter = "none";
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, W, H);
    ctx.setTransform(K, 0, 0, K, 0, 0);

    if (st.intro !== undefined) {
      const lines = S.intro.lines;
      ctx.globalAlpha = st.intro;
      ctx.fillStyle = "#fff";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      lines.forEach((s, k) => {
        font(k === 0 ? 34 : 22);
        ctx.fillText(s, cw / 2, ch / 2 + (k - (lines.length - 1) / 2) * 56);
      });
      return;
    }

    if (st.bg) drawLayer(st.bg, st.cam, "背景");
    if (st.img) drawLayer(st.img, st.cam, "插圖");
    for (const sp of st.sprites) drawSprite(sp, st.cam);

    if (st.blocker[3] > 0) {
      const [r, g, b, a] = st.blocker;
      ctx.fillStyle = `rgba(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)},${a})`;
      ctx.fillRect(0, 0, cw, ch);
    }

    for (const tx of st.texts) {
      ctx.save();
      ctx.globalAlpha = tx.a;
      ctx.shadowColor = "rgba(0,0,0,0.85)";
      ctx.shadowBlur = 4 * K;
      drawText(tx.text, tx.n, tx.x, tx.y, tx.width, tx.size, tx.size * 1.5, tx.align, "#fff");
      ctx.restore();
    }

    if (st.dialog) {
      const D = S.style.dialog;
      const g = ctx.createLinearGradient(0, D.band_top, 0, ch);
      g.addColorStop(0, "rgba(0,0,0,0)");
      g.addColorStop(0.3, "rgba(0,0,0,0.62)");
      g.addColorStop(1, "rgba(0,0,0,0.86)");
      ctx.fillStyle = g;
      ctx.fillRect(0, D.band_top, cw, ch - D.band_top);
      if (st.dialog.name) {
        font(D.name_size);
        ctx.fillStyle = D.name_color;
        ctx.textAlign = "right";
        ctx.textBaseline = "top";
        ctx.fillText(st.dialog.name, D.name_right, D.text_y - (D.name_size - D.text_size) * 0.6);
      }
      drawText(st.dialog.text, st.dialog.n, D.text_x, D.text_y, D.text_width, D.text_size, D.line_height, "left", "#fff");
    }
  }
})();
