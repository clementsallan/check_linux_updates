# What is this?

Check updates on Linux boxes. Includes CentOS and Ubuntu/Debian support.

# Preparation

* Python/Fabric is needed for your client machine.
* Debian package "update-notifier-common" is needed on Debian machines.
    * Probably it is already installed on Ubuntu machines from the beginning.
* Prepare hosts.py that contains "HOSTS" as a list for a list of target hosts

e.g. (hosts.py)

    HOSTS = ['mowa-net.jp', 'test.mowa-net.jp']

# License

Apache2
