import type { Input, SensorState, StepEvent } from '../types';

/** ←/→ 閃身步、Space 按住哆嗦毛、↑/↓ 前後移動、H 按住舉手、P 切換在場 */
export class KeyboardInput implements Input {
  readonly name = '鍵盤';
  private distance = 4.0;
  private x = 0;
  private present = true;
  private events: StepEvent[] = [];
  private held = new Set<string>();

  constructor() {
    window.addEventListener('keydown', (e) => {
      if (e.repeat) return;
      this.held.add(e.code);
      switch (e.code) {
        case 'ArrowLeft':
          this.events.push('step_left');
          this.x = Math.max(-1, this.x - 0.3);
          break;
        case 'ArrowRight':
          this.events.push('step_right');
          this.x = Math.min(1, this.x + 0.3);
          break;
        case 'ArrowUp':
          this.distance = Math.max(0.8, this.distance - 0.25);
          break;
        case 'ArrowDown':
          this.distance = Math.min(5, this.distance + 0.25);
          break;
        case 'KeyP':
          this.present = !this.present;
          break;
      }
      if (e.code.startsWith('Arrow') || e.code === 'Space') e.preventDefault();
    });
    window.addEventListener('keyup', (e) => this.held.delete(e.code));
  }

  video() {
    return null;
  }

  poll(): SensorState {
    const events = this.events;
    this.events = [];
    return {
      status: 'ok',
      present: this.present,
      distance_m: this.distance,
      x_m: this.x,
      events,
      shaking: this.held.has('Space'),
      hands_up: this.held.has('KeyH'),
    };
  }
}
