#!/usr/bin/env python3
"""
scan-ssh — fast SSH reachability + credential tester.

Pipeline (optimized for speed):
  1. async TCP connect scan on port 22  -> finds hosts that are UP *and* have SSH open
     (far faster than spawning `ping` once per host for a /16)
  2. SSH password auth test on the open hosts, many workers in parallel

Default target head is 172.16.0.0/16 (configurable via --network / --prefix).

Authorized use only: run this against hosts/networks you own or are
explicitly permitted to test.
"""
from __future__ import annotations

import argparse
import asyncio
import ipaddress
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


# ---------------------------------------------------------------------------
# Phase 1: async TCP port scan (host up + SSH port open)
# ---------------------------------------------------------------------------
async def _check_port(ip: str, port: int, timeout: float, sem: asyncio.Semaphore):
    async with sem:
        try:
            fut = asyncio.open_connection(ip, port)
            reader, writer = await asyncio.wait_for(fut, timeout=timeout)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return ip
        except Exception:
            return None


async def _scan_ports(ips, port: int, timeout: float, concurrency: int):
    sem = asyncio.Semaphore(concurrency)
    tasks = [asyncio.ensure_future(_check_port(ip, port, timeout, sem)) for ip in ips]
    open_hosts = []
    done = 0
    total = len(tasks)
    for fut in asyncio.as_completed(tasks):
        res = await fut
        done += 1
        if res:
            open_hosts.append(res)
        if done % 2000 == 0 or done == total:
            print(f"\r  [scan] {done}/{total} đã quét, {len(open_hosts)} host mở cổng {port}",
                  end="", file=sys.stderr, flush=True)
    print("", file=sys.stderr)
    return sorted(open_hosts, key=lambda x: tuple(int(o) for o in x.split(".")))


# ---------------------------------------------------------------------------
# Phase 2: SSH password auth test (paramiko, thread pool)
# ---------------------------------------------------------------------------
def _ssh_try(ip: str, user: str, password: str, port: int, timeout: float):
    try:
        import paramiko
    except ImportError:
        return (ip, None, "paramiko chưa cài (pip install paramiko)")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            ip, port=port, username=user, password=password,
            timeout=timeout, banner_timeout=timeout, auth_timeout=timeout,
            allow_agent=False, look_for_keys=False,
        )
        return (ip, True, "OK")
    except Exception as exc:  # paramiko.AuthenticationException, socket errors, etc.
        return (ip, False, type(exc).__name__)
    finally:
        try:
            client.close()
        except Exception:
            pass


def _test_ssh(hosts, user, password, port, timeout, workers):
    ok, done, total = [], 0, len(hosts)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_ssh_try, h, user, password, port, timeout): h for h in hosts}
        for fut in as_completed(futs):
            ip, success, msg = fut.result()
            done += 1
            if success:
                ok.append(ip)
                print(f"\r  [ssh] {ip}  OK ({user})" + " " * 20)
            print(f"\r  [ssh] {done}/{total} đã thử, {len(ok)} đăng nhập được",
                  end="", file=sys.stderr, flush=True)
    print("", file=sys.stderr)
    return sorted(ok, key=lambda x: tuple(int(o) for o in x.split(".")))


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------
def _build_targets(network: str, prefix: str | None):
    if prefix:
        parts = prefix.strip().rstrip(".").split(".")
        if len(parts) == 2:        # 172.16  -> /16
            network = f"{prefix}.0.0/16"
        elif len(parts) == 3:      # 172.16.10 -> /24
            network = f"{prefix}.0/24"
        else:
            raise SystemExit(f"--prefix không hợp lệ: {prefix} (dùng 'A.B' hoặc 'A.B.C')")
    net = ipaddress.ip_network(network, strict=False)
    return [str(h) for h in net.hosts()], str(net)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(
        description="Quét host sống + test đăng nhập SSH (ping/port scan + sshpass-style auth).")
    p.add_argument("--network", default="172.16.0.0/16",
                   help="Dải CIDR cần quét (mặc định 172.16.0.0/16).")
    p.add_argument("--prefix",
                   help="Đầu IP tiện lợi: 'A.B' => /16, 'A.B.C' => /24 (ghi đè --network).")
    p.add_argument("-u", "--user", default="root", help="Username SSH (mặc định root).")
    p.add_argument("-p", "--password", required=True,
                   help="Password SSH để test (bắt buộc; KHÔNG commit vào repo).")
    p.add_argument("-w", "--workers", type=int, default=100,
                   help="Số luồng test SSH song song (mặc định 100).")
    p.add_argument("-c", "--concurrency", type=int, default=1000,
                   help="Số kết nối async khi scan cổng (mặc định 1000).")
    p.add_argument("--port", type=int, default=22, help="Cổng SSH (mặc định 22).")
    p.add_argument("--scan-timeout", type=float, default=2.0,
                   help="Timeout scan cổng, giây (mặc định 2).")
    p.add_argument("--ssh-timeout", type=float, default=3.0,
                   help="Timeout đăng nhập SSH, giây (mặc định 3).")
    p.add_argument("--alive-out", default="alive.txt",
                   help="File ghi host mở cổng SSH (mặc định alive.txt).")
    p.add_argument("--ok-out", default="ssh_ok.txt",
                   help="File ghi host đăng nhập được (mặc định ssh_ok.txt).")
    args = p.parse_args(argv)

    ips, net_str = _build_targets(args.network, args.prefix)
    print(f"[*] Mục tiêu: {net_str}  ({len(ips)} IP)")
    print(f"[*] Phase 1: scan cổng {args.port} (async, concurrency={args.concurrency}, "
          f"timeout={args.scan_timeout}s)")
    t0 = time.time()
    alive = asyncio.run(_scan_ports(ips, args.port, args.scan_timeout, args.concurrency))
    with open(args.alive_out, "w") as f:
        f.write("\n".join(alive) + ("\n" if alive else ""))
    print(f"[*] -> {len(alive)} host mở cổng {args.port} ({time.time()-t0:.1f}s) -> {args.alive_out}")

    if not alive:
        print("[*] Không có host nào mở cổng SSH. Dừng.")
        return 0

    print(f"[*] Phase 2: test SSH {args.user}/*** (workers={args.workers}, "
          f"timeout={args.ssh_timeout}s)")
    t1 = time.time()
    ok = _test_ssh(alive, args.user, args.password, args.port, args.ssh_timeout, args.workers)
    with open(args.ok_out, "w") as f:
        f.write("\n".join(ok) + ("\n" if ok else ""))
    print(f"[*] -> {len(ok)} host đăng nhập được bằng {args.user} "
          f"({time.time()-t1:.1f}s) -> {args.ok_out}")
    print(f"[*] Tổng thời gian: {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
