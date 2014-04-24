# What is this?

 * Checks updates on Linux machiens (that is expected to run as a server).
 * Using Python Fabric via API.
     * "fab" command (Fabric's command line interface) is not used.
 * Has option for upgrading/rebooting each machine on demand.
 * Can parallelize or serialize the execution.
 * Supports CentOS and Ubuntu/Debian.
 * "Grouping" capability exists for convenience.
 * Tested with Python 2.7 + Fabric 1.8.3 + Paramiko 1.11.0
 * No capability to select authentication scheme at this point.
     * You will need to enter a password for each host
       when password-less sudo is not configured.
 * Not tested on venv.

# Preparation

 * Needs Python/Fabric on your client machine (that runs this command)
     * pip will be your friend
 * Needs "update-notifier-common" is needed on target Debian machines.
     * Already installed on some Ubuntu machines.
 * Prepare hosts.py that contains get_hosts() and get_host_groups() methods
   (See below)
     * get_hosts() should return all the hosts you manage.
     * get_host_groups() should return a dictionary mapping group names to
       each host. All hosts here should be in get_hosts().
     * Multiple groups can contain same host names.

# Example

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

Here's sample output:

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

# License

Apache2
