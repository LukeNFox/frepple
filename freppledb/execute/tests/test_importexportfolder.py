#
# Copyright (C) 2007-2016 by frePPLe bvba
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

# ./frepplectl.py test freppledb.execute.tests.test_importexportfolder.Execute_with_commands -v 2

import os
from shutil import rmtree
import tempfile

from django.conf import settings
from django.core import management
from django.db import DEFAULT_DB_ALIAS
from django.test import TransactionTestCase

from freppledb.input.models import ManufacturingOrder, PurchaseOrder, DistributionOrder


class Execute_with_commands(TransactionTestCase):

  fixtures = ["demo"]
  serialized_rollback = True

  def setUp(self):
    # Make sure the test database is used
    os.environ['FREPPLE_TEST'] = "YES"
    # Export and import from a temporary folder to avoid interfering with
    # existing data files
    self.datafolder = tempfile.mkdtemp()
    settings.DATABASES[DEFAULT_DB_ALIAS]['FILEUPLOADFOLDER'] = self.datafolder


  def tearDown(self):
    rmtree(self.datafolder)


  def test_exportimportfromfolder(self):

    # Run frePPLe on the test database. No longer needed because records are already in the fixture, in Enterprise conficts with webservice
    #management.call_command('runplan', plantype=1, constraint=15, env='supply')

    self.assertTrue(ManufacturingOrder.objects.count() > 30)
    self.assertTrue(PurchaseOrder.objects.count() > 20)
    self.assertTrue(DistributionOrder.objects.count() > 0)

    # The exporttofolder filters by status so the count must also filter
    countMO = ManufacturingOrder.objects.filter(status='proposed').count()
    countPO = PurchaseOrder.objects.filter(status='proposed').count()
    countDO = DistributionOrder.objects.filter(status='proposed').count()

    management.call_command('exporttofolder')

    ManufacturingOrder.objects.all().delete()
    DistributionOrder.objects.all().delete()
    PurchaseOrder.objects.all().delete()

    self.assertEqual(DistributionOrder.objects.count(), 0)
    self.assertEqual(PurchaseOrder.objects.count(), 0)
    self.assertEqual(ManufacturingOrder.objects.count(), 0)

    # Move export files to the import folder
    for file in os.listdir(os.path.join(self.datafolder, 'export')):
      if file.endswith(".csv.gz"):
        os.rename(
          os.path.join(self.datafolder, 'export', file),
          os.path.join(self.datafolder, file)
          )

    management.call_command('importfromfolder')

    self.assertEqual(DistributionOrder.objects.count(), countDO)
    self.assertEqual(PurchaseOrder.objects.count(), countPO)
    self.assertEqual(ManufacturingOrder.objects.count(), countMO)
