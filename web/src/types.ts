export type StepEvent =
  | 'step_left'
  | 'step_right'
  | 'step_up'
  | 'step_down'
  | 'step_forward'
  | 'step_back';

/** 與 Python server 協定相同形狀；disconnected 為網頁端自己加的狀態 */
export interface SensorState {
  status: 'ok' | 'no_camera' | 'disconnected';
  present: boolean;
  distance_m: number;
  x_m: number;
  /** 髖部中心高度（m，往上為正）；只看變化量 */
  y_m: number;
  events: StepEvent[];
  shaking: boolean;
  hands_up: boolean;
  /** Python 端已鎖定玩家 */
  locked?: boolean;
  /** 鎖定的人與衣服指紋的距離（0 = 一樣） */
  lock_match?: number | null;
  /** 正規化影像座標 [x, y, visibility]，未鏡像 */
  kp?: Record<string, [number, number, number]> | null;
}

export interface Input {
  readonly name: string;
  /** 取得最新狀態；events 為上次 poll 之後累積的事件 */
  poll(): SensorState;
  /** 最新的即時影像；沒有就回 null */
  video(): ImageBitmap | null;
}

export const EMPTY_STATE: SensorState = {
  status: 'disconnected',
  present: false,
  distance_m: 0,
  x_m: 0,
  y_m: 0,
  events: [],
  shaking: false,
  hands_up: false,
};
