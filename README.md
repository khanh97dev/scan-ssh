# scan-ssh

Công cụ quét nhanh host sống và kiểm tra đăng nhập SSH trên một dải mạng (mặc định `172.16.0.0/16`).

Tối ưu tốc độ theo 2 pha:

1. **Scan cổng 22 bất đồng bộ (async TCP connect)** — vừa xác định host sống vừa biết SSH có mở hay không. Nhanh hơn rất nhiều so với spawn `ping` cho từng IP trong một dải `/16`.
2. **Test đăng nhập SSH** bằng `paramiko`, chạy nhiều luồng song song (mặc định **100 worker**) chỉ trên các host đã mở cổng.

> ⚠️ **Chỉ dùng hợp pháp.** Chạy tool này với các host/dải mạng mà bạn sở hữu hoặc được phép kiểm tra. Người dùng tự chịu trách nhiệm tuân thủ quy định nội bộ và pháp luật.

## Cài đặt

```bash
pip install -r requirements.txt
```

## Dùng

```bash
# Quét toàn 172.16.0.0/16, user root, 100 worker (mặc định)
python3 scan_ssh.py --prefix 172.16 -u root -p 'MatKhau'

# Chỉ một /24 cho nhanh
python3 scan_ssh.py --prefix 172.16.10 -u root -p 'MatKhau'

# Tùy chỉnh tốc độ
python3 scan_ssh.py --network 10.0.0.0/16 -u admin -p 'MatKhau' \
    --workers 200 --concurrency 2000 --scan-timeout 1.5 --ssh-timeout 3
```

### Tham số

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `--network` | `172.16.0.0/16` | Dải CIDR cần quét |
| `--prefix` | — | Tiện lợi: `A.B` → `/16`, `A.B.C` → `/24` (ghi đè `--network`) |
| `-u, --user` | `root` | Username SSH |
| `-p, --password` | **bắt buộc** | Password để test (truyền qua CLI, không lưu trong repo) |
| `-w, --workers` | `100` | Số luồng test SSH song song |
| `-c, --concurrency` | `1000` | Số kết nối async khi scan cổng |
| `--port` | `22` | Cổng SSH |
| `--scan-timeout` | `2.0` | Timeout scan cổng (giây) |
| `--ssh-timeout` | `3.0` | Timeout đăng nhập SSH (giây) |
| `--alive-out` | `alive.txt` | File ghi host mở cổng SSH |
| `--ok-out` | `ssh_ok.txt` | File ghi host đăng nhập được |

## Kết quả

- `alive.txt` — các host mở cổng SSH.
- `ssh_ok.txt` — các host đăng nhập được bằng user/password đã cho.

## Lưu ý bảo mật

- **Không** hardcode mật khẩu vào mã nguồn — luôn truyền qua `-p` khi chạy.
- File output đã được `.gitignore` để tránh vô tình commit danh sách host nội bộ.
