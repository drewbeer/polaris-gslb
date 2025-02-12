# -*- coding: utf-8 -*-

import logging
import re
import ssl  # Import for TLS handling
from polaris_health import Error, ProtocolError, MonitorFailed
from polaris_health.protocols.tcp import TCPSocket
from . import BaseMonitor

__all__ = ['TCP']

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())

# maximum allowed length of match_re parameter
MAX_MATCH_RE_LEN = 128
# maximum allowed length of send_string parameter
MAX_SEND_STRING_LEN = 256


class TCP(BaseMonitor):
    """TCP monitor base with optional TLS support"""

    def __init__(self, port, use_tls=False, verify_tls=True, send_string=None,
                 match_re=None, interval=10, timeout=5, retries=2):
        """
        args:
            port: int, port number
            use_tls: bool, whether to use TLS (SSL) for the connection
            verify_tls: bool, whether to verify TLS certificates (only applicable if use_tls is True)
            send_string: string, a string to send to the socket,
                         before reading a response
            match_re: string, a regular expression to search for in a response

            Other args as per BaseMonitor() spec
        """
        super(TCP, self).__init__(interval=interval, timeout=timeout, retries=retries)

        # name to show in generic state export
        self.name = 'tcp'

        ### port ###
        self.port = port
        if not isinstance(port, int) or port < 1 or port > 65535:
            log_msg = 'port "{}" must be an integer between 1 and 65535'.format(port)
            LOG.error(log_msg)
            raise Error(log_msg)

        ### use_tls ###
        self.use_tls = use_tls

        ### verify_tls ###
        self.verify_tls = verify_tls

        ### match_re ###
        self.match_re = match_re
        self._match_re_compiled = None
        if self.match_re is not None:
            if not isinstance(match_re, str) or len(match_re) > MAX_MATCH_RE_LEN:
                log_msg = 'match_re "{}" must be a string, {} chars max'.format(match_re, MAX_MATCH_RE_LEN)
                LOG.error(log_msg)
                raise Error(log_msg)

            # compile regexp obj to use for matching
            try:
                self._match_re_compiled = re.compile(self.match_re, flags=re.I)
            except Exception as e:
                log_msg = 'failed to compile a regular expression from "{}", {}'.format(self.match_re, e)
                LOG.error(log_msg)
                raise Error(log_msg)

        ### send_string ###
        self.send_string = send_string
        self._send_bytes = None
        if send_string is not None:
            if not isinstance(send_string, str) or len(send_string) > MAX_SEND_STRING_LEN:
                log_msg = 'send_string "{}" must be a string, {} chars max'.format(send_string, MAX_SEND_STRING_LEN)
                LOG.error(log_msg)
                raise Error(log_msg)

            # convert to bytes for sending over network
            self._send_bytes = self.send_string.encode()

    def run(self, dst_ip):
        """
        Connect a TCP socket (optionally with TLS)
        If we have a string to send, send it to the socket
        If have a regexp to match, read response and match the regexp

        args:
            dst_ip: string, IP address to connect to

        returns:
            None

        raises:
            MonitorFailed() on a socket operation timeout/error or if failed
            match the regexp.
        """
        tcp_sock = TCPSocket(ip=dst_ip, port=self.port, timeout=self.timeout)

        # Connect socket, wrap it in SSL if TLS is enabled
        try:
            tcp_sock.connect()

            # TLS handshake if use_tls is True
            if self.use_tls:
                context = ssl.create_default_context()

                # Disable TLS certificate verification if verify_tls is False
                if not self.verify_tls:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE

                # Wrap the socket in SSL/TLS
                tcp_sock.wrap_ssl(context=context)

            # Send string if provided
            if self.send_string is not None:
                tcp_sock.sendall(self._send_bytes)
        except ProtocolError as e:
            raise MonitorFailed(e)

        # if we have nothing to match, close the socket and return
        if self.match_re is None:
            tcp_sock.close()
            return

        # We have a regexp to match
        response_string = ''
        while True:
            try:
                recv_bytes = tcp_sock.recv()
            except ProtocolError as e:
                if response_string == '':
                    log_msg = 'got {error}, no data received from the peer'.format(error=e)
                else:
                    log_msg = ('failed to match the regexp within the timeout, '
                               'got {error}, response(up to 512 chars): {response_string}'
                               .format(error=e, response_string=response_string[:512]))
                raise MonitorFailed(log_msg)

            # remote side closed connection, no need to call sock.close()
            if recv_bytes == b'':
                if response_string == '':
                    log_msg = 'remote closed the connection, no data received from the peer'
                else:
                    log_msg = 'remote closed the connection, failed to match the regexp in the response(up to 512 chars): {}'.format(response_string[:512])
                raise MonitorFailed(log_msg)

            # received data
            else:
                response_string += recv_bytes.decode(errors='ignore')
                if self._match_re_compiled.search(response_string):
                    tcp_sock.close()
                    return
