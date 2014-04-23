#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import argparse

from fabric.contrib.files import exists
from fabric.api import hide,run
from fabric.tasks import execute
from fabric.state import env
from fabric.utils import abort,error

# Prepare it yourself
from hosts import HOSTS
# HOSTS = ['localhost']

def get_update_line(host, updates, sec_updates, reboot_required):
    updates_str = '{}({})'.format(updates, sec_updates)
    return ((u'{:<%d}: updates: {:>6}, reboot-required: {}'
             % env.host_column_size)
            .format(host, updates_str, reboot_required))


def _print_update_line(host, updates, sec_updates, reboot_required):
    print(get_update_line(host, updates, sec_updates, reboot_required))


def check_debian_updates():
    # Ubuntu or Debian with additional apt-check
    if not exists('/usr/lib/update-notifier/apt-check'):
        print((u'{:<%d}: (apt-check is not available)'
               % env.host_column_size)
              .format(env.host))
        return
    result = run('/usr/lib/update-notifier/apt-check', quiet=True)
    if result.failed:
        error('{}: apt-check failed.'.format(env.host))
        return
    (updates, sec_updates) = map(lambda x: int(x),
                                 str(result.stdout).split(';'))
    reboot_required = exists('/var/run/reboot-required')
    if updates or sec_updates or reboot_required:
        _print_update_line(env.host, updates, sec_updates, reboot_required)


def check_centos_updates():
    # CentOS
    result = run('command -v yum >& /dev/null', quiet=True)
    if result.failed:
        error('{}: yum does not exist'.format(env.host))
        return
    result = run('yum --quiet check-update', quiet=True)
    # yum returns 0 when there's no update and returns 100
    # when there are update(s).
    # Will return 1 on error, but be a bit more pessimistic here.
    if result.return_code != 0 and result.return_code != 100:
        error('yum failed')
        return
    # Each line will contain actual package names to be updated.
    # Just count the number of lines here.
    # split('\n') will return [''] for an empty result. Filter it.
    updates = len(filter(lambda x: x, str(result.stdout).split('\n')))
    # It seems there's no way whether each is for security or not..
    sec_updates = '?'

    result_1 = run('rpm -q --last kernel', quiet=True)
    result_2 = run('uname -r', quiet=True)
    if result_1.succeeded and result_2.succeeded:
        # e.g. "kernel-2.6.32-431.11.2.el6.x86_64"
        latest_line = str(result_1.stdout).split()[0]
        # e.g. "2.6.32-431.11.2.el6.x86_64"
        current = str(result_2.stdout)
        reboot_required = current not in latest_line
    else:
        reboot_required = '?'
   
    if updates or reboot_required:
        _print_update_line(env.host, updates, sec_updates, reboot_required)


def do_check_updates():
    result = run('command -v apt-get >& /dev/null', quiet=True)
    if result.succeeded:
        check_debian_updates()
    else:
        check_centos_updates()


def do_sanity_check():
    result = run('uname -s')
    if str(result.stdout) != 'Linux':
        abort('{} is Non-Linux machine.'.format(env.host))


def main():
    hosts = HOSTS
    env.abort_on_prompts = True
    env.host_column_size = reduce(lambda x,y: max(x, len(y)), hosts, 0)
    env.parallel = True
    with hide('everything', 'status'):
        execute(do_sanity_check, hosts=hosts)
    with hide('everything', 'status'):
        execute(do_check_updates, hosts=hosts)


if __name__ == '__main__':
    main()
