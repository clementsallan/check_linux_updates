#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
check_update_local.py

Shows the number of (security) updates on Linux systems with yum or apt.
Tested on Debian, Ubuntu, CentOS, Fedora (not on RHEL).

On Debian-like systems, requires "update-notifier-common" package.
On Redhat-like systems, requires "yum-plugin-security" (on Fedora11/CentOS6),
or "yum-security" (on older Redhat).

On error an unusually high positive number ([60001,60100]) will be used.

Copyright: Daisuke Miyakawa (d.miyakawa (a-t) gmail d-o-t com)
Licensed under Apache 2 License.
'''

import sys
# Actually not TESTED ;-P
if (sys.version_info[0], sys.version_info[1]) < (2, 6):
    raise RuntimeError('Not supported: {0}'.format(sys.version))

# argparse is available since Python 2.7, not 2.6
try:
    import argparse
except:
    print >>sys.stderr, (' argparse not available.'
                         ' Installing argparse with pip may solve the issue.')
    sys.exit(1)

from logging import getLogger
from logging import StreamHandler
from logging import DEBUG

try:
    from logging import NullHandler
except:
    from logging import Handler
    class NullHandler(Handler):
        def emit(self, record):
            pass

import os

from subprocess import Popen, PIPE, STDOUT
import shlex


ERROR_EXCEPTION_RAISED = 60002
ERROR_FAILED_TO_DETECT_SYSTEM = 60003
ERROR_MISC_ERROR = 60100

logger = getLogger(__name__)

class TesterBase(object):
    def needs_reboot(self):
        raise NotImplementedError()

    def get_update_count(self, is_security_updates):
        raise NotImplementedError()

    @classmethod
    def get_instance(cls, args):
        '''
        Checks a few files to detect which linux distribution is
        installed on the system, returning an appropriate object for it.
        Returns null when detection fails.
        '''
        if os.path.exists(DebianTester.DEBIAN_VERSION_FILE):
            logger.debug('{0} exists. Assuming debian-like system.'
                         .format(DebianTester.DEBIAN_VERSION_FILE))
            if logger.level <= DEBUG:
                f = open(DebianTester.DEBIAN_VERSION_FILE, 'r')
                logger.debug('debian-version: {0}'.format(f.read().rstrip()))
                if os.path.exists(DebianTester.LSB_RELEASE_FILE):
                    logger.debug('lsb-release found')
                    f = open(DebianTester.LSB_RELEASE_FILE)
                    for line in f:
                        logger.debug(line.rstrip())
            p = Popen(shlex.split('apt-get --version'),
                      stderr=STDOUT, stdout=PIPE)
            p.wait()
            if p.returncode != 0:
                logger.error('Failed to find apt-get')
                return None
            logger.debug('Result of "apt-get --version"')
            for line in p.stdout:
                logger.debug(line.rstrip())

            # apt-check exists only when "update-notifier-common" package
            # is installed on the Debian(-like) system.
            if not os.path.exists(DebianTester.APT_CHECK_FILE):
                logger.error('{0} does not exist while {1} exists.'
                             ' on debian-like systems this tool requires '
                             ' update-notifier-common package too.'
                             .format(DebianTester.APT_CHECK_FILE,
                                     DebianTester.DEBIAN_VERSION_FILE))
                return None
            return DebianTester()
        else:
            logger.debug('{0} does not exist'
                         .format(DebianTester.DEBIAN_VERSION_FILE))

        if os.path.exists(RedhatTester.REDHAT_RELEASE_FILE):
            logger.debug('{0} exists. Assuming redhat-like system.'
                         .format(RedhatTester.REDHAT_RELEASE_FILE))
            if logger.level <= DEBUG:
                f = open(RedhatTester.REDHAT_RELEASE_FILE)
                logger.debug('redhat-release: {0}'.format(f.read().rstrip()))

            p = Popen(shlex.split('yum --version'), stderr=STDOUT, stdout=PIPE)
            p.wait()
            if p.returncode != 0:
                logger.error('Failed to find yum')
                return None
            logger.debug('result of "yum --version"')
            for line in p.stdout:
                logger.debug(line.rstrip())
            return RedhatTester()


class DebianTester(TesterBase):
    '''
    Tester for debian (and ubuntu)
    '''

    DEBIAN_VERSION_FILE = '/etc/debian_version'
    APT_CHECK_FILE = '/usr/lib/update-notifier/apt-check'
    REBOOT_REQUIRED_FILE = '/var/run/reboot-required'
    # Probably ubuntu-specific
    LSB_RELEASE_FILE = '/etc/lsb-release'

    def needs_reboot(self):
        # Just check if reboot-required exists or not.
        if os.path.exists(self.REBOOT_REQUIRED_FILE):
            return True
        else:
            return False

    def get_update_count(self, is_security_updates=False):
        # Run apt-file command, expecting "updates;sec-updates" string.
        p = Popen([self.APT_CHECK_FILE], stderr=STDOUT, stdout=PIPE)
        p.wait()
        if (p.returncode > 0):
            raise RuntimeError('apt-check failed with {0}. err:\n{1}'
                               .format(p.returncode, p.stdout.read()))

        # '18;2' -> update 18, sec-update 2
        stdout_str = p.stdout.read()
        logger.debug('stdout: {0}'.format(stdout_str))
        (updates, sec_updates) = stdout_str.split(';')
        if is_security_updates:
            return int(sec_updates)
        else:
            return int(updates)


class RedhatTester(TesterBase):
    '''
    Tested on CentOS and Fedora, not RHEL :-P
    '''
    REDHAT_RELEASE_FILE = '/etc/redhat-release'

    def needs_reboot(self):
        cmd1 = 'rpm -q --last kernel'
        p1 = Popen(shlex.split(cmd1), stderr=PIPE, stdout=PIPE)
        p1.wait()
        if p1.returncode:
            raise RuntimeError('Failed to run "{0}" (ret: {1}). stderr:\n{2}'
                               .format(cmd1, p1.returncode,
                                       str(p1.stderr.read().rstrip())))
        # e.g. "kernel-2.6.32-431.17.1.el6.x86_64   Thu May 15 20:00:00 2014"
        latest_kernel_line = p1.stdout.read().split()[0]
        logger.debug('latest_kernel_line: {0}'.format(latest_kernel_line))
        cmd2 = 'uname -r'
        p2 = Popen(shlex.split(cmd2), stderr=PIPE, stdout=PIPE)
        p2.wait()
        if p2.returncode:
            raise RuntimeError('Failed to run "{0}" (ret: {1}). stderr:\n{2}'
                               .format(cmd2, p2.returncode,
                                       p2.stderr.read().rstrip()))
        # e.g. "2.6.32-431.17.1.el6.x86_64"
        current_kernel = p2.stdout.read().rstrip()
        logger.debug('current_kernel: {0}'.format(current_kernel))
        # Because rpm result contains not only kernel version but also
        # date and other info, don't use "!=" but "not in". 
        return current_kernel not in latest_kernel_line

    def get_update_count(self, is_security_updates=False):
        if is_security_updates:
            cmd = 'yum --security check-update'
        else:
            cmd = 'yum check-update'
        p = Popen(shlex.split(cmd), stderr=PIPE, stdout=PIPE)
        p.wait()

        # yum returns 0 when there's no update and returns 100
        # when there are update(s).
        # Will return 1 on error, but be a bit more pessimistic here.
        if p.returncode != 0 and p.returncode != 100:
            raise RuntimeError('Failed to run "{0}" (ret: {1}). stderr:\n{2}'
                               .format(cmd, p.returncode,
                                       p.stderr.read().rstrip()))
        output = p.stdout.read()
        update_lines = filter(lambda x: x.rstrip().endswith('updates'),
                              output.split('\n'))
        return len(update_lines)


def main():
    parser = argparse.ArgumentParser(
        description=('Check if update is available. Returns num of updates'))
    parser.add_argument('--log', default='INFO',
                        help=('Set Python log level. e.g. DEBUG, INFO, WARN'))
    parser.add_argument('-d', '--debug', action='store_true',
                        help=('Shortcut for --log DEBUG'))
    parser.add_argument('-s', '--security-updates',
                        action='store_true',
                        help=('Instead of showing num of updates,'
                              ' show num of security updates.'))
    parser.add_argument('-r', '--reboot_required',
                        action='store_true',
                        help=('Instead of showing num of updates,'
                              ' return 1 if reboot is required'))
    parser.add_argument('-q', '--quiet',
                        action='store_true',
                        help='Logging will be disabled entirely.')
    args = parser.parse_args()
    if args.debug:
        args.log = 'DEBUG'
    if args.quiet:
        handler = NullHandler()
    else:
        handler = StreamHandler()

    level = args.log.upper()
    # Python 2.6 does not accept level as a string.
    if (sys.version_info[0], sys.version_info[1]) == (2, 6):
        from logging import CRITICAL, FATAL, ERROR, WARNING, WARN, INFO, NOTSET
        compatMap = {
            'CRITICAL' : CRITICAL,
            'ERROR' : ERROR,
            'WARN' : WARNING,
            'WARNING' : WARNING,
            'INFO' : INFO,
            'DEBUG' : DEBUG,
            'NOTSET' : NOTSET,
            }
        if level.isalpha():
            if compatMap.has_key(level):
                level = compatMap[level]
            else:
                raise ValueError("Unknown level: {0}".formatlevel)

    logger.setLevel(level)
    handler.setLevel(level)
    logger.addHandler(handler)
    logger.debug('Started.')
    try:
        tester = TesterBase.get_instance(args)
        if not tester:
            logger.error('Failed to find appropriate tester')
            print(ERROR_FAILED_TO_DETECT_SYSTEM)
            return
        if args.reboot_required:
            if tester.needs_reboot():
                print(1)
            else:
                print(0)
        else:
            print(tester.get_update_count(
                is_security_updates=args.security_updates))
    except Exception as e:
        logger.error('Exception raised', e)
        import traceback
        logger.error(traceback.format_exc())
        print(ERROR_EXCEPTION_RAISED)
    logger.debug('Finished')


if __name__ == '__main__':
    main()

