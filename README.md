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

* Python/Fabric is needed for your client machine.
* Debian package "update-notifier-common" is needed on Debian machines.
    * Probably it is already installed on Ubuntu machines from the beginning.
* Prepare hosts.py that contains "HOSTS" as a list for a list of target hosts
* No prompt should be shown. That means, need pub-key auth for all hosts.

e.g. (hosts.py)

    HOSTS = ['mowa-net.jp', 'test.mowa-net.jp']

# Example

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
    mowanet: mowa-net.jp, centos.mowa-net.jp, deb.mowa-net.jp
    > check-linux-updates.py --upgrade-restart mowanet
    ..
    (check updates and upgrade commands to appropriate host in the group,
     rebooting them if needed)
    ..

# License

Apache2
