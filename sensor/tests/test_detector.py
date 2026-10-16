import math

from detector import Detector, Sample

FPS = 30
DT = 1 / FPS


def pose(arm_dx=0.0, arm_dy=0.0, hands_up=False, hip_vis=0.9, body_dx=0.0):
    """站姿關鍵點（影像正規化座標）。body_dx 整個人平移，arm_dx/dy 只動手。"""
    kp = {
        "nose": (0.5, 0.2, 0.9),
        "left_shoulder": (0.55, 0.3, 0.9),
        "right_shoulder": (0.45, 0.3, 0.9),
        "left_elbow": (0.58, 0.42, 0.9),
        "right_elbow": (0.42, 0.42, 0.9),
        "left_wrist": (0.58, 0.52, 0.9),
        "right_wrist": (0.42, 0.52, 0.9),
        "left_hip": (0.53, 0.6, hip_vis),
        "right_hip": (0.47, 0.6, hip_vis),
    }
    if hands_up:
        kp["left_wrist"] = (0.58, 0.1, 0.9)
        kp["right_wrist"] = (0.42, 0.1, 0.9)
    out = {}
    for name, (x, y, v) in kp.items():
        if "elbow" in name or "wrist" in name:
            x, y = x + arm_dx, y + arm_dy
        out[name] = (x + body_dx, y, v)
    return out


def run(det, frames):
    """frames: list of (kp, hip_x_m)；回傳每幀輸出。"""
    return [det.update(Sample(t=i * DT, kp=kp, hip_x_m=x, distance_m=2.5)) for i, (kp, x) in enumerate(frames)]


def still(n, x=0.0):
    return [(pose(), x)] * n


def test_no_person_not_present():
    out = Detector().update(Sample(t=0.0))
    assert out["present"] is False and out["events"] == []


def test_low_hip_visibility_not_present():
    out = Detector().update(Sample(t=0.0, kp=pose(hip_vis=0.2), hip_x_m=0.0, distance_m=2.0))
    assert out["present"] is False


def test_standing_still_triggers_nothing():
    outs = run(Detector(), still(60))
    assert all(o["present"] and o["events"] == [] and not o["shaking"] and not o["hands_up"] for o in outs)


def test_small_sway_does_not_step():
    frames = [(pose(), 0.05 * math.sin(i / 3)) for i in range(90)]
    assert all(o["events"] == [] for o in run(Detector(), frames))


def test_step_player_right():
    # 相機座標 x 往負 = 影像左 = 玩家右手邊
    frames = still(10) + [(pose(), -0.04 * k) for k in range(1, 9)] + still(10, -0.32)
    events = [e for o in run(Detector(), frames) for e in o["events"]]
    assert events == ["step_right"]


def test_step_player_left():
    frames = still(10) + [(pose(), 0.04 * k) for k in range(1, 9)] + still(10, 0.32)
    events = [e for o in run(Detector(), frames) for e in o["events"]]
    assert events == ["step_left"]


def steps_3d(points):
    """points: list of (hip_x_m, hip_y_m, distance_m)"""
    det = Detector()
    outs = [det.update(Sample(t=i * DT, kp=pose(), hip_x_m=x, hip_y_m=y, distance_m=z)) for i, (x, y, z) in enumerate(points)]
    return [e for o in outs for e in o["events"]]


def test_step_up_down_forward_back():
    rest = [(0.0, 0.0, 2.5)] * 10
    # 跳起：相機 y 往負 = 往上
    assert steps_3d(rest + [(0.0, -0.04 * k, 2.5) for k in range(1, 9)]) == ["step_up"]
    assert steps_3d(rest + [(0.0, 0.04 * k, 2.5) for k in range(1, 9)]) == ["step_down"]
    assert steps_3d(rest + [(0.0, 0.0, 2.5 - 0.04 * k) for k in range(1, 9)]) == ["step_forward"]
    assert steps_3d(rest + [(0.0, 0.0, 2.5 + 0.04 * k) for k in range(1, 9)]) == ["step_back"]


def test_step_picks_largest_axis():
    rest = [(0.0, 0.0, 2.5)] * 10
    move = [(0.0, -0.02 * k, 2.5 - 0.05 * k) for k in range(1, 9)]  # 往前多、往上少
    assert steps_3d(rest + move) == ["step_forward"]


def test_slow_walk_sideways_is_not_step():
    # 0.5 m 花 2 秒走完：每 0.4 s 只移 0.1 m
    frames = [(pose(), -0.5 * i / 60) for i in range(60)]
    assert all(o["events"] == [] for o in run(Detector(), frames))


def test_step_cooldown():
    # 往右閃後立刻往左閃回來（0.2 s 內），冷卻中不觸發
    frames = still(5) + [(pose(), -0.1 * k) for k in range(1, 4)] + [(pose(), -0.3 + 0.1 * k) for k in range(1, 4)]
    events = [e for o in run(Detector(), frames) for e in o["events"]]
    assert events == ["step_right"]


def test_x_m_is_player_view():
    out = Detector().update(Sample(t=0.0, kp=pose(), hip_x_m=-0.4, distance_m=2.0))
    assert out["x_m"] == 0.4


def test_shake_triggers():
    frames = [(pose(arm_dx=0.06 * (1 if i % 2 else -1), arm_dy=0.04 * (1 if i % 3 else -1)), 0.0) for i in range(30)]
    outs = run(Detector(), frames)
    assert outs[-1]["shaking"] is True


def test_body_translation_is_not_shake():
    # 整個人快速橫移（閃身步），手相對肩膀沒動 → 不算哆嗦毛
    frames = [(pose(body_dx=0.01 * i), -0.03 * i) for i in range(20)]
    assert not any(o["shaking"] for o in run(Detector(), frames))


def test_shake_stops_after_window():
    shake = [(pose(arm_dx=0.06 * (1 if i % 2 else -1)), 0.0) for i in range(30)]
    outs = run(Detector(), shake + still(30))
    assert outs[29]["shaking"] is True
    assert outs[-1]["shaking"] is False


def test_hands_up():
    outs = run(Detector(), [(pose(hands_up=True), 0.0)] * 3)
    assert all(o["hands_up"] for o in outs)


def test_distance_holds_last_value_when_missing():
    det = Detector()
    det.update(Sample(t=0.0, kp=pose(), hip_x_m=0.0, distance_m=3.0))
    out = det.update(Sample(t=DT, kp=pose(), hip_x_m=None, distance_m=None))
    assert out["distance_m"] == 3.0 and out["present"] is True


def test_single_arm_drop_is_not_shake():
    # 舉手後一次把手放下：一個速度尖峰，不算哆嗦毛
    frames = [(pose(hands_up=True), 0.0)] * 15 + still(15)
    assert not any(o["shaking"] for o in run(Detector(), frames))


def test_brief_dropout_holds_state_and_step_history():
    det = Detector()
    for i in range(10):
        det.update(Sample(t=i * DT, kp=pose(), hip_x_m=0.0, distance_m=2.5))
    # 漏偵測 3 幀（0.1 s）：仍在場
    for i in range(10, 13):
        assert det.update(Sample(t=i * DT))["present"] is True
    # 回來時已經橫移完：漏掉前的歷史還在，照樣觸發閃身步
    out = det.update(Sample(t=13 * DT, kp=pose(), hip_x_m=-0.3, distance_m=2.5))
    assert out["events"] == ["step_right"]


def test_long_dropout_is_absent_and_clears_history():
    det = Detector()
    hold = det.cfg["presence"]["hold_s"]
    det.update(Sample(t=0.0, kp=pose(), hip_x_m=0.0, distance_m=2.5))
    assert det.update(Sample(t=hold + 0.05))["present"] is False
    # 再出現在別處（可能換人）：不能算成閃身步
    out = det.update(Sample(t=hold + 0.1, kp=pose(), hip_x_m=-0.5, distance_m=2.5))
    assert out["present"] is True and out["events"] == []
