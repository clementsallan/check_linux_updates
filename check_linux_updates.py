#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import argparse
from getpass import getpass

from fabric.api import hide,sudo,run
from fabric.context_managers import shell_env
from fabric.contrib.files import exists
from fabric.tasks import execute
from fabric.state import env
from fabric.utils import abort,error,puts,warn

import paramiko
import socket

# Prepare those function by yourself.
from hosts import get_hosts, get_host_groups

# http://stackoverflow.com/questions/1956777/
def _is_host_up(host, port):
    original_timeout = socket.getdefaulttimeout()
    new_timeout = 3
    socket.setdefaulttimeout(new_timeout)
    try:
        paramiko.Transport((host, port))
        return True
    except:
        return False
    finally:
        socket.setdefaulttimeout(original_timeout)


def _get_update_line(host, updates, sec_updates, reboot_required,
                     packages=None):
    updates_str = '{}({})'.format(updates, sec_updates)
    ret = ((u'{:<%d}: {:>6}' % env.host_column_size)
           .format(host, updates_str))
    if reboot_required:
        ret += ' (REBOOT-REQUIRED)'
    if packages:
        ret += '\n  {}'.format(', '.join(packages))
    return ret


def _print_update_line(host, updates, sec_updates, reboot_required,
                       packages=None):
    print(_get_update_line(host, updates, sec_updates, reboot_required,
                           packages))


def check_debian_updates():
    quiet = not env.args.verbose
    if env.args.refresh:
        result = sudo('apt-get update', warn_only=True, quiet=quiet)
        if result.failed:
            error('{}: apt-get update failed.'.format(env.host))
            return

    # Ubuntu or Debian with additional apt-check
    if not exists('/usr/lib/update-notifier/apt-check'):
        print((u'{:<%d}: (apt-check is not available)'
               % env.host_column_size)
              .format(env.host))
        return None
    result = run('/usr/lib/update-notifier/apt-check',
                 warn_only=True,
                 quiet=quiet)
    if result.failed:
        error('{}: apt-check failed.'.format(env.host))
        return None
    (updates, sec_updates) = map(lambda x: int(x),
                                 str(result.stdout).split(';'))
    reboot_required = exists('/var/run/reboot-required')
    if updates or sec_updates or reboot_required or env.args.verbose:
        if env.args.show_packages:
            result = sudo('apt-get -s upgrade', warn_only=True, quiet=quiet)
            if result.succeeded:
                do_check_next = False
                packages = None
                for line in str(result.stdout).split('\n'):
                    if do_check_next:
                        packages = line.split()
                        break
                    elif 'The following packages will be upgraded' in line:
                        do_check_next = True
                        pass
                    pass
                if packages:
                    _print_update_line(env.host, updates, sec_updates,
                                       reboot_required, packages)
                else:
                    warn('No packages found for {}'.format(env.host))

        else:
            _print_update_line(env.host, updates, sec_updates, reboot_required)

    return (updates, sec_updates, reboot_required)


def check_centos_updates():
    quiet = not env.args.verbose
    # CentOS
    result = run('command -v yum >& /dev/null', quiet=quiet)
    if result.failed:
        error('{}: yum does not exist'.format(env.host))
        return None
    if quiet:
        cmd = 'yum --quiet check-update'
    else:
        cmd = 'yum check-update'

    # warn_only is not used because yum returns 100 even on successful cases,
    # while warn_only treats it as error case, showing "Warning".
    result = run(cmd, quiet=True)

    # yum returns 0 when there's no update and returns 100
    # when there are update(s).
    # Will return 1 on error, but be a bit more pessimistic here.
    if result.return_code != 0 and result.return_code != 100:
        error('yum failed with return_code "{}"'.format(result.return_code))
        return None

    output = str(result.stdout)

    update_lines = filter(lambda x: x.rstrip().endswith('updates'),
                          output.split('\n'))
    # Count the number of lines that contain "update" at the end.
    updates = len(update_lines)
    if env.args.show_packages:
        packages = []
        for update in update_lines:
            packages.append(update.split()[0]
                            .rstrip('.x86_64')
                            .rstrip('.x386')
                            .rstrip('.noarch'))
    else:
        packages = None

    # It seems there's no way whether each is for security or not..
    sec_updates = '?'

    result_1 = run('rpm -q --last kernel', quiet=quiet)
    result_2 = run('uname -r', quiet=quiet)
    if result_1.succeeded and result_2.succeeded:
        # e.g. "kernel-2.6.32-431.11.2.el6.x86_64"
        latest_line = str(result_1.stdout).split()[0]
        # e.g. "2.6.32-431.11.2.el6.x86_64"
        current = str(result_2.stdout)
        reboot_required = current not in latest_line
    else:
        reboot_required = '?'
   
    if updates or reboot_required or env.args.verbose:
        _print_update_line(env.host, updates, sec_updates, reboot_required,
                           packages)

    return (updates, 0, reboot_required)


def upgrade_debian():
    # Show updates by default.
    quiet = env.args.quiet
    sudo('apt-get -y dist-upgrade', warn_only=True, quiet=quiet)


def upgrade_centos():
    # Show updates by default.
    quiet = env.args.quiet
    sudo('yum -y upgrade', warn_only=True, quiet=quiet)


def do_check_updates():
    quiet = not env.args.verbose
    if not _is_host_up(env.host, int(env.port)):
        warn('Host {} on port {} is down.'.format(env.host, env.port))
        return

    result = run('command -v apt-get >& /dev/null', quiet=True)
    is_debian = result.succeeded
    
    if is_debian:
        result = check_debian_updates()
    else:
        result = check_centos_updates()

    if result:
        upgrade_done = False
        (updates, sec_updates, reboot_required) = result
        if (updates or sec_updates) and env.args.upgrade:
            puts('Upgrading {}'.format(env.host))
            if is_debian:
                upgrade_debian()
            else:
                upgrade_centos()
            upgrade_done = True
        if (upgrade_done or reboot_required) and env.args.upgrade_restart:
            puts('Rebooting {}'.format(env.host))
            sudo('reboot', warn_only=True, quiet=quiet)
    if env.args.verbose:
        puts('Finished')


def do_sanity_check():
    result = run('uname -s')
    if str(result.stdout) != 'Linux':
        abort('{} is Non-Linux machine.'.format(env.host))


def main():
    parser = argparse.ArgumentParser(
        description=u'Checks if remote hosts need update or not.')
    parser.add_argument('--refresh',
                        help=(u'Run apt-get update on Debian/Ubuntu.'),
                        action='store_true')
    parser.add_argument('--sanity-check',
                        help=(u'Executes sanity check toward each host'
                              u' serially (not in parallel).'
                              u' If some hosts show prompt in the check phase,'
                              u' this command will abort itself immediately.'
                              u' Might be useful for "debugging" new hosts.'),
                        action='store_true')
    parser.add_argument('-s', '--serial',
                        help=u'Executes check serially',
                        action='store_true')
    parser.add_argument('--upgrade',
                        help=(u'Request hosts actually upgrade itself'
                              u' when necessary.'
                              u' Note that this will execute "dist-upgrade"'
                              u' on debian(-like) OSes, not "upgrade.'),
                        action='store_true')
    parser.add_argument('--upgrade-restart',
                        help=(u'Request hosts actually upgrade itself'
                              u' and restart when update is available.'
                              u' Note that, with this option, restart'
                              u' will be executed regardless of the OS\'s'
                              u' "Reboot-Required" status.'
                              u' Note that this will execute "dist-upgrade"'
                              u' on debian(-like) OSes, not "upgrade.'),
                        action='store_true')
    parser.add_argument('hosts', metavar='HOST',
                        type=str,
                        nargs='*',
                        help=(u'Host names or host groups. If not specified,'
                              u' default hosts configuration will be used.'
                              u' This may allow "all" "list", "list_groups".'))
    parser.add_argument('-q', '--quiet',
                        action='store_true',
                        help=u'Suppress unnecessary output.')
    parser.add_argument('--show-packages',
                        action='store_true',
                        help=(u'This will show names of packages'
                              u' to be upgraded.'))
    parser.add_argument('-v', '--verbose',
                        action='store_true',
                        help=u'Show verbose outputs, including Fabric ones.')
    args = parser.parse_args()        
    output_groups = ()
    if args.verbose:
        output_groups = ()
        args.quiet = False
    elif args.quiet:
        output_groups = ('everything', 'status')
    else:
        output_groups = ('running', 'status')

    with hide(*output_groups), shell_env(LANG='C'):
        if (args.upgrade or args.upgrade_restart) and not args.hosts:
            abort(u'--upgrade/--upgrade-restart toward all hosts not allowed'
                  u' by default.'
                  u' Consider using "all" for host, forcing what you want.')

        if args.hosts:
            groups = get_host_groups()
            if len(args.hosts) == 1 and args.hosts[0] == 'all':
                hosts = get_hosts()
            elif len(args.hosts) == 1 and args.hosts[0] == 'list':
                print('\n'.join(get_hosts()))
                return
            elif len(args.hosts) == 1 and args.hosts[0] == 'list_groups':
                column_size = reduce(lambda x,y: max(x, len(y)),
                                     groups.keys(), 0)
                for key, value in groups.iteritems():
                    print((u'{:<%d}: {}' % column_size)
                          .format(key, ', '.join(value)))
                return

            hosts = []
            for host in args.hosts:
                if groups.has_key(host):
                    hosts.extend(groups[host])
                else:
                    hosts.append(host)
        else:
            hosts = get_hosts()
        if not hosts:
            abort('No hosts provided.')

        # Determine left-most column size.
        # It should be same as length of host name with maximum characters.
        # e.g.
        # ['mn.to', 'mowa-net.jp', 'test.mowa-net.jp']
        # -> 17 (== len('test.mowa-net.jp'))
        env.host_column_size = reduce(lambda x,y: max(x, len(y)), hosts, 0)

        if args.upgrade_restart:
            args.upgrade = True

        # On serial execution there's no need to abort on prompts.
        # Also assume serial execution when there's just one host.
        if len(hosts) == 1:
            args.serial = True
        env.parallel = not args.serial
        env.abort_on_prompts = not args.serial

        # Remember our args.
        env.args = args            
        if args.sanity_check:
            puts('Start sanity check')
            execute(do_sanity_check, hosts=hosts)
        execute(do_check_updates, hosts=hosts)


if __name__ == '__main__':
    main()
