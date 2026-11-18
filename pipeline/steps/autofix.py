"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: chỉ xử lý issue severity ERROR, sửa thẳng vào `ds` (KHÔNG đụng data/raw),
trả về danh sách thay đổi {image, line, action, before, after} = file `03_fixes.csv`.

| code lỗi                                       | action           |
|------------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | "clip_box" (box rỗng sau khi cắt -> "drop_line") |
| MISSING_LABEL_FILE                             | "needs_label" (không tạo file) |
| BAD_CLASS_NAME                                 | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| "remove_image"   |
"""
from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line

DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
CLIP_CODES = {"BOX_OUT_OF_IMAGE"}
REMOVE_CODES = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}


def _fx(image, line, action, before, after):
    return dict(image=image, line=line, action=action, before=before, after=after)


def _clip(text):
    """Cắt box về [0,1]. Trả chuỗi dòng mới, hoặc None nếu box không còn diện tích."""
    cls, x, y, w, h = parse_yolo_line(text)
    x1, x2 = max(0.0, x - w / 2), min(1.0, x + w / 2)
    y1, y2 = max(0.0, y - h / 2), min(1.0, y + h / 2)
    nw, nh = round(x2 - x1, 6), round(y2 - y1, 6)
    if nw <= 0 or nh <= 0:                      # nằm hẳn ngoài ảnh (hoặc mỏng tới mức làm tròn về 0)
        return None
    return f"{cls} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {nw:.6f} {nh:.6f}"


def fix(ds, issues, cfg):
    errors = [i for i in issues if i.severity == ERROR]          # WARN là việc của người: không động tới
    fixes = []

    # 1) Xoá ảnh (trùng / rò rỉ / hỏng / sai kích thước) — làm trước để bỏ qua issue dòng của ảnh đã xoá
    removed = set()
    for i in errors:
        if i.code not in REMOVE_CODES or i.image in removed:
            continue
        img, lab = ds.image_path(i.image), ds.label_path(i.image)
        if img is None and not lab.exists():                     # đã xoá ở lần chạy trước -> idempotent
            continue
        before = img.name if img else "(không có ảnh)"
        if img is not None:
            img.unlink()
        if lab.exists():
            lab.unlink()
            before += f" + labels/{lab.name}"
        removed.add(i.image)
        fixes.append(_fx(i.image, None, "remove_image", f"{before} [{i.code}]", "(đã xoá khỏi dataset)"))

    # 2) data.yaml: ghi lại names đúng thứ tự của dự án (một lần, dù có nhiều issue BAD_CLASS_NAME)
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        old = ds.yaml_names()
        want = dict(enumerate(cfg["classes"]))
        if old != want:
            d = {}
            if ds.yaml_path.exists():
                d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
            d["names"] = want
            ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
            fixes.append(_fx("data.yaml", None, "rename_classes", str(old), str(want)))

    # 3) Ảnh chưa có nhãn: máy KHÔNG bịa nhãn (không tạo file, kể cả rỗng) -> chuyển người gán
    seen_missing = set()
    for i in errors:
        if i.code != "MISSING_LABEL_FILE" or i.image in removed or i.image in seen_missing:
            continue
        seen_missing.add(i.image)
        if ds.image_path(i.image) is not None and not ds.label_path(i.image).exists():
            fixes.append(_fx(i.image, None, "needs_label", "(không có file)", "chuyển người gán"))

    # 4) Lỗi theo dòng: gom theo file, dùng số dòng GỐC, ghi lại file MỘT lần
    drop, clip = defaultdict(set), defaultdict(set)
    for i in errors:
        if i.line is None or i.image in removed:
            continue
        if i.code in DROP_CODES:
            drop[i.image].add(i.line)
        elif i.code in CLIP_CODES:
            clip[i.image].add(i.line)

    for stem in sorted(set(drop) | set(clip)):
        p = ds.label_path(stem)
        if not p.exists():
            continue
        raw = p.read_text(encoding="utf-8", errors="replace")
        lines = raw.splitlines()                                 # giữ cả dòng trống -> chỉ số = số dòng gốc
        out, changed = [], False
        for no, text in enumerate(lines, 1):
            if no in drop[stem]:                                 # xoá dòng thắng: không clip thêm
                fixes.append(_fx(stem, no, "drop_line", text.strip(), ""))
                changed = True
                continue
            if no in clip[stem]:
                try:
                    new = _clip(text)
                except ValueError:
                    new = None
                if new is None:
                    fixes.append(_fx(stem, no, "drop_line", text.strip(), ""))
                else:
                    fixes.append(_fx(stem, no, "clip_box", text.strip(), new))
                    out.append(new)
                changed = True
                continue
            out.append(text)
        if changed:
            p.write_text("".join(ln + "\n" for ln in out), encoding="utf-8")
    return fixes
