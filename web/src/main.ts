import { Sfx } from './audio/sfx';
import { Game } from './game/game';
import { KeyboardInput } from './input/keyboard';
import { SensorInput } from './input/sensor';
import { render } from './render/render';
import type { Input } from './types';

const canvas = document.getElementById('game') as HTMLCanvasElement;
const ctx = canvas.getContext('2d')!;

const sensor = new SensorInput();
const keyboard = new KeyboardInput();
let input: Input = new URLSearchParams(location.search).has('kb') ? keyboard : sensor;
let showDebug = true;

const sfx = new Sfx();
// 瀏覽器要求使用者操作過才能出聲
window.addEventListener('pointerdown', () => sfx.unlock());
window.addEventListener('keydown', () => sfx.unlock());

window.addEventListener('keydown', (e) => {
  if (e.code === 'KeyK') input = input === sensor ? keyboard : sensor;
  if (e.code === 'KeyD') showDebug = !showDebug;
});

function resize() {
  // 不乘 devicePixelRatio：影像只有 960 寬，Retina 上畫 2 倍大的畫布只是白燒 GPU
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}
window.addEventListener('resize', resize);
resize();

const game = new Game();
let last = performance.now();

function frame(now: number) {
  const dt = Math.min(0.1, (now - last) / 1000);
  last = now;
  // 兩邊都 poll，避免非使用中的輸入囤積舊事件
  const fromSensor = sensor.poll();
  const fromKeyboard = keyboard.poll();
  const s = input === sensor ? fromSensor : fromKeyboard;
  const prevPhase = game.phase;
  game.update(dt, s);
  // 開局鎖住剛舉手的人；回待機解鎖，換下一位
  sensor.setLocked(game.phase !== 'IDLE');
  if (game.phase === 'IDLE' && prevPhase !== 'IDLE') sfx.stopAll();
  for (const e of game.drainSounds()) sfx.play(e);
  render(ctx, game, s, { inputName: input.name, showDebug, now, video: input.video(), muted: !sfx.ready });
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
