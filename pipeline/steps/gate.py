"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"
"""
from ..common import ERROR, WARN


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    stems = set(image_stems)
    reviewed = set(reviewed)
    hold_at = cfg["gate"]["warn_ratio_hold"]

    # Lỗi bắt buộc: đếm TẤT CẢ (kể cả lỗi cấp dataset như data.yaml, kể cả ảnh đã duyệt) — không bao giờ bỏ qua.
    errors = [i for i in issues if i.severity == ERROR]
    # Ảnh còn cảnh báo: chỉ ảnh có trong dataset, chưa được người duyệt; đếm ẢNH, không đếm issue.
    warn_images = {i.image for i in issues if i.severity == WARN and i.image in stems and i.image not in reviewed}

    n_images = len(stems)
    ratio = round(len(warn_images) / n_images, 4) if n_images else 0.0

    if errors:
        decision = "Rework"
        codes = sorted({i.code for i in errors})
        reasons = [f"còn {len(errors)} lỗi bắt buộc ({', '.join(codes)}) — phải sửa trước khi phát hành"]
    elif ratio >= hold_at:
        decision = "Hold"
        reasons = [f"{len(warn_images)}/{n_images} ảnh ({ratio:.1%}) còn cảnh báo chưa người duyệt >= ngưỡng {hold_at:.0%}"]
    else:
        decision = "Release"
        reasons = [f"0 lỗi bắt buộc; {len(warn_images)}/{n_images} ảnh ({ratio:.1%}) còn cảnh báo chưa duyệt < ngưỡng {hold_at:.0%}"]
    if reviewed:
        reasons.append(f"{len(reviewed & stems)} ảnh đã được người duyệt")

    return dict(decision=decision, n_errors=len(errors), n_warn_images=len(warn_images),
                n_images=n_images, warn_ratio=ratio, reasons=reasons)
