from body import Metric, looks_like_person
from detector import load_config

CFG = load_config()
W, H = 1280, 720
FX = FY = 640.0


def standing(dx=0.0):
    # 2.5 m 遠：肩寬 ~0.4 m ≈ 102 px，軀幹 ~0.5 m ≈ 128 px
    return {
        "nose": (0.5 + dx, 0.22, 0.9),
        "left_shoulder": (0.54 + dx, 0.32, 0.9),
        "right_shoulder": (0.46 + dx, 0.32, 0.9),
        "left_hip": (0.53 + dx, 0.5, 0.9),
        "right_hip": (0.47 + dx, 0.5, 0.9),
        "left_knee": (0.53 + dx, 0.7, 0.9),
        "right_knee": (0.47 + dx, 0.7, 0.9),
    }


def check(kp, hip_z=2.5, shoulder_z=2.5, metric=True):
    m = Metric(FX, FY, hip_z, shoulder_z) if metric else None
    return looks_like_person(kp, W, H, m, CFG)


def test_real_person_passes():
    assert check(standing()) == (True, "")


def test_far_tree_rejected():
    ok, why = check(standing(), hip_z=8.0, shoulder_z=8.0)
    assert not ok and "距離" in why


def test_wrong_size_rejected():
    # 同樣像素大小，但在 5 m 外 → 肩寬換算 0.8 m，太大
    ok, why = check(standing(), hip_z=5.0, shoulder_z=5.0)
    assert not ok and "肩寬" in why


def test_depth_not_continuous_rejected():
    ok, why = check(standing(), hip_z=2.5, shoulder_z=4.0)
    assert not ok and "深度" in why


def test_upside_down_rejected():
    kp = standing()
    kp["nose"] = (0.5, 0.6, 0.9)
    assert check(kp)[0] is False


def test_low_visibility_rejected():
    kp = standing()
    kp["nose"] = (0.5, 0.22, 0.2)
    assert check(kp)[0] is False


def test_webcam_skips_metric_checks():
    assert check(standing(), metric=False) == (True, "")
