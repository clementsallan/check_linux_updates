# What is this?

Check updates on Linux boxes. Includes CentOS and Ubuntu/Debian support.

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

* Shows updates(security-updates), reboot-required
    * CentOS will show '?' for security-updates
* "updates" and "reboot-required" will be aligned

# License

Apache2
