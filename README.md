# What is this?

 * Checks updates on Linux boxes.
 * Has option for upgrading/rebooting each machine on demand.
 * Can parallelize or serialize the execution.
 * Supports CentOS and Ubuntu/Debian.
 * No capability to select authenticatio scheme at this point
     * You may need to enter password for each host when password-less sudo
     is not allowed.
 * "Grouping" capability exists.

# Preparation

* Needs Python/Fabric on your client machine (that runs this command)
* Needs "update-notifier-common" is needed on target Debian machines.
    * Already installed on some Ubuntu machines.
* Prepare hosts.py that contains get_hosts() and get_host_groups() methods
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
    example.com       : updates:   6(6), reboot-required: True
    test.example.com  : updates:   2(1), reboot-required: False
    mowa-net.jp       : updates:   5(0), reboot-required: False
    centos.mowa-net.jp: updates:  14(?), reboot-required: False
    
    > check-linux-updates.py --upgrade example.com
    ..
    (run upgrade command (apt-get dist-upgrade or yum upgrade)
    ..
    
    > check-linux-updates.py list_groups
    example: example.com, test.example.com, test2.example.com
    mowanet: mowa-net.jp, test.mowa-net.jp, centos.mowa-net.jp
    centos : centos.mowa-net.jp, test2.example.com
    
    > check-linux-updates.py --upgrade-restart mowa-net
    ..
    (check updates and request upgrade for appropriate hosts in the group,
     "mowa-net", rebooting them if needed)
    ..

# License

Apache2
