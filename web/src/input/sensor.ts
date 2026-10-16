import { EMPTY_STATE, type Input, type SensorState, type StepEvent } from '../types';

/** 連 Python server，斷線每 1 秒重連 */
export class SensorInput implements Input {
  readonly name = '相機';
  private latest: SensorState = { ...EMPTY_STATE };
  private events: StepEvent[] = [];
  private wantLocked = false;
  private ws: WebSocket | null = null;
  private frame: ImageBitmap | null = null;
  private frameAt = 0;
  private decoding = false;

  constructor(private url = 'ws://localhost:8765') {
    this.connect();
  }

  private connect() {
    const ws = new WebSocket(this.url);
    this.ws = ws;
    ws.binaryType = 'blob';
    // server 可能重啟過：連上就重送目前要的鎖定狀態
    ws.onopen = () => this.sendLock();
    ws.onmessage = (m) => {
      if (m.data instanceof Blob) return this.onJpeg(m.data);
      const msg = JSON.parse(m.data) as Partial<SensorState>;
      if (msg.status !== 'ok') {
        this.latest = { ...EMPTY_STATE, status: 'no_camera' };
        return;
      }
      // 沒人時 server 送 null
      this.latest = {
        ...EMPTY_STATE,
        ...msg,
        distance_m: msg.distance_m ?? 0,
        x_m: msg.x_m ?? 0,
        events: [],
      } as SensorState;
      this.events.push(...(msg.events ?? []));
    };
    ws.onclose = () => {
      this.latest = { ...EMPTY_STATE };
      setTimeout(() => this.connect(), 1000);
    };
  }

  private onJpeg(blob: Blob) {
    if (this.decoding) return; // 解碼跟不上就丟幀，不要越積越多延遲
    this.decoding = true;
    createImageBitmap(blob)
      .then((bmp) => {
        this.frame?.close();
        this.frame = bmp;
        this.frameAt = performance.now();
      })
      .catch(() => {})
      .finally(() => (this.decoding = false));
  }

  /** 開局鎖定當下回報的人（剛舉手的那位）；回待機解鎖。只在狀態改變時送 */
  setLocked(on: boolean) {
    if (on === this.wantLocked) return;
    this.wantLocked = on;
    this.sendLock();
  }

  private sendLock() {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(this.wantLocked ? 'lock' : 'unlock');
  }

  video() {
    return performance.now() - this.frameAt < 1000 ? this.frame : null;
  }

  poll(): SensorState {
    const events = this.events;
    this.events = [];
    return { ...this.latest, events };
  }
}
