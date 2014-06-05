# check_updates.py
## What is this?

 * Checks updates on remote Linux machines via ssh, and shows a list of
   package updates.
 * Can parallelize or serialize the execution.
     * Requires appropriate public keys when you want parallel check.
     * Password authentication works only with serial check (--serial, -s).
 * Has an option for upgrading/rebooting each machine on demand.
     * Password-less sudo will be required on most of parallel checks.
     * With serial check you can enter password.
 * Supports both debian-like and redhat-like systems.
     * Sorry the original author does not manage other Unix/Linux systems.
     * Please don't expect W*ndows support.
 * "Host-Grouping" capability exists for convenience.
     * Useful for batch manipulation for a specific "region".
 * Developed with Python 2.7 + Fabric 1.8.3 + Paramiko 1.11.0 (Debian wheezy)
     * Tested with Ubuntu 12.04LTS, 14.04LTS, Debian sid, CentOS 6, Fedora 20
 * For local execution only, check ``check_local_updat.py`` instead.

## More details

 * Uses Python Fabric API.
     * "fab" command (Fabric's command line interface) is not used.
 * Private/public key handling and sudo handling is very immature at this point.
 * There is no capability to select authentication scheme at this point.
     * You will need to enter a password for each host
       when there's no private-key, password-less sudo is not configured, etc.

## Preparation

 * Python 2.7 must be ready on executing environment.
     * CentOS 6 seems NOT ready.
 * Needs Python/Fabric on your client machine (that runs this command)
     * "pip" command will be your friend.
 * Needs "update-notifier-common" is needed on target debian-like systems.
     * Already installed on some Ubuntu machines.
 * Prepare "hosts.py" that contains get_hosts() and get_host_groups() methods
   (See below)
     * get_hosts() should return all hosts you manage.
     * get_host_groups() should return a dictionary mapping group names to
       each host. All hosts here should be in get_hosts().
     * Multiple groups can contain same host names.

### Example hosts.py

    (hosts.py)
    
    hosts_mowanet = ['mowa-net.jp', 'test.mowa-net.jp', 'centos.mowa-net.jp']
    hosts_example = ['example.com', 'test.example.com', 'test2.example.com']
    hosts_centos = ['centos.mowa-net.jp', 'test2.example.com']
    
    # Duplicate entries should exist
    _HOSTS = hosts_mowanet + hosts_example + hosts_centos
    # Remove duplicate entries
    _UNIQUE_HOSTS = sorted(set(_HOSTS), key=_HOSTS.index)
    
    _HOST_GROUPS = {'mowa-net': hosts_mowanet,
                    'example': hosts_example,
                    'centos': hosts_centos}
    
    def get_hosts():
        return _UNIQUE_HOSTS
    
    def get_host_groups():
        return _HOST_GROUPS

## Example output

    > check-linux-updates.py
    example.com       :   6(6) (REBOOT-REQUIERD)
    test.example.com  :   2(1)
    mowa-net.jp       :   5(0)
    centos.mowa-net.jp:  14(?)
    
    > check-linux-updates.py --upgrade example.com
    ..
    (run upgrade command (apt-get dist-upgrade or yum upgrade)
    ..
    
    > check-linux-updates.py list_groups
    example : example.com, test.example.com, test2.example.com
    mowa-net: mowa-net.jp, test.mowa-net.jp, centos.mowa-net.jp
    centos  : centos.mowa-net.jp, test2.example.com
    
    > check-linux-updates.py --upgrade-restart mowa-net
    ..
    (check updates and request upgrade for appropriate hosts in the group,
     "mowa-net", rebooting them if needed)
    ..

# check_update_local.py

 * Local check version. No ssh. No auto-upgrade with sudo.
 * Shows the number of (security) updates on Linux systems with yum or apt.
 * On error an unusually high positive number ([60001,60100]) will be used.
     * Assumes the system does not have actual 60000 updates!
 * Mainly developed with Python2 (2.7), not Python3
     * CentOS 6 seems to have 2.6.6 by default. Be careful :-(
 * Tested on Debian wheezy 7.5, Ubuntu 12.04LTS/14.04LTS,
   CentOS 6, Fedora 20 (not on RHEL).
     * On Debian-like systems, requires "update-notifier-common" package.
     * On Redhat-like systems, requires appropriate package
         * "yum-plugin-security" (on Fedora11/CentOS6),
         * "yum-security" (on older Redhat).
     * On CentOS 6, you need to install argparse via pip
         * http://pip.readthedocs.org/en/latest/installing.html
         * ``pip2.6 install argparse``
         * Python 2.6 is barely supported.. :-P

# Example output

Example shows the system has 2 updates (including 1 security update),
requiring system reboot.

    $ check_update_local.py
    2
    $ check_update_local.py -s
    1
    $ check_update_local.py -r
    1

## I like Zabbix :-)

This local variant would be more useful with Zabbix Agent
than just the user's manual execution.

Try UserParameter like the following:

    UserParameter=mowa.updates,/var/lib/zabbix/check_update_local.py -q
    UserParameter=mowa.secupdates,/var/lib/zabbix/check_update_local.py -s -q
    UserParameter=mowa.reboots,/var/lib/zabbix/check_update_local.py -r -q

Reboot the agent and double-check if Zabbix Server is able to expect
those additional parameters.
For testing, zabbix_get command will be your friend.

    (Run this on "server" side, not on "agent" side that has the script)
    $ zabbix_get -s yourhost.exampl.com -k mowa.reboots
    1

# License

Copyright: Daisuke Miyakawa (d.miyakawa (a-t) gmail d-o-t com)
Licensed under Apache 2 License.

