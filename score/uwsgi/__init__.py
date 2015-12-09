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


import os
from score.init import ConfiguredModule, ConfigurationError
from .process import (
    Overlord, Zergling, NoSuchZergling, AlreadyPaused,
    AlreadyRunning, AlreadyReloading, NotRunning)


defaults = {
    'rootdir': None,
}


def init(confdict):
    """
    Initializes this module acoording to :ref:`our module initialization
    guidelines <module_initialization>` with the following configuration keys:

    :confkey:`rootdir` :faint:`[default=None]`
        The folder containing all uwsgi instances' files.

    """
    conf = defaults.copy()
    conf.update(confdict)
    if not conf['rootdir']:
        raise ConfigurationError(__package__,
                                 'No root folder provided')
    os.makedirs(conf['rootdir'], exist_ok=True)
    return ConfiguredUwsgiModule(conf['rootdir'])


class ConfiguredUwsgiModule(ConfiguredModule):
    """
    This module's :class:`configuration object
    <score.init.ConfiguredModule>`.
    """

    def __init__(self, rootdir):
        super().__init__(__package__)
        self.rootdir = rootdir
        conf = self

        class ConfiguredOverlord(Overlord):

            @classmethod
            def instances(cls):
                for folder in os.listdir(conf.rootdir):
                    if os.path.isdir(os.path.join(conf.rootdir, folder)):
                        overlord = cls(folder)
                        if overlord.is_running():
                            yield overlord

            def __init__(self, *args, **kwargs):
                self.conf = conf
                super().__init__(*args, **kwargs)

        class ConfiguredZergling(Zergling):

            def __init__(self, *args, **kwargs):
                self.conf = conf
                super().__init__(*args, **kwargs)

        self.Overlord = ConfiguredOverlord
        self.Zergling = ConfiguredZergling


__all__ = [
    'init', 'ConfiguredUwsgiModule', 'Overlord', 'Zergling', 'NoSuchZergling',
    'AlreadyPaused', 'AlreadyRunning', 'AlreadyReloading', 'NotRunning']
