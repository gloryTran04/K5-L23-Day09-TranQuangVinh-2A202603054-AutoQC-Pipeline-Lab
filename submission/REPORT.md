# Báo cáo Day 09 — Trần Quang Vinh, 2A202603054

> Mọi số trong báo cáo lấy từ `submission/reports/` (cấu hình `phash_dist = 12`, `second_opinion.conf = 0.6`), `submission/calibration/`, và các lần chạy ghi rõ lệnh.

## 1. Kết luận trước
Pipeline kết luận **HOLD** (mã thoát **10**). **224** ảnh vào; bước nhận loại **22** ảnh (hỏng, nhỏ, trùng, rò rỉ test), còn **202** ảnh đi qua QC và được xuất ra `submission/export/clean_v1/` (202 file nhãn, `manifest.json` ghi `decision = Hold`). Đây là **bản nháp để thử nghiệm, chưa được phát hành**.

Lý do: sau sửa tự động và người duyệt, **0 lỗi bắt buộc** còn lại. Nhưng **38/202 ảnh (18.8%)** vẫn còn cảnh báo chưa được người duyệt, ≥ ngưỡng 10% (`08_summary.json`). Hàng đợi có 125 ảnh mà ngân sách duyệt chỉ có 80.

## 2. Lỗi và phân việc
Lấy từ `02_error_list_v1.csv` (211 dòng trên 149 ảnh; mẫu số: 224 ảnh quét ở bước nhận, 202 ảnh ở QC). Cách sửa lấy từ `03_fixes.csv` (35 thay đổi).

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `CORRUPT_IMAGE` | 2 ảnh / 224 | máy: loại ở bước nhận | ảnh không mở được (`load()` lỗi), không thể dùng |
| `BAD_SIZE` | 3 ảnh / 224 | máy: loại | cạnh ngắn < 250 px (180–226 px) |
| `DUP_IMAGE_EXACT` | 8 ảnh / 224 | máy: loại | trùng từng byte (md5); giữ ảnh đầu tiên |
| `DUP_IMAGE_NEAR` | 4 ảnh / 224 | máy: loại | phash ≤ 12 (đã calibrate, §3) |
| `LEAK_TEST` | 5 ảnh / 224 | máy: loại | trùng ảnh tập test (`img_0049, 0101, 0167, 0174, 0221`); để lại thì điểm test bị thổi phồng |
| `MISSING_LABEL_FILE` | 6 ảnh / 202 | **người** (`needs_label`) | máy không được bịa nhãn, kể cả file rỗng (rỗng = ảnh nền); có trọng số 10 nên lên đầu hàng đợi |
| `BAD_CLASS_ID` | 6 dòng (6 ảnh) | máy: `drop_line` | id 93 / 7 / 4 / −1 không có lớp tương ứng; không đoán được lớp đúng |
| `BAD_FORMAT` | 3 dòng (3 ảnh) | máy: `drop_line` | 2 dòng có `nan`, 1 dòng thiếu cột: không parse được |
| `BOX_ZERO` | 4 dòng (4 ảnh) | máy: `drop_line` | box rộng/cao = 0, không có vật |
| `DUP_BOX` | 7 dòng (7 ảnh) | máy: `drop_line` | cùng lớp, IoU > 0.9 với dòng trước: một vật bị gán hai lần |
| `BOX_OUT_OF_IMAGE` | 8 dòng (8 ảnh) | máy: `clip_box` (8) | cắt về [0,1], giữ lớp; không dòng nào phải xoá vì nằm hẳn ngoài ảnh |
| `BAD_CLASS_NAME` | 2 dòng (`data.yaml`) | máy: `rename_classes` (1 lần) | `Person`, `Bus` viết hoa sai; ghi lại `names` đúng thứ tự dự án |
| `POSSIBLE_MISSING` | 53 cờ / 52 ảnh | **người** | model thấy vật mà nhãn không có box; model cũng có thể sai nên chỉ cảnh báo |
| `POSSIBLE_WRONG_CLASS` | 18 cờ / 18 ảnh | **người** | nhầm lớp hợp lệ (12 ca car↔person, 6 ca giữa các loại xe): là lỗi ngữ nghĩa |
| `POSSIBLE_LOOSE_BOX` | 28 cờ / 24 ảnh | **người** | cùng vật, cùng lớp nhưng IoU < 0.5 |
| `POSSIBLE_FALSE_POS` | 29 cờ / 27 ảnh | **người** | box nhãn không khớp dự đoán nào; precision chỉ 0.31 trên calib nên phải xem |
| `EMPTY_LABEL` | 12 ảnh | **người** | file rỗng: ảnh nền hay quên gán? (vd. `img_0004` có xe mà nhãn rỗng) |
| `BOX_TINY` / `BOX_HUGE` | 6 dòng (4 ảnh) / 3 dòng (3 ảnh) | **người** | quy tắc kích thước (< 12 px, > 95% ảnh), cần mắt người xác nhận |
| `CLASS_RARE` | 4 dòng (`<dataset>`) | (không sửa riêng) | do các token lạ `-1` (2 box), `4` (2), `7` (1), `93` (1); hết sau khi autofix xoá các dòng `BAD_CLASS_ID` |

**Hàng đợi `05_review_queue.csv` (125 ảnh).** Điểm ưu tiên = Σ trọng số mã × (1 + conf của model), cộng điểm cho dòng đã bị máy sửa. Trọng số cố định trong config: NEEDS_LABEL 10 > WRONG_CLASS 3 > MISSING = FALSE_POS = FIXED_DROP_LINE 2 > LOOSE 1.5 > … > BOX_TINY 0.3. Vì vậy:
- Vị trí 1 là `img_0020` (11.52): cộng dồn FIXED_DROP_LINE + MISSING + WRONG_CLASS.
- Vị trí 2–7 là **6 ảnh chưa có nhãn** (10.0 mỗi ảnh): nếu không gán thì gate ra Rework (§4a).
- Tiếp theo là các ảnh có nhiều cờ ngữ nghĩa với conf cao (`img_0160`, `img_0127`, `img_0004`…). Cuối hàng là ảnh chỉ có BOX_TINY / BOX_HUGE (0.3–0.5).

**Với ngân sách 80 ảnh** (ảnh thứ 80 có điểm 3.34; `06_review_log.csv`: 80/80 ảnh được thay bằng nhãn người): trong 123 cờ ngữ nghĩa `POSSIBLE_*` ở v2 (trên 103 ảnh), người xem được **94 cờ trên 74 ảnh**. Theo loại: WRONG_CLASS **18/18 ảnh**, MISSING **50/52 ảnh**, FALSE_POS 12/23 ảnh, LOOSE_BOX chỉ **8/24 ảnh** (trọng số thấp). 45 ảnh cuối hàng không được xem; 38 ảnh trong số đó vẫn còn cảnh báo ở v3 (LOOSE_BOX 16, FALSE_POS 11, BOX_TINY 6, EMPTY_LABEL 4, BOX_HUGE 3, MISSING 2). Đây chính là 38 ảnh làm gate ra Hold.

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **12** | DUP_IMAGE_NEAR 1.00 / 0.50 → **1.00 / 0.67**; DUP_IMAGE_EXACT 1.00 / 1.00 (giữ nguyên) | Đây là lỗi bắt buộc, máy **tự xoá ảnh**, nên ưu tiên precision. Mọi giá trị từ 4 đến 14 cho cùng P/R trên calib. 16 có recall cao nhất (0.83) nhưng trên raw loại nhầm 8 ảnh (xem bên dưới); 20 làm recall EXACT tụt còn 0.33. Chọn 12 vì nằm giữa khoảng trống của phân bố khoảng cách trên raw (trùng thật ≤ 10, cặp kế tiếp đã ở 16), có biên an toàn cả hai phía. |
| `second_opinion.conf` | 0.25 | **0.6** | WRONG_CLASS 0.56 / 0.83 → **0.62 / 0.83**; MISSING 0.50 / 1.00 → **0.57 / 1.00**; LOOSE_BOX 0.29 / 0.40 → 0.20 / 0.20; FALSE_POS 0.31 / 1.00 (không đổi, vì dùng `fp_conf` cố định) | Đây là cảnh báo cho người, nên **không được hy sinh recall** của hai lỗi nặng nhất (thiếu box, nhầm lớp). 0.6 là giá trị cao nhất còn giữ recall MISSING = 1.00 và WRONG_CLASS = 0.83, trong khi precision tăng, nên người duyệt bớt mở uổng (hàng đợi trên raw giảm từ 130 xuống 125 ảnh so với conf 0.5). Lên 0.7 thì recall MISSING tụt còn 0.88. Cái giá: recall LOOSE_BOX giảm 0.40 → 0.20 (chỉ có 5 lỗi chèn, mỗi lỗi bằng 20%). |

**Chỗ calibration có thể đánh lừa (có bằng chứng):**
1. **`phash_dist` tốt nhất trên calib lại hại trên raw.** Nếu chỉ nhìn calib thì 16 là tốt nhất (recall NEAR 0.83). Nhưng chạy pipeline trên raw, số ảnh bị loại ở bước 1 tăng từ **22 lên 31**. Mở xem 9 ảnh thêm vào thì **8/9 là ảnh khác hẳn nhau**: 6 ảnh bị gán nhầm `LEAK_TEST` (vd. `img_0013` là bàn làm việc, bị cho là trùng `test_087` là sân bóng chày; `img_0038` lướt sóng bị cho là trùng `test_002` bánh cưới), 2 ảnh bị gán nhầm `DUP_IMAGE_NEAR` (`img_0011`↔`img_0008`, `img_0177`↔`img_0113`). Chỉ `img_0084`↔`img_0074` là trùng thật (bản cắt). Phân bố khoảng cách phash trên raw: các cặp trùng thật ở 0–10 (`img_0223`↔`img_0077` = 6, `img_0186`↔`img_0061` = 10), không có cặp nào ở 12–14, rồi 9 cặp ở 16. Vì calib chỉ có 6 ca gần trùng nên không thấy được vùng báo nhầm này.
2. **Calib khác phân bố lỗi của raw.** Trên calib, 5/6 lỗi nhầm lớp là person→car, model rất tự tin (conf 0.8 vẫn giữ recall 0.83, precision 1.00), nên chỉ nhìn calib dễ chọn 0.8. Nhưng trên raw, nhầm lớp chủ yếu là giữa các loại xe và model kém tự tin hơn: trong 6 cờ WRONG_CLASS loại car/truck/bus ở `02_error_list_v1`, **2 cờ có conf < 0.8** (bus→car, bus→truck) sẽ mất nếu chọn 0.8, và số cờ MISSING giảm từ 53 xuống 32. Ngoài ra, mỗi ô của calib chỉ có 5–8 lỗi chèn nên P/R nhảy từng bước 12–20%: không đủ để phân biệt các giá trị gần nhau.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Cửa chặn thật sự chặn.** Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb; echo $?` (không có người duyệt):
- log: `kết luận: REWORK — còn 6 lỗi bắt buộc (MISSING_LABEL_FILE) — phải sửa trước khi phát hành`, rồi `Bước 5/5 KHÔNG xuất: còn lỗi bắt buộc (Rework)`; **mã thoát 20**;
- `work/rep_nb/08_summary.json`: `decision = Rework`, `n_errors = 6`, `exported = null`; thư mục `work/exp_nb/clean_v1` **không được tạo**.
- 6 ảnh chưa có file nhãn (`img_0031, img_0053, img_0126, img_0135, img_0170, img_0219`) không thể sửa bằng máy: autofix chỉ ghi `needs_label` (lần này thêm 6 dòng trong `03b_fixes_after_review.csv`) và **không** tạo file rỗng. Vì vậy cổng giữ nguyên Rework. Trong lần chạy chính (ngân sách 80), cả 6 ảnh có trọng số NEEDS_LABEL = 10 nên nằm trong 7 vị trí đầu `05_review_queue.csv`, được người gán nhãn, và `07_error_list_v3` còn 0 lỗi bắt buộc.

**(b) Quan sát bằng mắt và điểm mù.**

*Quan sát bằng mắt trước khi chạy pipeline* (`viz_labels.py`, 13 ảnh `img_0001`–`img_0012`, `img_0030`): (1) `img_0001` thiếu box người lính ở giữa ảnh, đồng thời dòng 1 và 3 là một box lặp; (2) `img_0004` có file nhãn rỗng dù ảnh có ít nhất 3 xe con và 1 người; (3) `img_0030` dòng 9 có box tràn mép trái (x_min = −0.023). Đối chiếu với pipeline: các lỗi cú pháp (box lặp, box tràn, ảnh hỏng `img_0010`) được **bắt chắc chắn và tự sửa**. Lỗi ngữ nghĩa (thiếu box ở `img_0001`, nhãn rỗng ở `img_0004`) máy chỉ **nghi ngờ** qua `POSSIBLE_MISSING` / `EMPTY_LABEL` rồi đẩy vào hàng đợi cho người (vị trí 25 và 10). Riêng `img_0030` cho thấy giới hạn của autofix: cắt box làm hết lỗi cú pháp, nhưng phần còn lại chỉ là một vệt rộng khoảng 1.5% ảnh (bị cờ `BOX_TINY` và `POSSIBLE_FALSE_POS`), tức là sửa cú pháp không bảo đảm nhãn đúng nghĩa.

*Điểm mù của pipeline (có bằng chứng):*
    1. **Ảnh trùng bị biến đổi mạnh lọt qua.** `img_0084` là bản cắt của `img_0074` (phash 16 > ngưỡng 12), nên **cả hai vẫn nằm trong** `export/clean_v1/manifest.json`. Trên calib, `DUP_IMAGE_NEAR` cũng sót 2/6 ca biến đổi mạnh nhất (`calib_037` mức 3, `calib_038` mức 4). Nâng ngưỡng lên 16 thì bắt được cặp này, nhưng kéo theo 8 cặp báo nhầm (xem §3), nên chấp nhận đây là điểm mù đã biết.
    2. **Nhầm lớp bị che bởi một box đúng lớp chồng lên.** Trên calib, `POSSIBLE_WRONG_CLASS` bắt được 5/5 ca person→car nhưng **sót ca duy nhất truck→bus** (`calib_009` dòng 6). Lý do: cùng chiếc xe đó còn có box car ở dòng 4 (IoU 0.95 với dự đoán car của model), và theo quy tắc "đã có nhãn đúng lớp phủ vật thì không cờ", box bus sai lớp bị bỏ qua.
    3. **Model lớn cũng nhầm giữa các loại xe.** `img_0083`: nhãn máy là bus, yolo26l nói car (conf 0.69), còn nhãn người sau khi duyệt là **truck**, tức cả hai đều sai. Sau duyệt, `07_error_list_v3` vẫn cờ `img_0078`, `img_0083`, `img_0220` là "truck nhưng model nói car" trên nhãn người: đây là báo động giả của chính checker. `second_opinion` chỉ gợi ý "có gì đó sai", không được dùng để tự đổi lớp.
    4. **Box lỏng nhẹ và nhãn chưa ai xem.** `POSSIBLE_LOOSE_BOX` chỉ bắt 1/5 box phình ×1.45–1.58 trên calib (recall 0.20). Hàng đợi có 125 ảnh nhưng ngân sách chỉ 80, nên **45 ảnh không được xem**; 38/202 ảnh vẫn còn cảnh báo và đi vào bản export nháp với nhãn máy.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
**Thiết lập (công bằng):** notebook `notebooks/day09_train_compare.ipynb` trên Colab T4, `scripts/train_compare.py --variants raw clean --seeds 0 1 --epochs 20`. Hai biến thể dùng cùng model khởi tạo `yolo26n.pt`, cùng siêu tham số (imgsz 640, batch 16), cùng seed {0, 1}, cùng val `gold_val` (40 ảnh) và cùng test (100 ảnh nhãn người). Chỉ khác dữ liệu train:
- `raw`: toàn bộ 224 ảnh `data/raw` với nhãn gốc, gồm cả 2 ảnh hỏng, 12 ảnh trùng, 5 ảnh rò rỉ test và mọi dòng nhãn lỗi;
- `clean`: 202 ảnh theo `submission/export/clean_v1/manifest.json` (export nháp, quyết định Hold).

**Kết quả:** ⏳ *[ĐIỀN SAU KHI TRAIN: dán bảng từ `submission/results/comparison.md` (mAP50, mAP50-95, precision, recall, TB ± độ lệch chuẩn) và số ảnh train thực tế của mỗi biến thể]*

**So với nhiễu:** ⏳ *[ĐIỀN SAU KHI TRAIN: chênh mAP50 (clean − raw) = … so với độ lệch chuẩn giữa 2 seed = …. Nếu |chênh| ≤ khoảng 2 lần độ lệch chuẩn thì viết "**chưa kết luận được** clean tốt hơn raw"; chỉ khi chênh lệch vượt rõ nhiễu ở cả 2 seed mới được nói một biến thể tốt hơn.]*

**Giả thuyết giải thích và cách kiểm** (đặt ra trước khi xem kết quả):
1. **Rò rỉ test thổi phồng `raw`.** `raw` chứa 5 ảnh trùng tập test (`img_0049`↔`test_033`, `img_0101`↔`test_039`, `img_0167`↔`test_044`, `img_0174`↔`test_085`, `img_0221`↔`test_009`). Model `raw` đã "thấy" 5/100 ảnh test. Cách kiểm: đánh giá lại hai model trên 95 ảnh test còn lại, hoặc so AP của 5 ảnh đó giữa hai biến thể.
2. **`clean` vẫn còn nhãn máy chưa ai xem.** 45 ảnh ngoài ngân sách giữ nguyên nhãn máy; 38 ảnh còn cảnh báo (16 LOOSE_BOX, 11 FALSE_POS…). Lợi ích của `clean` vì vậy bị giới hạn. Cách kiểm: thêm biến thể `oracle` (cùng ảnh với clean, nhãn người) làm chặn trên.
3. **Nhiễu thống kê lớn.** Test chỉ có 100 ảnh, mỗi biến thể chỉ 2 seed; lớp truck (41 box) và bus (32 box) có rất ít box so với person (574) theo `class_stats.csv`, nên AP theo lớp dao động mạnh. Cách kiểm: xem `ap50_per_class` trong `results/*.json`, và thêm seed nếu còn quota.
4. **Ultralytics tự bỏ dữ liệu hỏng của `raw`.** Ảnh không mở được và dòng có id lạ bị cảnh báo và bỏ qua khi train, nên `raw` thực chất không bẩn bằng con số 224 ảnh. Cách kiểm: đọc log cảnh báo ở ô train của notebook và trường `train_images` trong json.

**Kết luận và việc tiếp theo:** ⏳ *[ĐIỀN SAU KHI TRAIN: kết luận trung thực theo bảng trên, và việc tiếp theo (thêm seed, bỏ 5 ảnh rò rỉ khỏi đánh giá, chạy `oracle`).]*

## 6. Quyết định và ghi chú AI
**(a) Quyết định cuối: HOLD**, không phát hành `clean_v1`. Số liệu khớp với `08_summary.json` và `07_error_list_v3`: 0 lỗi bắt buộc, 38/202 = 18.8% ảnh còn cảnh báo chưa duyệt ≥ 10%.
- **Điều kiện để thành Release:** số ảnh còn cảnh báo chưa duyệt phải xuống ≤ 20/202 (< 10%). Theo đúng thứ tự `05_review_queue.csv`, cần duyệt thêm 18 ảnh (vị trí 81–98, tức ngân sách ≥ 98 ảnh thay vì 80); đây là quyết định của dự án, không phải của người làm pipeline. Cách khác là giảm báo động giả của checker (FALSE_POS precision chỉ 0.31 trên calib, chiếm 11/38 ảnh còn lại) bằng một model kiểm mạnh hơn hoặc guideline rõ hơn, rồi calibrate lại. **Không** được hạ recall chỉ để hàng đợi vừa ngân sách.
- **Điều kiện chuyển sang Rework:** nếu còn bất kỳ lỗi bắt buộc nào, ví dụ 6 ảnh chưa có nhãn mà người không gán (đã chứng minh ở §4a: ngân sách 0 → Rework, mã 20, không xuất).

**(b) Ghi chú dùng AI** 
- **Prompt chính:** "Đọc kỹ toàn bộ repo để hiểu yêu cầu bài lab, hướng dẫn chi tiết từng bước"
- **Cách kiểm:** (1) chạy `pytest` từng file, rồi toàn bộ: **79/79 xanh**; (2) `make calibrate` trên bộ calib có lỗi chèn: các mã cú pháp đạt P = R = 1.00; (3) mở `viz_labels.py` đối chiếu bằng mắt (§4b); (4) chạy lại `--budget 0` để thấy gate chặn; (5) một script kiểm chứng độc lập (`work/verify_report_numbers.py`) tính lại **mọi con số** trong §3–§4 từ output thật của repo.

*(Thưởng +2, tùy chọn)* CVAT: không làm.
