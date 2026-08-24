#!/usr/bin/env python3
"""Relais Wake-on-LAN : reçoit un déclenchement HTTP authentifié et émet un
magic packet en broadcast UDP sur le réseau local. Stdlib uniquement."""

import hmac
import http.server
import os
import socket
import sys

TARGET_MAC = os.environ["WOL_TARGET_MAC"]
BROADCAST_ADDR = os.environ.get("WOL_BROADCAST_ADDR", "255.255.255.255")
AUTH_TOKEN = os.environ["WOL_AUTH_TOKEN"]
LISTEN_PORT = int(os.environ.get("WOL_LISTEN_PORT", "8085"))
BIND_ADDR = os.environ.get("WOL_BIND_ADDR", "127.0.0.1")


def build_magic_packet(mac):
    mac_bytes = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    if len(mac_bytes) != 6:
        raise ValueError(f"adresse MAC invalide: {mac!r}")
    return b"\xff" * 6 + mac_bytes * 16


def send_magic_packet():
    packet = build_magic_packet(TARGET_MAC)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (BROADCAST_ADDR, 9))
    finally:
        sock.close()


class Handler(http.server.BaseHTTPRequestHandler):
    def _reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _is_authorized(self):
        expected = f"Bearer {AUTH_TOKEN}"
        received = self.headers.get("Authorization", "")
        return hmac.compare_digest(received, expected)

    def do_POST(self):
        if self.path != "/wake":
            self._reply(404, "not found\n")
            return
        if not self._is_authorized():
            self._reply(401, "unauthorized\n")
            return
        try:
            send_magic_packet()
        except Exception as exc:
            self._reply(500, f"erreur: {exc}\n")
            return
        self._reply(200, "magic packet envoye\n")

    def do_GET(self):
        if self.path == "/health":
            self._reply(200, "ok\n")
            return
        self._reply(404, "not found\n")

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    server = http.server.HTTPServer((BIND_ADDR, LISTEN_PORT), Handler)
    server.serve_forever()
