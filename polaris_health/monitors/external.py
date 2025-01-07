# -*- coding: utf-8 -*-

import logging
import subprocess
import re
from polaris_health import Error, MonitorFailed
from . import BaseMonitor

__all__ = ['ExternalScript']

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())

# maximum allowed length of match_re parameter
MAX_MATCH_RE_LEN = 128

class ExternalScript(BaseMonitor):
    """External script monitor."""

    def __init__(self, script_path, match_re=None, interval=10, timeout=5, retries=2):
        """
        args:
            script_path: string, the path to the external script to execute
            match_re: string, a regular expression to search for in the script output

            Other args as per BaseMonitor() spec
        """
        super(ExternalScript, self).__init__(interval=interval, timeout=timeout, retries=retries)

        # name to show in generic state export
        self.name = 'external_script'

        ### script_path ###
        self.script_path = script_path
        if not isinstance(script_path, str):
            log_msg = 'script_path must be a valid string, received "{}"'.format(script_path)
            LOG.error(log_msg)
            raise Error(log_msg)

        ### match_re ###
        self.match_re = match_re
        self._match_re_compiled = None
        if self.match_re is not None:
            if not isinstance(match_re, str) or len(match_re) > MAX_MATCH_RE_LEN:
                log_msg = 'match_re "{}" must be a string, {} chars max'.format(match_re, MAX_MATCH_RE_LEN)
                LOG.error(log_msg)
                raise Error(log_msg)
            try:
                self._match_re_compiled = re.compile(self.match_re, flags=re.I)
            except Exception as e:
                log_msg = 'failed to compile a regular expression from "{}": {}'.format(self.match_re, e)
                LOG.error(log_msg)
                raise Error(log_msg)

    def run(self, dst_ip):
        """
        Execute the external script and process the result.

        args:
            dst_ip: string, IP address to pass as an argument to the script

        returns:
            None

        raises:
            MonitorFailed if the script fails or if the match_re is not found
        """
        command = [self.script_path, dst_ip]
        try:
            # Run the external script and capture stdout and stderr
            result = subprocess.run(command, capture_output=True, timeout=self.timeout, text=True)
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            log_msg = 'external script timed out after {} seconds'.format(self.timeout)
            LOG.error(log_msg)
            raise MonitorFailed(log_msg)
        except subprocess.CalledProcessError as e:
            log_msg = 'external script failed with error: {}'.format(e)
            LOG.error(log_msg)
            raise MonitorFailed(log_msg)

        # Check if the script succeeded (exit code 0)
        if exit_code != 0:
            log_msg = 'external script failed with exit code {}: stderr={}'.format(exit_code, stderr)
            LOG.error(log_msg)
            raise MonitorFailed(log_msg)

        # If there's a match_re, match against the output
        if self.match_re is not None:
            if not self._match_re_compiled.search(stdout):
                log_msg = 'failed to match regexp "{}" in script output'.format(self.match_re)
                LOG.error(log_msg)
                raise MonitorFailed(log_msg)

        LOG.info('external script ran successfully with output: {}'.format(stdout))
