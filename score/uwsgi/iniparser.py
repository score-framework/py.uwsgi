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


from collections import OrderedDict

import re


NO_VALUE = type('NO_FALLBACK', (object,), {})()


class ParseError(Exception):
    pass


class UwsgiIni:
    """
    Accessor for a uwsgi ini file. The main feature of these files is that keys
    can occur more than once in sections. Furthermore, keys are not required to
    have values. Such keys will automatically receive the value `True`.

    The following is perfectly valid, for example::

        [overlord]
        daemonize = /tmp/overlord.log
        logdate
        master-fifo = /tmp/first.fifo
        master-fifo = /tmp/second.fifo

    Handling of sections remains the same though: every section must have a
    unique name.
    """

    def __init__(self):
        self.sections = OrderedDict()

    def load(self, fp):
        """
        Loads the configuration from given :term:`file object` *fp*.
        """
        return self.loads(fp.read())

    def loads(self, string):
        """
        Loads the configuration from given *string*.
        """
        self.sections = OrderedDict()
        section = None
        for i, line in enumerate(string.split('\n')):
            line = line.strip()
            if not line or line.startswith(';'):
                continue
            if line[0] == '[':
                if line[-1] != ']':
                    raise ParseError('Line %d starts with bracket, '
                                     'but doesn\'t end in one' % i)
                name = line[1:-1].strip()
                if not re.match(r'[a-zA-Z0-9_-]+$', name):
                    raise ParseError('Line %d contains invalid section name: %s'
                                     % (i, name))
                section = UwsgiSection(name)
                self.sections[name] = section
                continue
            if section is None:
                raise ParseError('Line %d is outside of any sections' % i)
            try:
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip()
            except ValueError:
                k, v = (line, True)
            section[k] = v

    def write(self, fp):
        """
        Writes this configuration to given :term:`file object` *fp*.
        """
        fp.write(self.dumps())

    def dumps(self):
        """
        Converts this configuration to string.
        """
        result = ''
        for name, section in self.sections.items():
            result += '[%s]\n' % name
            for k, v in section:
                result += '%s = %s\n' % (k, str(v))
            result += '\n'
        return result

    def __getitem__(self, key):
        if key not in self.sections:
            self.sections[key] = UwsgiSection(key)
        return self.sections[key]

    def __setitem__(self, key, value):
        self.sections[key] = section = UwsgiSection(key)
        for k, v in value:
            section[k] = v

    def __delitem__(self, key):
        self.sections.pop(key, None)

    def __iter__(self):
        return iter(self.sections)


class UwsgiSection:
    """
    A named section within a :class:`.UwsgiIni`. Behaves very much like an
    :class:`collections.OrderedDict`, but can contain keys multiple times.
    """

    def __init__(self, name):
        self.name = name
        self.pairs = []

    def __iter__(self):
        return iter(self.pairs)

    def __setitem__(self, key, value):
        self.pairs.append((key, value))

    def __getitem__(self, key):
        for k, v in reversed(self.pairs):
            if key == k:
                return v
        raise KeyError(k)

    def __delitem__(self, key):
        self.reset(key)

    def pop(self, key, fallback=NO_VALUE):
        for i, (k, v) in reversed(enumerate(self.pairs)):
            if k == key:
                del self.pairs[i]
                return v
        if fallback != NO_VALUE:
            return fallback
        raise KeyError(key)

    def reset(self, key, value=NO_VALUE):
        """
        Removes all values with given *key*.
        """
        for i, (k, v) in reversed(enumerate(self.pairs)):
            if key == k:
                del self.pairs[i]
        if value != NO_VALUE:
            self[k] = v

    def get_all(self, key):
        """
        Provides all values for given *key*.
        """
        return [v for k, v in self.pairs if k == key]
