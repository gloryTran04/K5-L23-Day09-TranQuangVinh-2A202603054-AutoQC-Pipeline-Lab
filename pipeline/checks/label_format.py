"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line

CHECK = "label_format"


def run(ds, cfg):
    c = cfg["label_format"]
    tol, min_px, max_frac, dup_iou = c["overflow_tol"], c["min_box_px"], c["max_box_frac"], c["dup_box_iou"]
    n_cls = len(ds.classes)
    issues = []

    for lf in ds.label_files():                       # sắp xếp theo tên -> kết quả tất định
        stem = lf.stem
        size = ds.image_size(stem)                    # (W, H) hoặc None (ảnh hỏng / không có ảnh)
        kept = []                                     # (line_no, box) các dòng hợp lệ ĐÃ gặp, để dò DUP_BOX
        for ln_no, text in ds.read_label_lines(stem) or []:   # số dòng GỐC, đã bỏ dòng trống
            # 1) cú pháp
            try:
                cls, x, y, w, h = parse_yolo_line(text)
            except ValueError as e:
                issues.append(Issue(CHECK, ERROR, "BAD_FORMAT", stem, f"dòng sai định dạng: {e} ({text.strip()!r})", ln_no))
                continue
            # 2) id lớp
            if not 0 <= cls < n_cls:
                issues.append(Issue(CHECK, ERROR, "BAD_CLASS_ID", stem, f"id lớp {cls} ngoài 0..{n_cls - 1}", ln_no, {"id": cls}))
                continue
            # 3) box rỗng
            if w <= 0 or h <= 0:
                issues.append(Issue(CHECK, ERROR, "BOX_ZERO", stem, f"box rộng/cao <= 0 (w={w}, h={h})", ln_no))
                continue
            # 4) tràn ảnh: lượng vượt ra ngoài [0,1] lớn nhất trong 4 mép
            overflow = max(0.0, -(x - w / 2), (x + w / 2) - 1, -(y - h / 2), (y + h / 2) - 1)
            if overflow > tol:
                issues.append(Issue(CHECK, ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ảnh {overflow:.4f} > {tol}", ln_no,
                                    {"overflow": round(overflow, 6)}))
            # 5) box lặp: cùng lớp với một dòng TRƯỚC, IoU > ngưỡng -> báo ở dòng sau
            box = (cls, x, y, w, h)
            prev = next((p for p, b in kept if b[0] == cls and iou_xywh(b[1:], box[1:]) > dup_iou), None)
            if prev is not None:
                issues.append(Issue(CHECK, ERROR, "DUP_BOX", stem, f"box lặp với dòng {prev}", ln_no, {"of_line": prev}))
            kept.append((ln_no, box))
            # 6) cảnh báo kích thước
            if size:
                W, H = size
                short_px = min(w * W, h * H)
                if short_px < min_px:
                    issues.append(Issue(CHECK, WARN, "BOX_TINY", stem, f"cạnh ngắn {short_px:.1f}px < {min_px}px", ln_no,
                                        {"short_px": round(short_px, 1)}))
            if w * h > max_frac:
                issues.append(Issue(CHECK, WARN, "BOX_HUGE", stem, f"box chiếm {w * h:.2f} ảnh > {max_frac}", ln_no,
                                    {"frac": round(w * h, 4)}))
    return issues
