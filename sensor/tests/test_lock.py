import numpy as np

from detector import Sample, load_config
from lock import Cand, PlayerLock, appearance_distance

RED = {"torso": np.eye(1, 192, 0).ravel()}
BLUE = {"torso": np.eye(1, 192, 100).ravel()}
RED_ISH = {"torso": RED["torso"] * 0.8 + BLUE["torso"] * 0.2}


def lock(want_locked: bool = False) -> PlayerLock:
    lk = PlayerLock(load_config())
    lk.want_locked = want_locked
    return lk


def person(t: float, u: float, z: float, sig=RED, hands_up=False, person_ok=True) -> Cand:
    # 面向鏡頭：玩家左邊 = 影像右邊（x 較大）
    lw, rw = ((u + 0.05, 0.1), (u - 0.05, 0.1)) if hands_up else ((u + 0.06, 0.55), (u - 0.06, 0.55))
    kp = {
        "nose": (u, 0.2, 0.9),
        "left_shoulder": (u + 0.04, 0.3, 0.9),
        "right_shoulder": (u - 0.04, 0.3, 0.9),
        "left_wrist": (*lw, 0.9),
        "right_wrist": (*rw, 0.9),
        "left_hip": (u + 0.02, 0.6, 0.9),
        "right_hip": (u - 0.02, 0.6, 0.9),
    }
    return Cand(Sample(t=t, kp=kp, hip_x_m=(u - 0.5) * z, distance_m=z), sig, person_ok)


def test_appearance_distance():
    assert appearance_distance(RED, RED) < 0.01
    assert appearance_distance(RED, BLUE) > 0.99
    assert appearance_distance(RED, RED_ISH) < 0.35
    assert appearance_distance(None, RED) == 0.0


def test_locks_on_request_then_ignores_others():
    lk = lock(want_locked=True)
    assert lk.pick(0.0, [person(0.0, 0.48, 4.0), person(0.0, 0.2, 2.0, BLUE)]).distance_m == 4.0
    assert lk.locked is not None
    for i in range(1, 30):
        t = i / 30
        # 藍衣路人走到畫面中央也不換人
        got = lk.pick(t, [person(t, 0.5, 2.0, BLUE), person(t, 0.3, 4.0 - t)])
        assert got.distance_m == 4.0 - t


def test_unlocked_returns_center_person_without_locking():
    lk = lock()
    got = lk.pick(0.0, [person(0.0, 0.2, 2.0), person(0.0, 0.55, 2.5)])
    assert got.distance_m == 2.5
    assert lk.locked is None


def test_unlocked_prefers_hands_up_person_and_locks_him_on_request():
    lk = lock()
    cands = lambda t: [person(t, 0.5, 2.0, BLUE), person(t, 0.2, 3.0, RED, hands_up=True)]
    assert lk.pick(0.0, cands(0.0)).distance_m == 3.0
    lk.want_locked = True  # 網頁端：舉手滿了，開局
    assert lk.pick(0.03, cands(0.03)).distance_m == 3.0
    assert appearance_distance(lk.locked.sig, RED) < 0.01


def test_unlocked_sticks_to_shown_person():
    lk = lock()
    lk.pick(0.0, [person(0.0, 0.45, 2.0)])
    # 另一個人站得更靠中央，但沒舉手：繼續回報原本那位
    assert lk.pick(0.03, [person(0.03, 0.44, 2.0), person(0.03, 0.5, 3.5, BLUE)]).distance_m == 2.0


def test_non_person_never_acquired_but_followed_once_locked():
    lk = lock(want_locked=True)
    assert lk.pick(0.0, [person(0.0, 0.5, 3.0, person_ok=False)]).kp is None
    assert lk.locked is None
    lk.pick(0.03, [person(0.03, 0.5, 3.0)])
    # 鎖定後側身（肩寬檢查不過）照樣跟
    assert lk.pick(0.06, [person(0.06, 0.52, 3.0, person_ok=False)]).kp is not None


def test_different_clothes_at_player_position_is_rejected():
    lk = lock(want_locked=True)
    lk.pick(0.0, [person(0.0, 0.5, 4.0, RED)])
    # 玩家不見，穿藍衣的人站到同一個位置
    assert lk.pick(0.1, [person(0.1, 0.5, 4.0, BLUE)]).kp is None


def test_reacquire_far_away_by_clothes():
    lk = lock(want_locked=True)
    lk.pick(0.0, [person(0.0, 0.3, 4.0, RED)])
    # 被擋住後從畫面另一邊出現：位置跳太遠，但衣服一樣 → 認回來；同時旁邊有藍衣路人
    got = lk.pick(0.1, [person(0.1, 0.9, 4.0, RED), person(0.1, 0.32, 4.0, BLUE)])
    assert got.kp is not None and got.hip_x_m == (0.9 - 0.5) * 4.0


def test_locked_player_hidden_returns_empty_not_bystander():
    lk = lock(want_locked=True)
    lk.pick(0.0, [person(0.0, 0.5, 4.0)])
    assert lk.pick(0.1, [person(0.1, 0.9, 1.5, BLUE)]).kp is None
    assert lk.locked is not None


def test_lock_released_on_request_and_after_timeout():
    lk = lock(want_locked=True)
    lk.pick(0.0, [person(0.0, 0.5, 4.0)])
    lk.want_locked = False
    lk.pick(0.1, [])
    assert lk.locked is None
    lk.want_locked = True
    lk.pick(1.0, [person(1.0, 0.5, 4.0)])
    lk.pick(1.0 + lk.cfg["lock"]["lost_timeout_s"] + 0.1, [])
    assert lk.locked is None
