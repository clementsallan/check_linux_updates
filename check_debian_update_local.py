#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
check_debian_update_local.py

Locally runs "/usr/lib/update-notifier/apt-check" command and 
shows (via stdout) the number of updates on Debian/Ubuntu.
The command itself is part of update-notifier-common package,
you may need to prepare it beforehand.

Shows a unusually high number on error.
This is because Zabbix Agent won't handle negative number.
Typically more than 60000.

If you want to use this with zabbix-agentd, consider UserParameter.

e.g.
UserParameter=mowa.updates,/var/lib/zabbix/check_debian_update_local.py
UserParameter=mowa.secupdates,/var/lib/zabbix/check_debian_update_local.py -s
UserParameter=mowa.reboots,/var/lib/zabbix/check_debian_update_local.py -r

Reboot the agent and check if Zabbix Server side can use these
additional parameters. zabbix_get command will be your friend.

(on server side)
$ zabbix_get -s yourhost.exampl.com -k mowa.reboots
1

Copyright: Daisuke Miyakawa (d.miyakawa (a-t) gmail d-o-t com)
Licensed under Apache 2 License.
'''

import argparse
from logging import getLogger
from logging import StreamHandler
from logging import NullHandler
from logging import DEBUG

import os

import subprocess
import shlex

ERROR_SYSTEM_NOT_READY = 60001
ERROR_EXCEPTION_RAISED = 60002
ERROR_MISC_ERROR = 60100

logger = getLogger(__name__)

APT_CHECK_FILE = '/usr/lib/update-notifier/apt-check'
REBOOT_REQUIRED_FILE = '/var/run/reboot-required'


def get_update_count(args):
    if args.reboot_required:
        if os.path.exists(REBOOT_REQUIRED_FILE):
            return 1
        else:
            return 0

    p = subprocess.Popen([APT_CHECK_FILE],
                         stderr=subprocess.STDOUT,
                         stdout=subprocess.PIPE)
    p.wait()

    if (p.returncode > 0):
        logger.error('Return-code: {}'.format(p.returncode))
        logger.error(p.stdout.read())
        return
    # '18;2' -> update 18, sec-update 2
    stdout_str = p.stdout.read()
    logger.debug('stdout: {}'.format(stdout_str))
    (updates, sec_updates) = stdout_str.split(';')
    if args.security_updates:
        return sec_updates
    else:
        return updates


def main():
    parser = argparse.ArgumentParser(
        description=('Check if update is available. Returns num of updates'))
    parser.add_argument('--log',
                        action='store',
                        default='INFO',
                        help=('Set Python log level. e.g. DEBUG, INFO, WARN.'))
    parser.add_argument('-s', '--security-updates',
                        action='store_true')
    parser.add_argument('-r', '--reboot_required',
                        action='store_true',
                        help=('Instead of showing num of updates,'
                              ' return 1 if reboot is required'))
    parser.add_argument('-q', '--quiet',
                        action='store_true',
                        help='Logging will be disabled entirely.')
    args = parser.parse_args()
    if args.quiet:
        handler = NullHandler()
    else:
        handler = StreamHandler()
    logger.setLevel(args.log.upper())
    handler.setLevel(args.log.upper())
    logger.addHandler(handler)

    # apt-check exists only when "update-notifier-common" package
    # is installed on the Debian(-like) system.
    if not os.path.exists(APT_CHECK_FILE):
        logger.error('{} does not exist.'
                     ' This script only works with debian(-like) systems'
                     ' with update-notifier-common package.')
        print(ERROR_SYSTEM_NOT_READY)

    try:
        logger.debug('Start running.')
        print(get_update_count(args))
    except Exception as e:
        logger.error('Exception raised', e)
        import traceback
        logger.error(traceback.format_exc())
        print(ERROR_EXCEPTION_RAISED)


if __name__ == '__main__':
    main()

