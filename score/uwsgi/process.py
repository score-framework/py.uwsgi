# Copyright © 2015 STRG.AT GmbH, Vienna, Austria
#
# This file is part of the The SCORE Framework.
#
# The SCORE Framework and all its parts are free software: you can redistribute
# them and/or modify them under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation which is in the
# file named COPYING.LESSER.txt.
#
# The SCORE Framework and all its parts are distributed without any WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. For more details see the GNU Lesser General Public
# License.
#
# If you have not received a copy of the GNU Lesser General Public License see
# http://www.gnu.org/licenses/.
#
# The License-Agreement realised between you as Licensee and STRG.AT GmbH as
# Licenser including the issue of its valid conclusion and its pre- and
# post-contractual effects is governed by the laws of Austria. Any disputes
# concerning this License-Agreement including the issue of its valid conclusion
# and its pre- and post-contractual effects are exclusively decided by the
# competent court, in whose district STRG.AT GmbH has its registered seat, at
# the discretion of STRG.AT GmbH also the competent court, in whose district the
# Licensee has his registered seat, an establishment or assets.


from .iniparser import UwsgiIni

import json
import logging
import os
import re
import socket
from subprocess import Popen, PIPE, DEVNULL
import sys
import textwrap

log = logging.getLogger(__name__)


class NoSuchZergling(Exception):
    """
    Thrown when the requested zergling does not exist.
    """


class AlreadyPaused(Exception):
    """
    Thrown when a paused instance is intructed to pause.
    """


class AlreadyRunning(Exception):
    """
    Thrown when a running instance is intructed to start/resume.
    """


class AlreadyReloading(Exception):
    """
    Thrown when a reloading instance is intructed to reloading.
    """


class NotRunning(Exception):
    """
    Indicates that the instance was not running.
    """


class UwsgiProcess:
    """
    A uwsgi process managed by this module.
    """

    def __init__(self):
        self._pid = None

    def start(self, *, quiet=False, checkrunning=True):
        """
        Starts this instance.

        Will print the output of the uwsgi process to stdout and stderr, unless
        *quiet* was `True`.

        If *checkrunning* is left at its default value, the function will first
        check if the instance is already running and raise
        :class:`.AlreadyRunning` if it was.
        """
        if checkrunning and self.is_running():
            raise AlreadyRunning(str(self))
        self._pid = None
        os.makedirs(self.folder, exist_ok=True)
        log.info('Starting %s' % str(self))
        stdout, stderr = sys.stdout, sys.stderr
        if quiet:
            stdout = DEVNULL
            stderr = PIPE
        process = Popen(self.cmdline, stdout=stdout, stderr=stderr,
                        cwd=os.path.join(self.folder, '..'))
        _, err = process.communicate()
        if process.returncode:
            msg = 'Error starting process %s' % self
            if err:
                msg += ':\n' + textwrap.indent(str(err, 'UTF-8'), '  ')
            raise Exception(msg)

    def stop(self):
        """
        Stops this instance.

        Will raise :class:`.NotRunning`, if the instance was already stopped.
        """
        if not self.is_running():
            raise NotRunning(str(self))
        log.info('Stopping %s' % str(self))
        open(self.fifo, 'w').write('q')
        self._pid = None

    def is_running(self):
        """
        Whether this instance is running, i.e. the process exists and is
        responding to its requests on its statistics socket. See
        :meth:`.read_stats`.
        """
        try:
            self.read_stats()
            return True
        except NotRunning:
            return False

    @property
    def pid(self):
        """
        The process id of this process, or `None` if it is not :meth:`.running`.
        """
        try:
            return self.read_stats()['pid']
        except NotRunning:
            return None

    def read_stats(self):
        """
        Reads and parses all data from this process' `statistics socket`_.

        .. _statistics socket:
            http://uwsgi-docs.readthedocs.org/en/latest/StatsServer.html
        """
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(self.stats_socket)
            result = b''
            read = sock.recv(4096)
            while read:
                result += read
                read = sock.recv(4096)
            return json.loads(str(result, 'UTF-8'))
        except (FileNotFoundError,
                ConnectionRefusedError,
                ConnectionResetError):
            raise NotRunning(str(self))


class Overlord(UwsgiProcess):
    """
    The overlord process handling client connections.
    """

    def __init__(self, name):
        super().__init__()
        self.name = name
        self.folder = os.path.join(self.conf.rootdir, self.name)
        self.fifo = os.path.join(self.folder, 'overlord.fifo')
        self.logfile = os.path.join(self.folder, 'overlord.log')
        self.stats_socket = os.path.join(self.folder, 'overlord.stats.sock')
        self.inifile = os.path.join(self.folder, 'uwsgi.ini')
        self.cmdline = ["uwsgi", "--ini", "%s/uwsgi.ini:overlord" % self.name]

    def regenini(self):
        """
        Re-generates and writes this overlord's ini file.
        """
        ini = UwsgiIni()
        section = ini['overlord']
        section['master'] = True
        section['daemonize'] = self.logfile
        section['stats-server'] = self.stats_socket
        section['plugin'] = 'zergpool'
        section['logdate'] = True
        section['zerg-pool'] = '%s:%s' % (
            os.path.join(self.folder, 'zerg.socket'),
            os.path.join(self.folder, 'socket'))
        section['master-fifo'] = self.fifo
        os.makedirs(self.folder, exist_ok=True)
        ini.write(open(self.inifile, 'w'))

    def zerglings(self):
        """
        All :class:`Zerglings <.Zergling>` associated with this overlord.
        """
        zerglings = []
        ini = UwsgiIni()
        if os.path.exists(self.inifile):
            ini.load(open(self.inifile))
        for section_name in ini:
            match = re.match(r'^zergling-(.*)$', section_name)
            if not match:
                continue
            name = match.group(1)
            section = ini[section_name]
            zergling = self.conf.Zergling._from_section(self, name, section)
            zerglings.append(zergling)
        return zerglings

    def zergling(self, name):
        try:
            return next(z for z in self.zerglings() if z.name == name)
        except StopIteration:
            raise NoSuchZergling(name)

    def __str__(self):
        return self.name


class Zergling(UwsgiProcess):

    @classmethod
    def _from_section(cls, overlord, name, section):
        return cls(overlord, name, section['ini-paste'])

    def __init__(self, overlord, name, appini):
        super().__init__()
        self.overlord = overlord
        self.name = name
        self.appini = appini
        self.folder = self.overlord.folder
        self.fifo = os.path.join(self.folder, 'zergling-%s.fifo' % name)
        self.logfile = os.path.join(self.folder, 'zergling-%s.log' % name)
        self.stats_socket = os.path.join(self.folder,
                                         'zergling-%s.stats.sock' % name)
        self.startup_file = os.path.join(self.folder,
                                         'zergling-%s.startup' % name)
        self.inifile = self.overlord.inifile
        self.cmdline = [
            "uwsgi", "--ini",
            "%s/uwsgi.ini:zergling-%s" % (self.overlord.name, self.name)]

    def regenini(self, startpaused=False, virtualenv=None):
        """
        Re-generates and updates this zerglings section in the overlord's ini
        file.  It is possible to create the configuration in a way that pauses
        the process immediately upon starting by passign a truthy value for
        *startpaused*.
        """
        ini = self._open_ini()
        if 'zergling-%s' % self.name in ini:
            del ini['zergling-%s' % self.name]
        section = ini['zergling-%s' % self.name]
        if virtualenv:
            section['virtualenv'] = virtualenv
        section['zerg'] = os.path.join(self.folder, 'zerg.socket')
        section['daemonize'] = self.logfile
        section['logdate'] = True
        section['stats-server'] = self.stats_socket
        section['master-fifo'] = self.fifo
        section['master-fifo'] = self.fifo + '.restart'
        if startpaused:
            section['plugin'] = "startpaused"
        section['plugin'] = "python%s" % ''.join(map(str, sys.version_info[:2]))
        section['ini-paste'] = self.appini
        section['hook-asap'] = 'write:%s true' % self.startup_file
        section['hook-accepting1-once'] = 'unlink:%s' % self.startup_file
        section['hook-as-user-atexit'] = 'unlink:%s.restart' % self.fifo
        section['hook-as-user-atexit'] = 'unlink:%s' % self.startup_file
        os.makedirs(self.folder, exist_ok=True)
        ini.write(open(self.inifile, 'w'))

    def reload(self, quiet=True):
        """
        Starts another instance of this process, which will stop the old
        instance once it is up and running. This means that there will be twice
        the number of processes for a short time and it will not be clear which
        of these instances will respond to an incoming request for a very brief
        time frame.
        """
        if self.is_reloading():
            raise AlreadyReloading(str(self))
        log.info('Reloading %s' % str(self))
        open(self.fifo, 'w').write('1')
        try:
            startpaused = self.is_paused()
        except NotRunning:
            startpaused = False
        ini = self._open_ini()
        section = ini['zergling-%s' % self.name]
        plugins = []
        found = False
        for plugin in section.get_all('plugin'):
            if plugin == "startpaused":
                found = True
                if startpaused:
                    break
            else:
                plugins.append(plugin)
        if found and not startpaused:
            section.reset("plugin")
            for plugin in plugins:
                section["plugin"] = plugin
        elif not found and startpaused:
            section["plugin"] = "startpaused"
        hooks = ("writefifo:%s.restart q" % self.fifo,)
        for hook in hooks:
            if hook not in section.get_all('hook-accepting1-once'):
                section['hook-accepting1-once'] = hook
        ini.write(open(self.inifile, 'w'))
        self.start(quiet=quiet, checkrunning=False)

    def pause(self):
        """
        Pauses this instance. Raises :class:`.AlreadyPaused` if already paused.
        """
        if self.is_paused():
            raise AlreadyPaused(str(self))
        log.info('Pausing %s' % str(self))
        open(self.fifo, 'w').write('p')

    def resume(self):
        """
        Resumes this instance. Raises :class:`.AlreadyRunning` if already
        running.
        """
        if not self.is_paused():
            raise AlreadyRunning(str(self))
        log.info('Resuming %s' % str(self))
        open(self.fifo, 'w').write('p')

    def start(self, *args, **kwargs):
        """
        Starts this instance. All arguments are passed to :meth:`.start`. But
        raises :class:`.AlreadyRunning` if already running.
        """
        if self.is_starting():
            raise AlreadyRunning(str(self))
        super().start(*args, **kwargs)

    def delete(self):
        """
        Removes this zergling configuration from the ini file.
        """
        if not os.path.exists(self.inifile):
            return
        ini = self._open_ini()
        if 'zergling-%s' % self.name not in ini:
            return
        del ini['zergling-%s' % self.name]
        ini.write(open(self.inifile, 'w'))
        files = (self.stats_socket, self.startup_file,
                 self.fifo, self.fifo + '.restart')
        for file in files:
            try:
                os.remove(file)
            except FileNotFoundError:
                pass

    def is_reloading(self):
        """
        Checks whether this uwsgi process is currently :meth:`reloading
        <.reload>`.
        """
        return os.path.exists(self.fifo + '.restart')

    def is_starting(self):
        """
        Whether this process is currently starting up. This value will only be
        `True` during the short time frame between the call to :meth:`.start`
        and the point at which it is :attr:`.running`.
        """
        return os.path.exists(self.startup_file)

    def is_paused(self):
        """
        Whether the instance is currently paused.
        """
        return self.read_stats()['workers'][0]['status'] == 'pause'

    def _open_ini(self):
        """
        Returns the overlords ini file as :class:`UwsgiIni` object.
        """
        ini = UwsgiIni()
        if os.path.exists(self.inifile):
            ini.load(open(self.inifile))
        return ini

    def __str__(self):
        return '%s/zergling-%s' % (self.overlord.name, self.name)
