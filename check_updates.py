#!/usr/bin/python
# -*- coding: utf-8 -*-

'''
Utility that checks if specified Linux (Ubuntu/CentOS) hosts
need to be updated or not.
'''

from __future__ import print_function

import argparse

from fabric.api import hide,sudo,run
from fabric.context_managers import shell_env
from fabric.contrib.files import exists
from fabric.tasks import execute
from fabric.state import env
from fabric.utils import abort,error,puts,warn

import paramiko
import socket

import fabwrap

# Prepare those function by yourself.
from hosts import get_hosts, get_host_groups

from utils import query_yes_no


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
    elif reboot_required == None:
        ret += ' (REBOOT-STATUS-UNKNOWN)'
    if packages:
        ret += '\n  {}'.format(', '.join(packages))
    return ret


def _print_update_line(host, updates, sec_updates, reboot_required,
                       packages=None):
    print(_get_update_line(host, updates, sec_updates, reboot_required,
                           packages))


def check_reboot_required_debian():
    return exists('/var/run/reboot-required')


def check_updates_debian(apt_command):
    '''
    Returns (updates, sec_updates, reboot_required) when successful.
    Returns None on failure.
    '''
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
    reboot_required = check_reboot_required_debian()
    if updates or sec_updates or reboot_required or env.args.verbose:
        if env.args.show_packages:
            result = sudo('{} -s upgrade'.format(apt_command),
                          warn_only=True, quiet=quiet)
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


def check_reboot_required_centos():
    '''
    * True == Reboote Required
    * False == Reboot not Required
    * None == unknown
    '''
    quiet = not env.args.verbose
    result_1 = run('rpm -q --last kernel', quiet=quiet)
    result_2 = run('uname -r', quiet=quiet)
    if result_1.succeeded and result_2.succeeded:
        # e.g. "kernel-2.6.32-431.11.2.el6.x86_64"
        latest_line = str(result_1.stdout).split()[0]
        # e.g. "2.6.32-431.11.2.el6.x86_64"
        current = str(result_2.stdout)
        reboot_required = current not in latest_line
    else:
        reboot_required = None
    return reboot_required

def run_yum_check_update(security=False):
    '''
    Returns (updates, packages).
    Note packages will be useful only when env.args.show_packages is set.
    '''
    quiet = env.args.quiet
    options = []
    if security: options.append('--security')
    if quiet:    options.append('--quiet')
    cmd = 'yum {} check-update'.format(' '.join(options))

    # yum returns 0 when there's no update and returns 100 there are updates.
    # On the other hand Fabric treats the return code 100 as "error".
    # To suppress meaningless warning, refrain using "warn_only" flag here.
    result = run(cmd, quiet=True)

    # yum returns 1 on error.
    # Here, treat non-0 and non-100 as an error just in case.
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
    return (updates, packages)

def check_updates_centos():
    '''
    Returns (updates, sec_updates, reboot_required) when successful.
    Returns None on failure.
    '''
    (updates, packages) = run_yum_check_update(False)
    (sec_updates, _) = run_yum_check_update(True)
    reboot_required = check_reboot_required_centos()

    # Note: reboot_required == None means 'Unknown',
    # in which case we want to show the line.
    if (updates or reboot_required or reboot_required == None
        or env.args.verbose):
        _print_update_line(env.host, updates, sec_updates, reboot_required,
                           packages)

    return (updates, 0, reboot_required)


def upgrade_debian(apt_command):
    # Show updates by default.
    quiet = env.args.quiet
    if env.args.dist_upgrade:
        sudo('{} -y dist-upgrade'.format(apt_command),
             warn_only=True, quiet=quiet)
    else:
        sudo('{} -y upgrade'.format(apt_command),
             warn_only=True, quiet=quiet)


def upgrade_centos():
    # Show updates by default.
    quiet = env.args.quiet
    sudo('yum -y upgrade', warn_only=True, quiet=quiet)


def do_check_updates():
    quiet = not env.args.verbose
    if not _is_host_up(env.host, int(env.port)):
        warn('Host {} on port {} is down.'.format(env.host, env.port))
        return

    # Contains apt_get/aptitude command. None on CentOS
    apt_command = None

    if env.args.prefer_aptitude:
        result_aptitude = run('command -v aptitude >& /dev/null', quiet=True)
        result_aptget = run('command -v apt-get >& /dev/null', quiet=True)
        if result_aptitude.succeeded:
            apt_command = 'aptitude'
        elif result_aptget.succeeded:
            warn(('Host {} does not have aptitude command'
                  ' while aptitude is preferred.'
                  ' Will use apt-get instead.')
                 .format(env.host))
            apt_command = 'apt-get'
    else:
        result_aptget = run('command -v apt-get >& /dev/null', quiet=True)
        if result_aptget.succeeded:
            apt_command = 'apt-get'
    if not apt_command:
        result = run('command -v yum >& /dev/null', quiet=quiet)
        if result.failed:
            error('Host {} does not have apt or yum. Exitting.'
                  .format(env.host))
            return

    if apt_command:
        result = check_updates_debian(apt_command)
    else:
        result = check_updates_centos()

    if result:
        upgrade_done = False
        (updates, sec_updates, reboot_required) = result
        if (updates or sec_updates):
            do_upgrade = False
            if env.args.auto_upgrade:
                do_upgrade = True
            elif env.args.ask_upgrade:
                do_upgrade = ('yes' == query_yes_no('Upgrade "{}"? '
                                                    .format(env.host)))

            if do_upgrade:
                puts('Upgrading {}'.format(env.host))
                if apt:
                    upgrade_debian(apt)
                else:
                    upgrade_centos()
                upgrade_done = True

                if apt_command:
                    reboot_required = check_reboot_required_debian(apt_command)
                else:
                    reboot_required = check_reboot_required_centos()

        if upgrade_done or reboot_required:
            do_reboot = False
            if env.args.auto_upgrade_restart:
                do_reboot = True
            elif reboot_required and env.args.ask_upgrade:
                do_reboot = ('yes' == query_yes_no('Reboot "{}"? '
                                                   .format(env.host)))
            if do_reboot:
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
    parser.add_argument('hosts', metavar='HOST', type=str, nargs='*',
                        help=(u'Host names or host groups. If not specified,'
                              u' default hosts configuration will be used.'
                              u' This may allow special command "all" "list",'
                              u' "groups" (= "list_groups").'))
    parser.add_argument('-s', '--serial', action='store_true',
                        help=u'Executes check in serial manner')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help=u'Suppress unnecessary output.')
    parser.add_argument('-n', '--nonregistered', action='store_true',
                        help=u'Allow host names that are not registered')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help=u'Show verbose outputs, including Fabric ones.')
    parser.add_argument('--ask-upgrade', action='store_true',
                        help=(u'Asks if upgrade should be done when'
                              u' appropriate.'
                              u' Only effective when --serial (-s) option'
                              u' is set'))
    parser.add_argument('--auto-upgrade', action='store_true',
                        help=(u'Requests hosts to upgrade itself'
                              u' when necessary.'))
    parser.add_argument('--dist-upgrade', action='store_true',
                        help=(u'Use "dist-upgrade" instead of "upgrade".'
                              u' Only effective with debian-like systems.'
                              u' Meaningless on redhat-like systems.'))
    parser.add_argument('--auto-upgrade-restart', action='store_true',
                        help=(u'Requests hosts to upgrade itself'
                              u' and restart when upgrade is finished.'
                              u' With this option restart'
                              u' will be executed regardless of necessity'
                              u' (with/without "Reboot-Required" status).'
                              u' This will execute "dist-upgrade"'
                              u' on debian(-like) OSes, not "upgrade.'))
    parser.add_argument('--refresh', action='store_true',
                        help=(u'Run "apt-get update" on debian-like systems.'))
    parser.add_argument('--show-packages', action='store_true',
                        help=(u'This will show names of packages'
                              u' to be upgraded.'))
    parser.add_argument('--sanity-check', action='store_true',
                        help=(u'First executes sanity check toward each host'
                              u' serially (not in parallel).'
                              u' If some hosts show prompt in the check phase,'
                              u' this command will abort itself immediately.'
                              u' Might be useful for "debugging" new hosts.'
                              u' If you are considering --serial option,'
                              u' This "check" would be meaningless.'))
    parser.add_argument('--prefer-aptitude', action='store_true',
                        help=(u'Try using "aptitude" instead of "apt-get"'
                              u' on debian-like systems.'
                              u' If not available, use "apt-get" anyway.'))
    args = parser.parse_args()
    output_groups = ()
    if args.verbose:
        output_groups = ()
        args.quiet = False
    elif args.quiet:
        output_groups = ('everything', 'status')
    else:
        output_groups = ('running', 'status')

    fabwrap.setup()    

    with hide(*output_groups), shell_env(LANG='C'):
        if ((args.auto_upgrade or args.auto_upgrade_restart)
            and not args.hosts):
            abort(u'--auto-upgrade/--auto-upgrade-restart toward all hosts'
                  u' not allowed by default.'
                  u' Consider using "all" for host param,'
                  u' which will do what you want.')

        # If there are one ore more "host" arguments are available,
        # Try the following;
        # 1. If the *first* argument is actually a special sequence like "all",
        #    "list", etc., then run a special sequence and exit the app.
        #    Other arguments will be ignored then even if they exist.
        # 2. For each "host" argument, do the following;
        #   2.1 if it looks a host group,
        #       mark all hosts in the group as check targets.
        #   2.2 if it looks registered host name,
        #       mark it as a check target.
        #   2.3 if it looks part of a *single* registered host name,
        #       mark it as a target.
        #   2.4 if there are multiple candidates for the argument,
        #       show an error and exit the app without actual check.
        #   2.5 if "-n" option is set, mark the host name as a target silently.
        if args.hosts:
            groups = get_host_groups()
            if len(args.hosts) == 1 and args.hosts[0] == 'all':
                hosts = get_hosts()
                args.hosts = []
            elif len(args.hosts) == 1 and args.hosts[0] == 'list':
                print('\n'.join(get_hosts()))
                return
            elif (len(args.hosts) == 1
                  and (args.hosts[0] == 'list-groups'
                       or args.hosts[0] == 'list_groups'
                       or args.hosts[0] == 'groups')):
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
                elif host in get_hosts():
                    hosts.append(host)
                else:
                    filtered = filter(lambda x: host in x, get_hosts())
                    if len(filtered) == 1:
                        hosts.append(filtered[0])
                    elif len(filtered) > 1:
                        abort('Multiple candidates for "{}"'.format(host))
                    elif args.nonregistered:
                        hosts.append(host)
                    else:
                        abort('No idea how to handle "{}"'.format(host))
                
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

        if args.auto_upgrade_restart:
            args.auto_upgrade = True

        # On serial execution there's no need to abort on prompts.
        # Also assume serial execution when there's just one host.
        if len(hosts) == 1:
            args.serial = True
        env.parallel = not args.serial
        env.abort_on_prompts = not args.serial

        if args.ask_upgrade:
            if not args.serial:
                abort('--ask-upgrade is useless on parallel mode.')
            if args.auto_upgrade:
                abort('--ask-upgrade is useless when auto-upgrade is enabled.')

        # Remember our args.
        env.args = args
        if args.sanity_check:
            puts('Start sanity check')
            execute(do_sanity_check, hosts=hosts)
        execute(do_check_updates, hosts=hosts)


if __name__ == '__main__':
    main()
