import { describe, expect, it } from 'vitest';
import type { SensorState } from '../types';
import { CONFIG as C } from './config';
import { Game } from './game';

const DT = 1 / 60;

function st(over: Partial<SensorState> = {}): SensorState {
  return {
    status: 'ok',
    present: true,
    distance_m: 4,
    x_m: 0,
    y_m: 0,
    events: [],
    shaking: false,
    hands_up: false,
    ...over,
  };
}

function run(g: Game, seconds: number, s: SensorState | ((g: Game) => SensorState)) {
  for (let t = 0; t < seconds; t += DT) g.update(DT, typeof s === 'function' ? s(g) : s);
}

const UP = st({ hands_up: true });

/** rng 固定回傳 → 核彈種類固定：0=left, 0.4=right, 0.9=top */
function playing(rngValue: number) {
  const g = new Game(() => rngValue);
  run(g, C.START_HOLD_S + 0.05, UP);
  expect(g.phase).toBe('COUNTDOWN');
  run(g, C.COUNTDOWN_S + 0.05, st());
  expect(g.phase).toBe('PLAYING');
  return g;
}

/** 跑到核彈出現，再跑到上方導彈可以結算閃過的時間點 */
function untilNukeInWindow(g: Game) {
  run(g, C.FIRST_GAP_S + 0.05, st());
  expect(g.nuke).not.toBeNull();
  run(g, C.RESOLVE_AFTER_S, st());
}

/** 側方核彈：等它出現、站在原地撐過預警（發射時鎖定 x=0），飛行中一直維持 s 直到結算 */
function sideNukeWhile(g: Game, s: SensorState) {
  while (!g.nuke) g.update(DT, st());
  while (g.nuke && g.nuke.t < C.WARN_S) g.update(DT, st());
  while (g.nuke) g.update(DT, s);
}

const AWAY = C.DODGE_SHIFT_M + 0.05;

describe('Game', () => {
  it('雙手舉高撐滿就倒數，倒數完開始', () => {
    playing(0);
  });

  it('只是站著（沒舉手）不會開始', () => {
    const g = new Game();
    run(g, 10, st());
    expect(g.phase).toBe('IDLE');
    run(g, 2, st({ present: false, hands_up: true }));
    expect(g.phase).toBe('IDLE');
  });

  it('舉手中手短暫掉下來不中斷，放下太久要重來', () => {
    const g = new Game();
    run(g, C.START_HOLD_S - 0.3, UP);
    run(g, C.HANDS_GRACE_S - 0.1, st());
    run(g, 0.35, UP);
    expect(g.phase).toBe('COUNTDOWN');
    const g2 = new Game();
    run(g2, C.START_HOLD_S - 0.3, UP);
    run(g2, C.HANDS_GRACE_S + 0.1, st());
    run(g2, 0.35, UP);
    expect(g2.phase).toBe('IDLE');
  });

  it('玩完回待機，原地站著不會自動開下一場', () => {
    const g = playing(0.9);
    while (g.phase === 'PLAYING') g.update(DT, st());
    run(g, C.RESULT_S + 5, st());
    expect(g.phase).toBe('IDLE');
  });

  it('側方核彈：飛行中往旁邊躲開 → 閃過（左右都行）', () => {
    for (const x of [AWAY, -AWAY]) {
      const g = playing(0);
      sideNukeWhile(g, st({ x_m: x }));
      expect(g.hp).toBe(C.HP);
      expect(g.dodged).toBe(1);
    }
  });

  it('側方核彈：往前後跨或蹲下躲開也算', () => {
    for (const away of [{ distance_m: 4 - AWAY }, { distance_m: 4 + AWAY }, { y_m: -AWAY }]) {
      const g = playing(0.4);
      sideNukeWhile(g, st(away));
      expect(g.dodged).toBe(1);
    }
  });

  it('側方核彈：站著不動 → 被炸', () => {
    const g = playing(0);
    sideNukeWhile(g, st());
    expect(g.hp).toBe(C.HP - 1);
  });

  it('側方核彈：只做了閃身步動作但又回到原位 → 被炸', () => {
    const g = playing(0);
    while (!g.nuke) g.update(DT, st());
    while (g.nuke.t < C.WARN_S) g.update(DT, st());
    g.update(DT, st({ events: ['step_right'], x_m: AWAY }));
    while (g.nuke) g.update(DT, st());
    expect(g.hp).toBe(C.HP - 1);
  });

  it('側方核彈：只在預警時移動，瞄準會跟過去 → 被炸', () => {
    const g = playing(0);
    while (!g.nuke) g.update(DT, st());
    while (g.nuke) g.update(DT, st({ x_m: AWAY }));
    expect(g.hp).toBe(C.HP - 1);
  });

  it('側方核彈：移動不夠遠 → 被炸', () => {
    const g = playing(0);
    sideNukeWhile(g, st({ x_m: C.DODGE_SHIFT_M - 0.05 }));
    expect(g.hp).toBe(C.HP - 1);
  });

  it('側方核彈：飛到那一刻才結算', () => {
    const g = playing(0);
    while (!g.nuke) g.update(DT, st());
    run(g, C.WARN_S, st());
    run(g, C.FLIGHT_S - 0.1, st({ x_m: AWAY }));
    expect(g.nuke).not.toBeNull();
    run(g, 0.15, st({ x_m: AWAY }));
    expect(g.nuke).toBeNull();
    expect(g.dodged).toBe(1);
  });

  it('上方追蹤導彈：怎麼移動都沒用，要揮手', () => {
    const g = playing(0.9);
    while (!g.nuke) g.update(DT, st());
    while (g.nuke) g.update(DT, st({ x_m: 1 }));
    expect(g.hp).toBe(C.HP - 1);
  });

  it('上方核彈：哆嗦毛滿 0.5 秒 → 閃過', () => {
    const g = playing(0.9);
    untilNukeInWindow(g);
    run(g, C.SHAKE_NEED_S + 0.05, st({ shaking: true }));
    expect(g.hp).toBe(C.HP);
    expect(g.dodged).toBe(1);
  });

  it('3 滴血扣完 → LOSE，5 秒後回 IDLE', () => {
    const g2 = playing(0.9);
    while (g2.phase === 'PLAYING') g2.update(DT, st());
    expect(g2.phase).toBe('LOSE');
    expect(g2.hp).toBe(0);
    run(g2, C.RESULT_S + 0.05, st());
    expect(g2.phase).toBe('IDLE');
  });

  it(`閃過 ${C.WIN_DODGES} 顆 → WIN`, () => {
    const g = playing(0);
    let x = 0;
    for (let i = 0; i < C.WIN_DODGES; i++) {
      expect(g.phase).toBe('PLAYING');
      while (!g.nuke || g.nuke.t < C.WARN_S) g.update(DT, st({ x_m: x }));
      x = x === 0 ? AWAY : 0;
      while (g.nuke) g.update(DT, st({ x_m: x }));
    }
    expect(g.dodged).toBe(C.WIN_DODGES);
    expect(g.phase).toBe('WIN');
  });

  it('玩家消失 2 秒 → 作廢回 IDLE', () => {
    const g = playing(0);
    run(g, C.ABSENT_ABORT_S + 0.05, st({ present: false }));
    expect(g.phase).toBe('IDLE');
  });

  it('音效事件：倒數、開始、預警、發射、閃過', () => {
    const g = playing(0);
    expect(g.drainSounds()).toEqual(['tick', 'tick', 'tick', 'go']);
    run(g, C.FIRST_GAP_S + C.WARN_S + 0.05, st());
    expect(g.drainSounds()).toEqual(['warn_side', 'launch_side']);
    while (g.nuke) g.update(DT, st({ x_m: AWAY }));
    expect(g.drainSounds()).toEqual(['dodge']);
  });

  it('感測器斷線時暫停', () => {
    const g = playing(0);
    run(g, 10, st({ status: 'disconnected' }));
    expect(g.phase).toBe('PLAYING');
    expect(g.nuke).toBeNull();
  });
});
