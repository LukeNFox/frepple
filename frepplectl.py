#!/usr/bin/env python3

#
# Copyright (C) 2007-2013 by frePPLe bv
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero
# General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

r"""
This command is the wrapper for all administrative actions on frePPLe.
"""

import os
import sys
import site

if __name__ == "__main__":
    try:
        # Initialize Python virtual environments
        venv = os.environ.get("VIRTUAL_ENV", None)
        if venv:
            os.environ["PATH"] = os.pathsep.join(
                [os.path.join(venv, "Scripts")]
                + os.environ.get("PATH", "").split(os.pathsep)
            )
            prev_length = len(sys.path)
            path = os.path.realpath(os.path.join(venv, "Lib", "site-packages"))
            site.addsitedir(path)
            sys.path[:] = sys.path[prev_length:] + sys.path[0:prev_length]
            sys.real_prefix = sys.prefix
            sys.prefix = venv

        # Initialize django
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "freppledb.settings")
        import django

        django.setup()

        # Synchronize the scenario table with the settings
        from freppledb.common.models import Scenario

        Scenario.syncWithSettings()

        # Run the command
        from django.core.management import execute_from_command_line

        execute_from_command_line(sys.argv)

    except KeyboardInterrupt:
        print("\nInterrupted with Ctrl-C")
        sys.exit(1)
