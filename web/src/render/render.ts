import { CONFIG as C } from '../game/config';
import { launched, nukeLife, type Game, type Nuke } from '../game/game';
import type { SensorState } from '../types';
import { drawAttract } from './attract';
import { bar, drawStick, text } from './draw';
import { drawBomb, drawExplosion, drawWarning } from './nuke';

interface Opts {
  inputName: string;
  showDebug: boolean;
  now: number;
  video: ImageBitmap | null;
  muted: boolean;
}

interface Pt {
  x: number;
  y: number;
}

/** 核彈瞄準點 */
interface Anchor {
  chest: Pt;
  head: Pt;
  r: number;
}

type Kp = [number, number, number];

const NEAR = 0.8;
/** 最近一顆核彈的位置，被炸時在這裡畫爆炸 */
let lastBlast: { x: number; y: number; r: number } | null = null;
/** 最近一次看到骨架時的瞄準點：漏偵測時沿用，核彈才不會瞬移到畫面中央 */
let lastAnchor: Anchor | null = null;
const HINT: Record<Nuke['kind'], string> = {
  left: '← 閃身步！ →',
  right: '← 閃身步！ →',
  top: '狗熊哆嗦毛！',
};
const BONES: [string, string][] = [
  ['left_shoulder', 'right_shoulder'],
  ['left_shoulder', 'left_elbow'],
  ['left_elbow', 'left_wrist'],
  ['right_shoulder', 'right_elbow'],
  ['right_elbow', 'right_wrist'],
  ['left_shoulder', 'left_hip'],
  ['right_shoulder', 'right_hip'],
  ['left_hip', 'right_hip'],
];

export function render(ctx: CanvasRenderingContext2D, g: Game, s: SensorState, o: Opts) {
  const { width: W, height: H } = ctx.canvas;
  const u = H / 100; // 1 單位 = 1% 高度
  ctx.fillStyle = '#0b0d12';
  ctx.fillRect(0, 0, W, H);

  const anchor = o.video ? drawLive(ctx, o.video, s, W, H, u, o.now) : drawSynthetic(ctx, s, W, H, u, o.now);
  if (g.nuke) drawNuke(ctx, g.nuke, anchor, W, u, o.now);

  drawHud(ctx, g, W, u);
  drawOverlay(ctx, g, s, W, H, u, o.now);
  if (g.flash) {
    const a = 1 - g.flash.t / 0.9;
    if (!g.flash.good && lastBlast) drawExplosion(ctx, lastBlast.x, lastBlast.y, lastBlast.r, g.flash.t / 0.9);
    if (!g.flash.good) {
      ctx.fillStyle = `rgba(255,40,40,${0.35 * a})`;
      ctx.fillRect(0, 0, W, H);
    }
    text(ctx, g.flash.text, W / 2, H * 0.22, 9 * u, g.flash.good ? `rgba(80,255,140,${a})` : `rgba(255,90,90,${a})`);
  }
  if (o.muted) text(ctx, '點一下畫面或按任意鍵開啟音效', W / 2, H - 3 * u, 2.6 * u, 'rgba(255,255,255,0.75)');
  if (o.showDebug) drawDebug(ctx, g, s, o.inputName, u, H);
}

/** 即時影像（鏡像、cover 填滿）+ 骨架；回傳真人身上的瞄準點 */
function drawLive(
  ctx: CanvasRenderingContext2D,
  video: ImageBitmap,
  s: SensorState,
  W: number,
  H: number,
  u: number,
  now: number,
): Anchor {
  const scale = Math.max(W / video.width, H / video.height);
  const dw = video.width * scale;
  const dh = video.height * scale;
  const ox = (W - dw) / 2;
  const oy = (H - dh) / 2;
  ctx.save();
  ctx.translate(W, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(video, ox, oy, dw, dh);
  ctx.restore();
  ctx.fillStyle = 'rgba(0,0,0,0.2)';
  ctx.fillRect(0, 0, W, H);

  const map = (p: Kp): Pt => ({ x: ox + (1 - p[0]) * dw, y: oy + p[1] * dh });
  const kp = s.present ? s.kp : null;
  if (!kp) return lastAnchor ?? { chest: { x: W / 2, y: H * 0.5 }, head: { x: W / 2, y: H * 0.3 }, r: 4 * u };

  ctx.strokeStyle = s.hands_up ? '#50ff8c' : s.shaking ? '#ffd23f' : '#4fd1ff';
  ctx.lineWidth = 0.8 * u;
  ctx.lineCap = 'round';
  ctx.beginPath();
  for (const [a, b] of BONES) {
    const pa = kp[a];
    const pb = kp[b];
    if (!pa || !pb || pa[2] < 0.5 || pb[2] < 0.5) continue;
    const A = map(pa);
    const B = map(pb);
    ctx.moveTo(A.x, A.y);
    ctx.lineTo(B.x, B.y);
  }
  ctx.stroke();

  const ls = map(kp.left_shoulder);
  const rs = map(kp.right_shoulder);
  const head = map(kp.nose);
  const shoulder = Math.hypot(ls.x - rs.x, ls.y - rs.y);
  if (s.locked) text(ctx, '🔒 玩家', head.x, head.y - shoulder * 0.9, Math.max(2.5 * u, shoulder * 0.3), '#4fd1ff');
  lastAnchor = { chest: { x: (ls.x + rs.x) / 2, y: (ls.y + rs.y) / 2 + shoulder * 0.3 }, head, r: Math.max(3 * u, shoulder * 0.45) };
  return lastAnchor;
}

/** 鍵盤模式：假地板 + 火柴人 */
function drawSynthetic(ctx: CanvasRenderingContext2D, s: SensorState, W: number, H: number, u: number, now: number): Anchor {
  const horizon = H * 0.3;
  const yFor = (d: number) => horizon + (H * 0.98 - horizon) * (NEAR / Math.max(d, NEAR));
  const scaleFor = (d: number) => NEAR / Math.max(d, NEAR);
  drawFloor(ctx, W, H, horizon);
  const d = s.present ? s.distance_m : 4;
  const px = W / 2 + s.x_m * W * 0.3 * scaleFor(d) * 2;
  const py = yFor(d);
  const ph = H * 0.75 * scaleFor(d);
  if (s.present) drawPlayer(ctx, px, py, ph, s, now);
  return { chest: { x: px, y: py - ph * 0.7 }, head: { x: px, y: py - ph }, r: 3.5 * u };
}

function drawFloor(ctx: CanvasRenderingContext2D, W: number, H: number, horizon: number) {
  ctx.fillStyle = '#141824';
  ctx.beginPath();
  ctx.moveTo(W * 0.4, horizon);
  ctx.lineTo(W * 0.6, horizon);
  ctx.lineTo(W, H);
  ctx.lineTo(0, H);
  ctx.fill();
}

function drawPlayer(ctx: CanvasRenderingContext2D, x: number, footY: number, h: number, s: SensorState, now: number) {
  drawStick(ctx, x, footY, h, { wob: s.shaking ? Math.sin(now / 30) * h * 0.04 : 0, armsUp: s.hands_up });
}

function drawNuke(ctx: CanvasRenderingContext2D, n: Nuke, a: Anchor, W: number, u: number, now: number) {
  const p = Math.max(0, (n.t - C.WARN_S) / C.FLIGHT_S);
  const r = a.r;
  let x: number;
  let y: number;
  if (n.kind === 'top') {
    x = a.head.x;
    y = -2 * r + (a.head.y + 2 * r) * p;
  } else {
    const from = n.kind === 'left' ? -2 * r : W + 2 * r;
    x = from + (a.chest.x - from) * p;
    y = a.chest.y;
  }
  const hot = launched(n);
  const target = n.kind === 'top' ? a.head : a.chest;
  lastBlast = { x, y, r };

  if (n.t < C.WARN_S) {
    const from =
      n.kind === 'top' ? { x: a.head.x, y: 8 * u } : { x: n.kind === 'left' ? 6 * u : W - 6 * u, y: a.chest.y };
    drawWarning(ctx, from, target, 3 * u, now);
  } else {
    const angle = n.kind === 'top' ? Math.PI / 2 : n.kind === 'left' ? 0 : Math.PI;
    drawBomb(ctx, x, y, r, angle, now, hot);
  }

  const color = hot ? '#ffd23f' : '#ffffff';
  text(ctx, HINT[n.kind], W / 2, 14 * u, 7 * u, color);
  if (n.kind === 'top') {
    const k = Math.min(1, n.shake / C.SHAKE_NEED_S);
    bar(ctx, W / 2 - 15 * u, 17 * u, 30 * u, 1.5 * u, k, '#ffd23f');
  }
  // 剩餘時間條
  bar(ctx, W / 2 - 25 * u, 3 * u, 50 * u, u, 1 - n.t / nukeLife, hot ? '#ffd23f' : '#888');
}

function drawHud(ctx: CanvasRenderingContext2D, g: Game, W: number, u: number) {
  if (g.phase !== 'PLAYING') return;
  for (let i = 0; i < C.HP; i++) {
    text(ctx, i < g.hp ? '❤' : '♡', (4 + i * 6) * u, 9 * u, 5 * u, '#ff4d6d', 'left');
  }
  // 右上角：閃過計數
  const cx = W - 4 * u;
  text(ctx, `閃過 ${g.dodged} / ${C.WIN_DODGES}`, cx, 9 * u, 6 * u, '#50ff8c', 'right');
  const pip = 2.6 * u;
  for (let i = 0; i < C.WIN_DODGES; i++) {
    ctx.fillStyle = i < g.dodged ? '#50ff8c' : 'rgba(255,255,255,0.18)';
    ctx.beginPath();
    ctx.arc(cx - (C.WIN_DODGES - 1 - i) * pip - pip / 2, 12.5 * u, pip * 0.38, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawOverlay(ctx: CanvasRenderingContext2D, g: Game, s: SensorState, W: number, H: number, u: number, now: number) {
  if (s.status === 'no_camera') return text(ctx, '相機未連線（按 K 切鍵盤模式）', W / 2, H / 2, 5 * u, '#ff8080');
  if (s.status === 'disconnected') return text(ctx, '感測器斷線（按 K 切鍵盤模式）', W / 2, H / 2, 5 * u, '#ff8080');
  switch (g.phase) {
    case 'IDLE':
      return drawAttract(ctx, g, s, W, H, u, now);
    case 'COUNTDOWN':
      return text(ctx, String(Math.ceil(C.COUNTDOWN_S - g.phaseTime)), W / 2, H * 0.5, 25 * u, '#ffffff');
    case 'PLAYING':
      if (!s.present) text(ctx, '玩家消失了！', W / 2, H * 0.5, 6 * u, '#ff8080');
      return;
    case 'WIN':
    case 'LOSE': {
      if (g.phase === 'WIN') text(ctx, `勝利！閃過 ${C.WIN_DODGES} 顆核彈`, W / 2, H * 0.4, 9 * u, '#50ff8c');
      else text(ctx, `你被炸掛了 💥 閃過 ${g.dodged} 顆`, W / 2, H * 0.4, 9 * u, '#ff5050');
      const left = Math.max(1, Math.ceil(C.RESULT_S - g.phaseTime));
      text(ctx, `謝謝遊玩！${left} 秒後換下一位`, W / 2, H * 0.5, 4.5 * u, '#ffffff');
      return;
    }
  }
}

function drawDebug(ctx: CanvasRenderingContext2D, g: Game, s: SensorState, inputName: string, u: number, H: number) {
  const lines = [
    `輸入: ${inputName}  [K 切換 / D 隱藏]`,
    `status: ${s.status}  present: ${s.present}  locked: ${s.locked ?? '-'}  衣服差異: ${s.lock_match ?? '-'}`,
    `distance: ${s.distance_m.toFixed(2)}m  x: ${s.x_m.toFixed(2)}m`,
    `shaking: ${s.shaking}  hands_up: ${s.hands_up}`,
    `phase: ${g.phase}  hp: ${g.hp}`,
  ];
  ctx.font = `${1.8 * u}px monospace`;
  ctx.textAlign = 'left';
  ctx.fillStyle = 'rgba(200,210,230,0.7)';
  lines.forEach((l, i) => ctx.fillText(l, 2 * u, H - (lines.length - i) * 2.4 * u));
}
