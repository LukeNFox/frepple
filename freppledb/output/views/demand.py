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

import json

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connections
from django.http import HttpResponseForbidden, HttpResponse, HttpResponseBadRequest
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import force_text

from freppledb.boot import getAttributeFields
from freppledb.common.report import GridPivot, GridFieldText
from freppledb.input.models import Demand, Item, PurchaseOrder, DistributionOrder, ManufacturingOrder


class OverviewReport(GridPivot):
  '''
  A report showing the independent demand for each item.
  '''
  template = 'output/demand.html'
  title = _('Demand report')
  post_title = _('plan')
  basequeryset = Item.objects.all()
  model = Item
  permissions = (("view_demand_report", "Can view demand report"),)
  rows = (
    GridFieldText('item', title=_('item'), key=True, editable=False, field_name='name', formatter='detail', extra='"role":"input/item"'),
    )
  crosses = (
    ('demand', {'title': _('demand')}),
    ('supply', {'title': _('supply')}),
    ('backlog', {'title': _('backlog')}),
    )
  help_url = 'user-guide/user-interface/plan-analysis/demand-report.html'

  @classmethod
  def initialize(reportclass, request):
    if reportclass._attributes_added != 2:
      reportclass._attributes_added = 2
      reportclass.attr_sql = ''
      # Adding custom item attributes
      for f in getAttributeFields(Item, initially_hidden=True):
        reportclass.attr_sql += 'item.%s, ' % f.name.split('__')[-1]

  @classmethod
  def extra_context(reportclass, request, *args, **kwargs):
    if args and args[0]:
      request.session['lasttab'] = 'plan'
      return {
        'title': force_text(Item._meta.verbose_name) + " " + args[0],
        'post_title': _('plan')
        }
    else:
      return {}

  @classmethod
  def query(reportclass, request, basequery, sortsql='1 asc'):
    basesql, baseparams = basequery.query.get_compiler(basequery.db).as_sql(with_col_aliases=False)

    # Assure the item hierarchy is up to date
    Item.rebuildHierarchy(database=basequery.db)

    # Execute a query to get the backlog at the start of the horizon
    startbacklogdict = {}
    query = '''
      select items.name, coalesce(req.qty, 0) - coalesce(pln.qty, 0)
      from (%s) items
      left outer join (
        select parent.name, sum(quantity) qty
        from demand
        inner join item on demand.item_id = item.name
        inner join item parent on item.lft between parent.lft and parent.rght
        where status in ('open', 'quote')
        and due < %%s
        group by parent.name
        ) req
      on req.name = items.name
      left outer join (
        select parent.name, sum(operationplan.quantity) qty
        from operationplan
        inner join demand on operationplan.demand_id = demand.name
          and operationplan.owner_id is null
          and operationplan.enddate < %%s
        inner join item on demand.item_id = item.name
        inner join item parent on item.lft between parent.lft and parent.rght
        group by parent.name
        ) pln
      on pln.name = items.name
      ''' % basesql
    with connections[request.database].chunked_cursor() as cursor_chunked:
      cursor_chunked.execute(query, baseparams + (request.report_startdate, request.report_startdate))
      for row in cursor_chunked:
        if row[0]:
          startbacklogdict[row[0]] = float(row[1])

    # Execute the query
    query = '''
      select 
      parent.name, %s
      d.bucket,
      d.startdate,
      d.enddate,
      sum(coalesce((select sum(quantity) from demand
       where demand.item_id = child.name and status in ('open','quote') and due >= greatest(%%s,d.startdate) and due < d.enddate),0)) orders,
      sum(coalesce((select sum(-operationplanmaterial.quantity) from operationplanmaterial
      inner join operationplan on operationplan.id = operationplanmaterial.operationplan_id and operationplan.type = 'DLVR'
      where operationplanmaterial.item_id = child.name 
      and operationplanmaterial.flowdate >= greatest(%%s,d.startdate) 
      and operationplanmaterial.flowdate < d.enddate),0)) planned    
      from (%s) parent
      inner join item child on child.lft between parent.lft and parent.rght
      cross join (
                   select name as bucket, startdate, enddate
                   from common_bucketdetail
                   where bucket_id = %%s and enddate > %%s and startdate < %%s
                   ) d
      group by 
      parent.name, %s
      d.bucket,
      d.startdate,
      d.enddate
      order by %s, d.startdate
    ''' % (reportclass.attr_sql, basesql, reportclass.attr_sql, sortsql)

    # Build the python result
    with connections[request.database].chunked_cursor() as cursor_chunked:
      cursor_chunked.execute(query, baseparams + (
        request.report_startdate, #orders
        request.report_startdate, #planned
        request.report_bucket, request.report_startdate, request.report_enddate #buckets
        ))
      previtem = None
      for row in cursor_chunked:
        numfields = len(row)
        if row[0] != previtem:
          backlog = startbacklogdict.get(row[0], 0)
          previtem = row[0]
        backlog += float(row[numfields-2]) - float(row[numfields-1])
        res = {
          'item': row[0],
          'bucket': row[numfields-5],
          'startdate': row[numfields-4].date(),
          'enddate': row[numfields-3].date(),
          'demand': round(row[numfields-2], 1),
          'supply': round(row[numfields-1], 1),
          'backlog': round(backlog, 1),
          }
        idx = 1
        for f in getAttributeFields(Item):
          res[f.field_name] = row[idx]
          idx += 1
        yield res


@staff_member_required
def OperationPlans(request):
  # Check permissions
  if request.method != "GET" or not request.is_ajax():
    return HttpResponseBadRequest('Only ajax get requests allowed')
  if not request.user.has_perm("view_demand_report"):
    return HttpResponseForbidden('<h1>%s</h1>' % _('Permission denied'))

  # Collect list of selected sales orders
  so_list = request.GET.getlist('demand')

  # Collect operationplans associated with the sales order(s)
  id_list = []
  for dm in Demand.objects.all().using(request.database).filter(pk__in=so_list).only('plan'):
    for op in dm.plan['pegging']:
      id_list.append(op['opplan'])

  # Collect details on the operationplans
  result = []
  for o in PurchaseOrder.objects.all().using(request.database).filter(id__in=id_list, status='proposed'):
    result.append({
      'id': o.id,
      'type': "PO",
      'item': o.item.name,
      'location': o.location.name,
      'origin': o.supplier.name,
      'startdate': str(o.startdate.date()),
      'enddate': str(o.enddate.date()),
      'quantity': float(o.quantity),
      'value': float(o.quantity * o.item.cost),
      'criticality': float(o.criticality)
    })
  for o in DistributionOrder.objects.all().using(request.database).filter(id__in=id_list, status='proposed'):
    result.append({
      'id': o.id,
      'type': "DO",
      'item': o.item.name,
      'location': o.location.name,
      'origin': o.origin.name,
      'startdate': str(o.startdate),
      'enddate': str(o.enddate),
      'quantity': float(o.quantity),
      'value': float(o.quantity * o.item.cost),
      'criticality': float(o.criticality)
    })
  for o in ManufacturingOrder.objects.all().using(request.database).filter(id__in=id_list, status='proposed'):
    result.append({
      'id': o.id,
      'type': "MO",
      'item': '',
      'location': o.operation.location.name,
      'origin': o.operation.name,
      'startdate': str(o.startdate.date()),
      'enddate': str(o.enddate.date()),
      'quantity': float(o.quantity),
      'value': '',
      'criticality': float(o.criticality)
    })

  return HttpResponse(
    content=json.dumps(result),
    content_type='application/json; charset=%s' % settings.DEFAULT_CHARSET
    )
