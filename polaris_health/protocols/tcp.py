# -*- coding: utf-8 -*-

import logging
import socket
import time
import ssl  # Import for TLS handling
from polaris_health import ProtocolError

__all__ = ['TCPSocket']

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())

# Buffer size for receiving data
RECV_BUFF_SIZE = 8192


class TCPSocket:
    """TCP socket helper with optional TLS support"""

    def __init__(self, ip, port, timeout=5, auto_timeout=True):
        """
        args:
            ip: str, IP address to connect to
            port: int, port number
            timeout: float, socket operation timeout in seconds
            auto_timeout: bool, automatically reduce the timeout based on I/O operation time
        """
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.auto_timeout = auto_timeout

        # Initialize the socket
        if ':' in ip:
            self._sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        else:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.settimeout(self.timeout)

    def connect(self):
        """Connect self._sock to self.ip:self.port"""
        start_time = time.monotonic()
        try:
            self._sock.connect((self.ip, self.port))
        except OSError as e:
            self._sock.close()
            raise ProtocolError('{} {} during socket.connect()'.format(e.__class__.__name__, e))
        self._decrease_timeout(time.monotonic() - start_time)

    def wrap_ssl(self, context=None):
        """
        Wrap the socket in SSL/TLS using the provided context.

        args:
            context: ssl.SSLContext, custom SSL context for configuring TLS behavior
        """
        try:
            # Default to a standard SSL context if none provided
            if context is None:
                context = ssl.create_default_context()
            self._sock = context.wrap_socket(self._sock, server_hostname=self.ip)
        except ssl.SSLError as e:
            self._sock.close()
            raise ProtocolError('SSL error: {} during TLS handshake'.format(e))

    def sendall(self, b):
        """Send all bytes to the connected socket."""
        start_time = time.monotonic()
        try:
            self._sock.sendall(b)
        except OSError as e:
            self._sock.close()
            raise ProtocolError('{} {} during socket.sendall()'.format(e.__class__.__name__, e))
        self._decrease_timeout(time.monotonic() - start_time)

    def recv(self):
        """Read response from the connected socket up to RECV_BUFF_SIZE bytes."""
        start_time = time.monotonic()
        try:
            received = self._sock.recv(RECV_BUFF_SIZE)
        except OSError as e:
            self._sock.close()
            raise ProtocolError('{} {} during socket.recv()'.format(e.__class__.__name__, e))
        self._decrease_timeout(time.monotonic() - start_time)
        return received

    def close(self):
        """Shut down and close the connected socket."""
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
            self._sock.close()
        except OSError as e:
            log_msg = 'Got {} {} when shutting down and closing the socket'.format(e.__class__.__name__, e)
            LOG.warning(log_msg)

    def settimeout(self, timeout):
        """Set timeout on the socket."""
        self._sock.settimeout(timeout)

    def _decrease_timeout(self, time_taken):
        """Decrease the timeout based on time taken for an I/O operation if auto_timeout is True."""
        if self.auto_timeout:
            self.timeout -= time_taken
            if self.timeout < 0:
                self.timeout = 0
            self.settimeout(self.timeout)
