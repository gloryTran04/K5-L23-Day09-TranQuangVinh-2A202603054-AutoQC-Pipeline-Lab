"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★

Test:  pytest tests/test_second_opinion.py -q

Chỉ CẢNH BÁO (WARN): model cũng có thể sai, ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

  P = dự đoán có conf >= conf VÀ diện tích px >= min_area_px
  Với mỗi r trong P, cands = nhãn (mọi lớp) có IoU(r, nhãn) >= iou_missing:
   (1) cands rỗng                                          -> POSSIBLE_MISSING
   (2) có cands cùng lớp: IoU tốt nhất < iou_loose          -> POSSIBLE_LOOSE_BOX (ngược lại: không cờ)
   (3) không có cùng lớp: IoU tốt nhất khác lớp >= iou_match -> POSSIBLE_WRONG_CLASS (ngược lại: không cờ)
  Mỗi dòng nhãn hợp lệ có IoU < iou_missing với MỌI dự đoán conf >= fp_conf (không lọc diện tích)
                                                           -> POSSIBLE_FALSE_POS (Issue.line = số dòng gốc)
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds

CHECK = "second_opinion"


def _labels_with_lines(ds, stem, n_cls):
    """[(số dòng gốc, (cls, cx, cy, w, h))] của các dòng parse được và có id lớp hợp lệ (giống ds.valid_boxes)."""
    out = []
    for no, text in ds.read_label_lines(stem) or []:
        try:
            b = parse_yolo_line(text)
        except ValueError:
            continue                                   # dòng hỏng: label_format đã báo, ở đây bỏ qua êm
        if 0 <= b[0] < n_cls:
            out.append((no, b))
    return out


def run(ds, cfg, preds=None):
    c = cfg["second_opinion"]
    conf_t, min_area, fp_conf = c["conf"], c["min_area_px"], c["fp_conf"]
    iou_missing, iou_match, iou_loose = c["iou_missing"], c["iou_match"], c["iou_loose"]
    if preds is None:
        preds = get_preds(ds, cfg, "checker")
    n_cls = len(ds.classes)
    issues = []

    for img in ds.image_files():
        stem = img.stem
        if stem not in preds or not ds.label_path(stem).exists():
            continue
        labels = _labels_with_lines(ds, stem, n_cls)
        rows = [(int(r[0]), float(r[1]), tuple(float(v) for v in r[2:6])) for r in preds[stem]]
        size = ds.image_size(stem)

        # --- từ phía model: vật model thấy chắc chắn (conf cao, đủ lớn)
        for cls, conf, box in rows:
            if conf < conf_t:
                continue
            if size and box[2] * size[0] * box[3] * size[1] < min_area:
                continue
            cands = [(iou_xywh(box, b[1:]), b[0]) for _, b in labels]
            cands = [(iou, lc) for iou, lc in cands if iou >= iou_missing]
            if not cands:
                issues.append(Issue(CHECK, WARN, "POSSIBLE_MISSING", stem,
                                    f"model thấy {ds.classes[cls] if cls < n_cls else cls} (conf {conf:.2f}) mà nhãn không có box",
                                    extra={"conf": conf, "pred_cls": cls, "box": [round(v, 4) for v in box]}))
                continue
            same = [iou for iou, lc in cands if lc == cls]
            if same:
                best = max(same)
                if best < iou_loose:
                    issues.append(Issue(CHECK, WARN, "POSSIBLE_LOOSE_BOX", stem,
                                        f"box {ds.classes[cls]} lệch/lỏng: IoU {best:.2f} < {iou_loose}",
                                        extra={"conf": conf, "iou": round(best, 4), "pred_cls": cls}))
                continue                                # nhãn đúng lớp đã phủ vật này
            best_iou, best_cls = max(cands)
            if best_iou >= iou_match:
                issues.append(Issue(CHECK, WARN, "POSSIBLE_WRONG_CLASS", stem,
                                    f"nhãn {ds.classes[best_cls]} nhưng model nói {ds.classes[cls] if cls < n_cls else cls} "
                                    f"(conf {conf:.2f}, IoU {best_iou:.2f})",
                                    extra={"conf": conf, "iou": round(best_iou, 4), "label_cls": best_cls, "pred_cls": cls}))
            # IoU khác lớp trong [iou_missing, iou_match): mơ hồ -> không cờ

        # --- từ phía nhãn: box nhãn không khớp vật nào model thấy (kể cả dự đoán nhỏ / conf thấp >= fp_conf)
        loose_preds = [box for _, conf, box in rows if conf >= fp_conf]
        for no, b in labels:
            best = max((iou_xywh(b[1:], box) for box in loose_preds), default=0.0)
            if best < iou_missing:
                issues.append(Issue(CHECK, WARN, "POSSIBLE_FALSE_POS", stem,
                                    f"box {ds.classes[b[0]]} không khớp dự đoán nào của model (IoU tốt nhất {best:.2f})",
                                    no, {"iou": round(best, 4)}))
    return issues
