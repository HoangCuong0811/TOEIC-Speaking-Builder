# TOEIC Speaking Builder

Tạo trọn bộ 1 đề TOEIC Speaking (Q1–11) gồm **audio MP3** và **video MP4**. Bạn chỉ cần nhập nội dung đề trên giao diện web (hoặc điền vào 1 file cấu hình). Thời gian chờ, thời gian làm bài, tiếng beep, tiếng tích tắc và tiếng ding được đo từ video SPEAKING_TEST_6, nên lần chạy nào cũng giống hệt nhau.

```
toeic_speaking_builder/
├── app.py                  ← web API (FastAPI) + giao diện
├── web/index.html          ← giao diện nhập đề
├── make_test.py            ← logic tạo audio + video, cũng chạy được bằng dòng lệnh
├── settings.py             ← cấu hình khi deploy (đọc từ biến môi trường TOEIC_*)
├── config/test_moi.json    ← nội dung đề khi chạy bằng dòng lệnh
├── assets/
│   ├── images/             ← logo, ảnh Q3, Q4, ảnh tài liệu Q8–10
│   ├── sfx/                ← beep, tích tắc, ding (cắt từ video gốc)
│   └── fonts/              ← font Inter
├── requirements.txt        ← thư viện cần cài, đã ghim phiên bản
├── requirements.lock       ← bản chụp đầy đủ mọi thư viện, dùng khi deploy
├── .vscode/launch.json     ← để bấm F5 chạy trong VS Code
├── models/                 ← (tự tạo) model giọng Kokoro, tải ở lần chạy đầu
└── output/                 ← (tự tạo) kết quả
```

---

## 1. Cài đặt (chỉ làm 1 lần)

1. **Cài Python 3.11 hoặc 3.12** từ https://www.python.org/downloads/
   - Trên Windows, ở màn hình cài đặt nhớ tick **"Add python.exe to PATH"**.
2. **Cài VS Code** và extension **Python** (của Microsoft).
3. Giải nén file zip. Trong VS Code chọn **File → Open Folder…** rồi chọn thư mục `toeic_speaking_builder`.
4. Mở Terminal trong VS Code (**Terminal → New Terminal**, hoặc `Ctrl + \``) rồi tạo môi trường ảo:

   **Windows (PowerShell):**
   ```powershell
   py -3.12 -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
   Nếu PowerShell báo *"running scripts is disabled"*, chạy lệnh dưới 1 lần rồi kích hoạt lại:
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```

   **macOS:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
   Khi kích hoạt thành công, đầu dòng lệnh sẽ có chữ `(.venv)`.

5. Cài thư viện (phiên bản đã được ghim, nên máy nào cài cũng ra đúng bản đã chạy tốt):
   ```bash
   pip install -r requirements.txt
   ```
   Khi deploy lên máy chủ, dùng `pip install -r requirements.lock` để ghim luôn cả các thư viện phụ thuộc.
6. Trong VS Code bấm `Ctrl + Shift + P`, gõ **Python: Select Interpreter**, rồi chọn mục có `.venv`.

Không cần cài ffmpeg riêng: thư viện `imageio-ffmpeg` đã kèm sẵn.

---

## 2. Chạy bằng giao diện web

Trong Terminal (đang có `(.venv)`):

```bash
python app.py
```

Rồi mở http://127.0.0.1:8001 trên trình duyệt. Hoặc mở tab **Run and Debug** (`Ctrl + Shift + D`), chọn **"Chay giao dien web (FastAPI)"** rồi bấm **F5**.

1. Ở mục **Chọn phần cần tạo**, tick phần muốn luyện (mặc định là **All** = cả đề).
2. Nhập nội dung của các phần đã chọn (câu 3, câu 4, tài liệu câu 8–10 cần chọn ảnh). Phần không chọn sẽ được ẩn, không cần nhập.
3. Bấm **Tạo video**. Thanh tiến độ hiện từng bước; tải lại trang cũng không mất tiến độ.
4. Khi xong, video hiện ngay trên trang, kèm nút **Tải video (MP4)** và **Tải audio (MP3)**.

Ghi chú:

- **Luyện từng phần:** Part 1 = câu 1–2, Part 2 = câu 3–4, Part 3 = câu 5–7, Part 4 = câu 8–10, Part 5 = câu 11. Có thể chọn 1 phần hoặc nhiều phần **liền nhau** (vd. Part 1–2, Part 2–4); video chạy đúng như trong đề đầy đủ, mỗi phần bắt đầu bằng lời hướng dẫn của phần đó. Không chọn được phần cách quãng (vd. Part 1 và Part 3): hãy tạo 2 video riêng. Tên file tự thêm hậu tố, vd. `..._Part2`, `..._Part1-2`. Nếu video kết thúc ở cuối một phần (Part 1–4), màn hình dừng ở **STOP** thêm 2 giây. Số câu trên màn hình vẫn giữ nguyên như trong đề (vd. Part 3 hiện "Question 5 of 11").

- **Lời đọc:** mặc định giọng đọc đọc đúng chữ hiển thị trên màn hình. Nếu chữ có giờ, ngày tháng, giá tiền hoặc ký hiệu (`9:30`, `April 12`, `$15`), tick **"Nhập lời đọc riêng"** rồi nhập cách đọc bằng chữ ở ô ngay bên dưới.
- **Câu 8–10** chỉ có giọng đọc (màn hình hiện ảnh tài liệu), nên viết luôn như khi đọc: `"nine thirty a.m."`.
- **Tải lại trang (F5) sẽ xoá hết nội dung đã nhập.** Nếu đang có nội dung, trình duyệt hỏi xác nhận trước: đồng ý thì trang tải lại với form trống, huỷ thì mọi thứ giữ nguyên. Job đang chạy hoặc video đã xong thì vẫn còn sau khi tải lại.
- Mỗi lần chỉ chạy 1 đề; đề gửi sau sẽ xếp hàng chờ.
- Kết quả từng lần tạo nằm trong `output/jobs/<mã job>/`. Mặc định thư mục này không tự xoá: bạn dọn tay, hoặc đặt `TOEIC_JOB_TTL_HOURS` để tự xoá (xem "Cấu hình khi deploy" bên dưới).

### API

Giao diện gọi các API dưới đây; bạn cũng có thể gọi trực tiếp. Tài liệu tự sinh ở http://127.0.0.1:8001/docs (tắt bằng `TOEIC_DOCS=0`).

| API | Ý nghĩa |
|---|---|
| `POST /api/jobs` | Tạo 1 đề. Gửi `multipart/form-data` gồm trường `data` (JSON nội dung đề) và 3 file `q3_image`, `q4_image`, `q8_10_image`. Trả về job kèm `id`. |
| `GET /api/jobs/{id}` | Trạng thái (`queued`, `running`, `done`, `error`), bước đang chạy và tiến độ `progress` (0–1). |
| `GET /api/jobs/{id}/video` | File MP4. Thêm `?download=1` để tải về. |
| `GET /api/jobs/{id}/audio` | File MP3. Thêm `?download=1` để tải về. |

Các trường của `data`: `name`, `parts` (tuỳ chọn, mảng các phần cần tạo, vd. `[2, 3]`; phải liền nhau, mặc định `[1, 2, 3, 4, 5]`), `q1_text`, `q2_text`, `q5_7_intro`, `q5`, `q6`, `q7`, `q7_options` (mảng), `q8_intro`, `q8`, `q9`, `q10`, `q11_lead`, `q11_statement`, `q11_instruction`, và `spoken` (tuỳ chọn, lời đọc riêng cho `q5_7_intro`, `q5`, `q6`, `q7`, `q7_options`, `q11_lead`, `q11_statement`, `q11_instruction`).

Chỉ các trường của những phần được chọn là bắt buộc (Part 2 cần ảnh `q3_image`, `q4_image`; Part 4 cần `q8_10_image`); ảnh của phần không chọn sẽ bị bỏ qua.

### Cấu hình khi deploy

Không đặt gì thì chạy đúng như trên máy bạn. Khi đưa lên máy chủ, đặt các biến môi trường dưới đây (đọc một lần lúc khởi động; giá trị sai sẽ làm chương trình dừng ngay kèm thông báo rõ):

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `TOEIC_HOST` | `127.0.0.1` | Địa chỉ lắng nghe. Đặt `0.0.0.0` khi chạy trong Docker hoặc máy chủ. Nếu chỉ dùng Cloudflare Tunnel trên cùng máy thì giữ nguyên (an toàn hơn). |
| `TOEIC_PORT` | `8001` | Cổng. |
| `TOEIC_DATA_DIR` | thư mục chứa mã nguồn | Thư mục gốc chứa `models/` và `output/`. Trỏ vào ổ đĩa bền (volume) để không mất dữ liệu khi deploy lại. |
| `TOEIC_MODELS_DIR` | `<TOEIC_DATA_DIR>/models` | Riêng nơi chứa model giọng đọc (khoảng 340 MB). |
| `TOEIC_OUTPUT_DIR` | `<TOEIC_DATA_DIR>/output` | Riêng nơi chứa kết quả các job. |
| `TOEIC_MAX_IMAGE_MB` | `20` | Dung lượng tối đa mỗi ảnh tải lên. |
| `TOEIC_VOICE` | `af_heart` | Giọng đọc (Kokoro). |
| `TOEIC_SPEED` | `1.0` | Tốc độ đọc, từ 0.5 đến 2.0. |
| `TOEIC_LANG` | `en-us` | Cách phát âm. Dùng `en-gb` với giọng Anh (`bf_…`, `bm_…`). |
| `TOEIC_JOB_TTL_HOURS` | `0` | Tự xoá file của job sau số giờ này (kể từ lần ghi cuối). `0` = không bao giờ xoá. Khi deploy nên đặt, ví dụ `72`. Job đang chờ hoặc đang chạy không bị xoá. |
| `TOEIC_DOCS` | `1` | `0` để tắt các trang `/docs`, `/redoc`, `/openapi.json`. Khi deploy công khai nên đặt `0`. |

Ví dụ (PowerShell):

```powershell
$env:TOEIC_JOB_TTL_HOURS = "72"; $env:TOEIC_DOCS = "0"; python app.py
```

Lưu ý khi deploy:

- **Chỉ chạy 1 tiến trình.** Danh sách job và hàng đợi nằm trong bộ nhớ của tiến trình, nên không chạy nhiều worker (đừng dùng `--workers 2`), nếu không các tiến trình sẽ không thấy job của nhau.
- **Khởi động lại sẽ mất danh sách job đang theo dõi** (file đã dựng xong vẫn còn trên đĩa cho tới khi hết hạn).
- **Chưa có đăng nhập.** Ai có đường link đều tạo được job; nếu đưa ra Internet, hãy đặt sau một lớp xác thực (ví dụ Cloudflare Access).

---

## 3. Chạy bằng dòng lệnh (file config)

Trong Terminal (đang có `(.venv)`):

```bash
python make_test.py config/test_moi.json
```

Hoặc mở tab **Run and Debug** (`Ctrl + Shift + D`), chọn **"Tao de TOEIC (audio + video)"** rồi bấm **F5**.

- **Lần chạy đầu:** script tự tải model giọng đọc (khoảng 340 MB) vào `models/`. Các lần sau không tải lại.
- **Thời gian:** khoảng 5–10 phút tuỳ máy. Phần vẽ khung hình là lâu nhất.
- **Kết quả** nằm trong `output/`:

| File | Dùng để |
|---|---|
| `TOEIC_Speaking_Test_moi.mp4` | Video hoàn chỉnh |
| `TOEIC_Speaking_Test_moi.mp3` | Audio riêng |
| `..._cue_sheet.csv` | Mốc thời gian từng câu, beep, đồng hồ (mở bằng Excel) |
| `..._timeline.json`, `..._audio.wav` | File trung gian, cần cho `--video-only` |

**Tuỳ chọn:**

| Lệnh | Ý nghĩa |
|---|---|
| `--audio-only` | Chỉ tạo audio, không dựng video |
| `--video-only` | Chỉ dựng lại video, giữ nguyên audio đã có. Dùng khi bạn chỉ sửa chữ trên màn hình hoặc đổi ảnh. |
| `--keep-frames` | Giữ lại các khung hình PNG để kiểm tra |

---

### Làm đề mới bằng file config

1. Sao chép `config/test_moi.json` thành file mới, ví dụ `config/test_07.json`, rồi đổi `"output_name"`.
2. Sửa phần **`"spoken"`**: đây là những gì giọng đọc sẽ đọc.
   - Viết như khi đọc: số viết bằng chữ (`"forty-five"`, `"nine thirty a.m."`), không ký hiệu, không viết hoa cả từ (`"most"` chứ không phải `"MOST"`).

   | Khoá | Nội dung |
   |---|---|
   | `Q5_INTRO` | Đoạn giới thiệu Q5–7 (viết liền cả đoạn, một hay nhiều câu đều được) |
   | `Q5`, `Q6` | Câu hỏi 5, 6 |
   | `Q7_A` | Câu hỏi 7 |
   | `Q7_B` | Các lựa chọn của câu 7, ví dụ `"Healthy snacks. Coffee. Ice cream."`. Không có lựa chọn thì để `""`. |
   | `Q8_INTRO` | Lời giới thiệu của người gọi trước Q8 |
   | `Q8`, `Q9`, `Q10` | Câu hỏi 8, 9, 10 |
   | `Q11_A`, `Q11_B`, `Q11_C` | Câu dẫn, nhận định, câu yêu cầu của Q11 |

3. Sửa phần **`"screen"`**: đây là chữ hiện trên màn hình, viết bình thường (dùng chữ số được).
   - `q1_text`, `q2_text`: đoạn văn học viên đọc to. Hai câu này chỉ hiện chữ, không có giọng đọc.
   - `q3_image`, `q4_image`, `q8_10_image`: chép ảnh vào `assets/images/` rồi ghi đường dẫn.
   - `q5_7_intro`, `q5`, `q6`, `q7`, `q7_options`, `q11_lead`, `q11_statement`, `q11_instruction`.
4. Muốn chỉ tạo một số phần, thêm `"parts": [2, 3]` ở cấp ngoài cùng của file config (các phần phải liền nhau, bỏ trống = cả đề). Khi đó chỉ cần điền nội dung của các phần đó.
5. Chạy: `python make_test.py config/test_07.json`.

Nếu chữ dài, script tự thu nhỏ cỡ chữ để vừa khung.

---

## 4. Tuỳ chỉnh (không bắt buộc)

- **Logo:** thay file `assets/images/logo.png`, giữ nguyên tên.
- **Màu giao diện:** sửa khối `THEME` trong `make_test.py`.
- **Giọng đọc:** đặt biến môi trường `TOEIC_VOICE` (ví dụ `af_bella`, `af_nicole`) và `TOEIC_SPEED` (0.9–1.0), xem bảng cấu hình ở mục 2.

---

## 5. Lỗi thường gặp

| Lỗi | Cách xử lý |
|---|---|
| `'python' is not recognized` | Cài lại Python và tick "Add to PATH", hoặc dùng `py` thay cho `python` |
| `pip install` báo lỗi ở `onnxruntime` | Dùng Python 3.11 hoặc 3.12 |
| Tải model bị lỗi hoặc treo | Tải tay 2 file dưới đây rồi bỏ vào thư mục `models/` |
| `Chua co audio` khi dùng `--video-only` | Chạy 1 lần không kèm `--video-only` trước |
| `Khong tim thay anh ...` | Kiểm tra đường dẫn ảnh trong config, tính từ thư mục `toeic_speaking_builder` |

Link tải model (nếu cần tải tay):
- https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
- https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

Font Inter dùng giấy phép SIL Open Font License (xem `assets/fonts/LICENSE_Inter.txt`).
