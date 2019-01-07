#
# Copyright (C) 2007-2013 by frePPLe bvba
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

from datetime import datetime, timedelta
import logging
import os
import shlex
import time
import operator
from multiprocessing import Process
from threading import Thread

from django.conf import settings
from django.core import management
from django.core.management import get_commands
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections

from freppledb import VERSION, runCommand
from freppledb.common.models import Parameter
from freppledb.common.middleware import _thread_locals
from freppledb.execute.models import Task


logger = logging.getLogger(__name__)


class WorkerAlive(Thread):
  def __init__(self, database=DEFAULT_DB_ALIAS):
    self.database = database
    Thread.__init__(self)
    self.daemon = True

  def run(self):
    while True:
      try:
        p = Parameter.objects.all().using(self.database).get_or_create(pk='Worker alive')[0]
        p.value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        p.save(update_fields=['value'])
      except:
        pass
      time.sleep(5)


def checkActive(database=DEFAULT_DB_ALIAS):
    try:
      p = Parameter.objects.all().using(database).get(pk='Worker alive')
      return datetime.now() - datetime.strptime(p.value, "%Y-%m-%d %H:%M:%S") <= timedelta(0, 5)
    except:
      return False


class Command(BaseCommand):

  help = '''Processes the job queue of a database.
    The command is intended only to be used internally by frePPLe, not by an API or user.
    '''

  requires_system_checks = False


  def get_version(self):
    return VERSION


  def add_arguments(self, parser):
    parser.add_argument(
      '--database', default=DEFAULT_DB_ALIAS,
      help='Nominates a specific database to load data from and export results into'
      )
    parser.add_argument(
      '--continuous', action="store_true",
      default=False, help='Keep the worker alive after the queue is empty'
      )


  def handle(self, *args, **options):

    # Pick up the options
    database = options['database']
    if database not in settings.DATABASES:
      raise CommandError("No database settings known for '%s'" % database )
    continuous = options['continuous']

    # Use the test database if we are running the test suite
    if 'FREPPLE_TEST' in os.environ:
      connections[database].close()
      settings.DATABASES[database]['NAME'] = settings.DATABASES[database]['TEST']['NAME']

    # Check if a worker already exists
    if checkActive(database):
      if 'FREPPLE_TEST' not in os.environ:
        logger.info("Worker for database '%s' already active" % settings.DATABASES[database]['NAME'])
      return

    # Spawn a worker-alive thread
    WorkerAlive(database).start()

    # Process the queue
    if 'FREPPLE_TEST' not in os.environ:
      logger.info("Worker %s for database '%s' starting to process jobs" % (
        os.getpid(), settings.DATABASES[database]['NAME']
        ))
    idle_loop_done = False
    setattr(_thread_locals, 'database', database)
    while True:
      try:
        task = Task.objects.all().using(database).filter(status='Waiting').order_by('id')[0]
        idle_loop_done = False
      except:
        # No more tasks found
        if continuous:
          time.sleep(5)
          continue
        else:
          # Special case: we need to permit a single idle loop before shutting down
          # the worker. If we shut down immediately, a newly launched task could think
          # that a worker is already running - while it just shut down.
          if idle_loop_done:
            break
          else:
            idle_loop_done = True
            time.sleep(5)
            continue
      try:
        if 'FREPPLE_TEST' not in os.environ:
          logger.info("Worker %s for database '%s' starting task %d at %s" % (
            os.getpid(), settings.DATABASES[database]['NAME'], task.id, datetime.now()
            ))
        background = False
        task.started = datetime.now()
        # Verify the command exists
        exists = False
        for commandname in get_commands():
          if commandname == task.name:
            exists = True
            break

        if not exists:
          # No such task exists
          logger.error('Task %s not recognized' % task.name)
          task.status = 'Failed'
          task.processid = None
          task.save(using=database)
        else:
          # Close all database connections to assure the parent and child
          # process don't share them.
          connections.close_all()
          # Spawn a new command process
          args = []
          kwargs = {
            'database': database,
            'task': task.id,
            'verbosity': 0
            }
          if task.arguments:
            for i in shlex.split(task.arguments):
              if '=' in i:
                key, val = i.split('=')
                kwargs[key.strip("--").replace('-', '_')] = val
              else:
                args.append(i)
          child = Process(
            target=runCommand,
            args=(task.name, *args),
            kwargs=kwargs,
            name="frepplectl %s" % task.name
            )
          child.start()
          background = 'background' in kwargs

          # Normally, the child will update the processid.
          # Just to make sure, we do it also here.
          task.processid = child.pid
          task.save(update_fields=['processid'], using=database)

          # Wait for the child to finish
          child.join()

          # Read the task again from the database and update it
          task = Task.objects.all().using(database).get(pk=task.id)
          task.processid = None
          if task.status not in ('Done', 'Failed') or not task.finished or not task.started:
            now = datetime.now()
            if not task.started:
              task.started = now
            if not background:
              if not task.finished:
                task.finished = now
              if task.status not in ('Done', 'Failed'):
                task.status = 'Done'
            task.save(using=database)
          if 'FREPPLE_TEST' not in os.environ:
            logger.info("Worker %s for database '%s' finished task %d at %s: success" % (
              os.getpid(), settings.DATABASES[database]['NAME'], task.id, datetime.now()
              ))
      except Exception as e:
        # Read the task again from the database and update.
        task = Task.objects.all().using(database).get(pk=task.id)
        task.status = 'Failed'
        now = datetime.now()
        if not task.started:
          task.started = now
        task.finished = now
        task.message = str(e)
        task.save(using=database)
        if 'FREPPLE_TEST' not in os.environ:
          logger.info("Worker %s for database '%s' finished task %d at %s: failed" % (
            os.getpid(), settings.DATABASES[database]['NAME'], task.id, datetime.now()
            ))
    # Remove the parameter again
    try:
      Parameter.objects.all().using(database).get(pk='Worker alive').delete()
    except:
      pass
    setattr(_thread_locals, 'database', None)

    # Remove log files exceeding the configured disk space allocation
    totallogs = 0
    filelist = []
    for x in os.listdir(settings.FREPPLE_LOGDIR):
      if x.endswith('.log'):
        size = 0
        creation = 0
        filename = os.path.join(settings.FREPPLE_LOGDIR, x)
        # needs try/catch because log files may still be open or being used and Windows does not like it
        try:
          size = os.path.getsize(filename)
          creation = os.path.getctime(filename)
          filelist.append( {'name': filename, 'size': size, 'creation': creation} )
        except:
          pass
        totallogs += size
    todelete = totallogs - settings.MAXTOTALLOGFILESIZE * 1024 * 1024
    filelist.sort(key=operator.itemgetter('creation'))
    for fordeletion in filelist:
      if todelete > 0:
        try:
          os.remove(fordeletion['name'])
          todelete -= fordeletion['size']
        except:
          pass

    # Exit
    if 'FREPPLE_TEST' not in os.environ:
      logger.info("Worker %s for database '%s' finished all jobs in the queue and exits" % (
        os.getpid(), settings.DATABASES[database]['NAME']
        ))
