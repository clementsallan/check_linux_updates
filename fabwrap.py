#!/usr/bin/python
# -*- coding: utf-8 -*-

'''
Misc functionality wrapping fabric's default impelementation.
'''


from fabric.auth import get_password, set_password
from fabric.exceptions import NetworkError
from fabric.network import HostConnectionCache
from fabric.network import normalize, normalize_to_string
from fabric.network import is_key_load_error, _tried_enough, prompt_for_password
from fabric import network
from fabric.state import env, output
from fabric import state
from logging import getLogger

# from logging import StreamHandler
from logging import NullHandler, DEBUG

import base64
from binascii import hexlify
import hashlib
import os
import paramiko
import paramiko as ssh
import socket
import sys
import time


local_logger = getLogger(__name__)
# handler = StreamHandler()
handler = NullHandler()
handler.setLevel(DEBUG)
local_logger.setLevel(DEBUG)
local_logger.addHandler(handler)

def get_fingerprint(line):
    key = base64.b64decode(line.strip().split()[1].encode('ascii'))
    return hashlib.md5(key).hexdigest()


class CustomHostConnectionCache(HostConnectionCache):
    '''
    fabric.network.HostConnectionCache that awares of OpenSSH's config file.
    This will interact with (paramiko's ssh) Agent and try to choose
    the best private key for each host.

    This is particularly useful when a user has 5 private/public key pairs
    or more. The case will confuse paramiko's key choice logic, causing
    mysterious authentication error during fabric operations due to
    too many authentication attempts.
    It happens with (current) demo.py in paramiko too:
    https://github.com/paramiko/paramiko/blob/1.15/demos/demo.py
    '''
    def __init__(self, config_file=None):
        super(CustomHostConnectionCache, self).__init__()
        config_file = config_file or os.path.expanduser("~/.ssh/config")
        self.ssh_config = paramiko.SSHConfig()
        if os.path.exists(user_config_file):
            with open(user_config_file) as f:
                self.ssh_config.parse(f)

    def connect(self, key, logger=None):
        logger = logger or local_logger
        user, host, port = normalize(key)
        logger.debug('user: {}, host: {}, port: {}'.format(user, host, port))
        key = normalize_to_string(key)
        identity_config = self.ssh_config.lookup(host)
        identity_files = identity_config.get('identityfile')
        self[key] = wrap_connect(user, host, port,
                                 cache=self,
                                 identity_files=identity_files)


def wrap_connect(user, host, port, cache,
                 seek_gateway=True,
                 identity_files=None,
                 logger=None):
    logger = logger or local_logger
    identity_files = identity_files or [os.path.expanduser("~/.ssh/id_rsa")]
    client = paramiko.SSHClient()
    known_hosts = env.get('system_known_hosts')
    if known_hosts:
        client.load_system_host_keys(known_hosts)
    if not env.disable_known_hosts:
        client.load_system_host_keys()
    if not env.reject_unknown_hosts:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connected = False
    password = get_password(user, host, port)
    tries = 0
    sock = None
    agent = paramiko.Agent()
    agent_keys = agent.get_keys()
    key_dict = {}
    for key in agent_keys:
        fp = hexlify(key.get_fingerprint())
        key_dict[fp] = key

    for identity_file in identity_files:
        pubkey_line = open('{}.pub'.format(identity_file)).readline().rstrip()
        fingerprint = get_fingerprint(pubkey_line)
        logger.debug('using identity "{}"(fp: {})'.format(identity_file, fingerprint))
        pkey = key_dict.get(fingerprint)
        if not pkey:
            readable = ':'.join(a+b for a,b in zip(fingerprint[::2], fingerprint[1::2]))
            logger.info('Agent does not know a key for {} "{}"'.format(host, readable))
            continue
        try:
            tries += 1
            if seek_gateway:
                sock = network.get_gateway(host, port, cache, replace=tries > 0)
            client.connect(
                hostname=host,
                port=int(port),
                username=user,
                password=None,
                pkey=pkey,
                key_filename=identity_file,
                timeout=env.timeout,
                allow_agent=not env.no_agent,
                look_for_keys=not env.no_keys,
                sock=sock
            )
            connected = True
            if env.keepalive:
                client.get_transport().set_keepalive(env.keepalive)

            return client
        # BadHostKeyException corresponds to key mismatch, i.e. what on the
        # command line results in the big banner error about man-in-the-middle
        # attacks.
        except ssh.BadHostKeyException, e:
            raise NetworkError("Host key for %s did not match pre-existing key! Server's key was changed recently, or possible man-in-the-middle attack." % host, e)
        # Prompt for new password to try on auth failure
        except (
            ssh.AuthenticationException,
            ssh.PasswordRequiredException,
            ssh.SSHException
        ), e:
            msg = str(e)
            # If we get SSHExceptionError and the exception message indicates
            # SSH protocol banner read failures, assume it's caused by the
            # server load and try again.
            if e.__class__ is ssh.SSHException \
                and msg == 'Error reading SSH protocol banner':
                if _tried_enough(tries):
                    raise NetworkError(msg, e)
                continue

            # For whatever reason, empty password + no ssh key or agent
            # results in an SSHException instead of an
            # AuthenticationException. Since it's difficult to do
            # otherwise, we must assume empty password + SSHException ==
            # auth exception.
            #
            # Conversely: if we get SSHException and there
            # *was* a password -- it is probably something non auth
            # related, and should be sent upwards. (This is not true if the
            # exception message does indicate key parse problems.)
            #
            # This also holds true for rejected/unknown host keys: we have to
            # guess based on other heuristics.
            if e.__class__ is ssh.SSHException \
                and (password or msg.startswith('Unknown server')) \
                and not is_key_load_error(e):
                raise NetworkError(msg, e)

            # Otherwise, assume an auth exception, and prompt for new/better
            # password.

            # Paramiko doesn't handle prompting for locked private
            # keys (i.e.  keys with a passphrase and not loaded into an agent)
            # so we have to detect this and tweak our prompt slightly.
            # (Otherwise, however, the logic flow is the same, because
            # ssh's connect() method overrides the password argument to be
            # either the login password OR the private key passphrase. Meh.)
            #
            # NOTE: This will come up if you normally use a
            # passphrase-protected private key with ssh-agent, and enter an
            # incorrect remote username, because ssh.connect:
            # * Tries the agent first, which will fail as you gave the wrong
            # username, so obviously any loaded keys aren't gonna work for a
            # nonexistent remote account;
            # * Then tries the on-disk key file, which is passphrased;
            # * Realizes there's no password to try unlocking that key with,
            # because you didn't enter a password, because you're using
            # ssh-agent;
            # * In this condition (trying a key file, password is None)
            # ssh raises PasswordRequiredException.
            text = None
            if e.__class__ is ssh.PasswordRequiredException \
                or is_key_load_error(e):
                # NOTE: we can't easily say WHICH key's passphrase is needed,
                # because ssh doesn't provide us with that info, and
                # env.key_filename may be a list of keys, so we can't know
                # which one raised the exception. Best not to try.
                prompt = "[%s] Passphrase for private key"
                text = prompt % env.host_string
            password = prompt_for_password(text)
            # Update env.password, env.passwords if empty
            set_password(user, host, port, password)
        # Ctrl-D / Ctrl-C for exit
        except (EOFError, TypeError):
            # Print a newline (in case user was sitting at prompt)
            print('')
            sys.exit(0)
        # Handle DNS error / name lookup failure
        except socket.gaierror, e:
            raise NetworkError('Name lookup failed for %s' % host, e)
        # Handle timeouts and retries, including generic errors
        # NOTE: In 2.6, socket.error subclasses IOError
        except socket.error, e:
            not_timeout = type(e) is not socket.timeout
            giving_up = _tried_enough(tries)
            # Baseline error msg for when debug is off
            msg = "Timed out trying to connect to %s" % host
            # Expanded for debug on
            err = msg + " (attempt %s of %s)" % (tries, env.connection_attempts)
            if giving_up:
                err += ", giving up"
            err += ")"
            # Debuggin'
            if output.debug:
                sys.stderr.write(err + '\n')
            # Having said our piece, try again
            if not giving_up:
                # Sleep if it wasn't a timeout, so we still get timeout-like
                # behavior
                if not_timeout:
                    time.sleep(env.timeout)
                continue
            # Override eror msg if we were retrying other errors
            if not_timeout:
                msg = "Low level socket error connecting to host %s on port %s: %s" % (
                    host, port, e[1]
                )
            # Here, all attempts failed. Tweak error msg to show # tries.
            # TODO: find good humanization module, jeez
            s = "s" if env.connection_attempts > 1 else ""
            msg += " (tried %s time%s)" % (env.connection_attempts, s)
            raise NetworkError(msg, e)
        # Ensure that if we terminated without connecting and we were given an
        # explicit socket, close it out.        # BadHostKeyException corresponds to key mismatch, i.e. what on the
        # command line results in the big banner error about man-in-the-middle
        # attacks.
        except ssh.BadHostKeyException, e:
            raise NetworkError("Host key for %s did not match pre-existing key! Server's key was changed recently, or possible man-in-the-middle attack." % host, e)
        # Prompt for new password to try on auth failure
        except (
            ssh.AuthenticationException,
            ssh.PasswordRequiredException,
            ssh.SSHException
        ), e:
            msg = str(e)
            # If we get SSHExceptionError and the exception message indicates
            # SSH protocol banner read failures, assume it's caused by the
            # server load and try again.
            if e.__class__ is ssh.SSHException \
                and msg == 'Error reading SSH protocol banner':
                if _tried_enough(tries):
                    raise NetworkError(msg, e)
                continue

            # For whatever reason, empty password + no ssh key or agent
            # results in an SSHException instead of an
            # AuthenticationException. Since it's difficult to do
            # otherwise, we must assume empty password + SSHException ==
            # auth exception.
            #
            # Conversely: if we get SSHException and there
            # *was* a password -- it is probably something non auth
            # related, and should be sent upwards. (This is not true if the
            # exception message does indicate key parse problems.)
            #
            # This also holds true for rejected/unknown host keys: we have to
            # guess based on other heuristics.
            if e.__class__ is ssh.SSHException \
                and (password or msg.startswith('Unknown server')) \
                and not is_key_load_error(e):
                raise NetworkError(msg, e)

            # Otherwise, assume an auth exception, and prompt for new/better
            # password.

            # Paramiko doesn't handle prompting for locked private
            # keys (i.e.  keys with a passphrase and not loaded into an agent)
            # so we have to detect this and tweak our prompt slightly.
            # (Otherwise, however, the logic flow is the same, because
            # ssh's connect() method overrides the password argument to be
            # either the login password OR the private key passphrase. Meh.)
            #
            # NOTE: This will come up if you normally use a
            # passphrase-protected private key with ssh-agent, and enter an
            # incorrect remote username, because ssh.connect:
            # * Tries the agent first, which will fail as you gave the wrong
            # username, so obviously any loaded keys aren't gonna work for a
            # nonexistent remote account;
            # * Then tries the on-disk key file, which is passphrased;
            # * Realizes there's no password to try unlocking that key with,
            # because you didn't enter a password, because you're using
            # ssh-agent;
            # * In this condition (trying a key file, password is None)
            # ssh raises PasswordRequiredException.
            text = None
            if e.__class__ is ssh.PasswordRequiredException \
                or is_key_load_error(e):
                # NOTE: we can't easily say WHICH key's passphrase is needed,
                # because ssh doesn't provide us with that info, and
                # env.key_filename may be a list of keys, so we can't know
                # which one raised the exception. Best not to try.
                prompt = "[%s] Passphrase for private key"
                text = prompt % env.host_string
            password = prompt_for_password(text)
            # Update env.password, env.passwords if empty
            set_password(user, host, port, password)
        # Ctrl-D / Ctrl-C for exit
        except (EOFError, TypeError):
            # Print a newline (in case user was sitting at prompt)
            print('')
            sys.exit(0)
        # Handle DNS error / name lookup failure
        except socket.gaierror, e:
            raise NetworkError('Name lookup failed for %s' % host, e)
        # Handle timeouts and retries, including generic errors
        # NOTE: In 2.6, socket.error subclasses IOError
        except socket.error, e:
            not_timeout = type(e) is not socket.timeout
            giving_up = _tried_enough(tries)
            # Baseline error msg for when debug is off
            msg = "Timed out trying to connect to %s" % host
            # Expanded for debug on
            err = msg + " (attempt %s of %s)" % (tries, env.connection_attempts)
            if giving_up:
                err += ", giving up"
            err += ")"
            # Debuggin'
            if output.debug:
                sys.stderr.write(err + '\n')
            # Having said our piece, try again
            if not giving_up:
                # Sleep if it wasn't a timeout, so we still get timeout-like
                # behavior
                if not_timeout:
                    time.sleep(env.timeout)
                continue
            # Override eror msg if we were retrying other errors
            if not_timeout:
                msg = "Low level socket error connecting to host %s on port %s: %s" % (
                    host, port, e[1]
                )
            # Here, all attempts failed. Tweak error msg to show # tries.
            # TODO: find good humanization module, jeez
            s = "s" if env.connection_attempts > 1 else ""
            msg += " (tried %s time%s)" % (env.connection_attempts, s)
            raise NetworkError(msg, e)
        # Ensure that if we terminated without connecting and we were given an
        # explicit socket, close it out.
        finally:
            if not connected and sock is not None:
                sock.close()                

    logger.info('Fall back to default implementation')
    return network.connect(user, host, port, cache)


def setup():
    logger = local_logger
    logger.debug('fabwrap.setup()')
    state.connections = CustomHostConnectionCache()

