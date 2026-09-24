#!/usr/bin/env python3
"""Development only (not packaged): evaluate one JS expression in a local Steam CEF target via the
DevTools protocol on 127.0.0.1:8080, stdlib only. Run on the handheld. usage: cdp.py <target-title> <js>"""
import base64
import json
import os
import socket
import struct
import sys
import urllib.parse
import urllib.request


def ws_connect(url):
    u = urllib.parse.urlparse(url)
    s = socket.create_connection((u.hostname, u.port or 80), timeout=10)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        resp += s.recv(4096)
    if b" 101 " not in resp.split(b"\r\n")[0]:
        raise RuntimeError(resp[:200])
    return s


def ws_send(s, text):
    data = text.encode()
    header = bytearray([0x81])
    mask = os.urandom(4)
    n = len(data)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header += struct.pack(">H", n)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", n)
    s.sendall(bytes(header) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))


def recv_exact(s, n):
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise RuntimeError("connection closed")
        buf += chunk
    return buf


def ws_recv(s):
    h = recv_exact(s, 2)
    n = h[1] & 0x7F
    if n == 126:
        n = struct.unpack(">H", recv_exact(s, 2))[0]
    elif n == 127:
        n = struct.unpack(">Q", recv_exact(s, 8))[0]
    return recv_exact(s, n).decode("utf-8", "replace")


def main():
    title, expr = sys.argv[1], sys.argv[2]
    targets = json.load(urllib.request.urlopen("http://127.0.0.1:8080/json", timeout=5))
    target = next(t for t in targets if t.get("title") == title)
    s = ws_connect(target["webSocketDebuggerUrl"])
    ws_send(s, json.dumps({"id": 1, "method": "Runtime.evaluate",
                           "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}))
    while True:
        msg = json.loads(ws_recv(s))
        if msg.get("id") == 1:
            res = msg.get("result", {})
            print(json.dumps(res.get("result", {}).get("value", res), ensure_ascii=False))
            break


if __name__ == "__main__":
    main()
