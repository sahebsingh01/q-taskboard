"""In-memory stand-in for a pyairtable ``Table``, for unit tests only.

It implements the subset of the Table API the export uses (``schema``,
``create_field``, ``all``, ``batch_update``, ``batch_upsert``) with Airtable's
semantics, and can be told to fail specific calls or records. Rows are kept in
grid order: insertion order, unless ``view_order`` is set.
"""
import uuid
from types import SimpleNamespace

import requests

DEFAULT_FIELDS = {
    'Name': 'singleLineText',
    'Notes': 'multilineText',
    'Assignee': 'singleCollaborator',
    'Status': 'singleSelect',
    'Attachment Summary': 'aiText',
}


def http_error(status, error_type='ERROR', message='', headers=None):
    response = requests.Response()
    response.status_code = status
    response._content = (
        f'{{"error": {{"type": "{error_type}", "message": "{message}"}}}}'.encode()
    )
    response.headers.update(headers or {})
    return requests.HTTPError(f'{status} Client Error', response=response)


class FakeAirtableTable:
    name = 'Tasks'

    def __init__(self, fields=None):
        self.fields = dict(fields or DEFAULT_FIELDS)  # name -> type
        self.records = {}  # record id -> fields, in creation order
        self.view_order = None  # optional grid order (list of record ids)
        self.calls = []
        # Exceptions raised, in order, by upcoming write calls.
        self.write_failures = []
        # Raised whenever a write contains a record whose `Name` is a key here.
        self.bad_names = {}

    # Test helpers

    def add_row(self, **fields):
        rid = f'rec{uuid.uuid4().hex[:14]}'
        self.records[rid] = dict(fields)
        if self.view_order is not None:
            self.view_order.append(rid)
        return rid

    def rows(self):
        """Fields of every row, in grid order."""
        return [self.records[rid] for rid in (self.view_order or list(self.records))]

    def _check_write(self, records):
        if len(records) > 10:
            raise http_error(422, 'INVALID_RECORDS', 'too many records')
        if self.write_failures:
            raise self.write_failures.pop(0)
        for record in records:
            name = record['fields'].get('Name')
            if name in self.bad_names:
                raise self.bad_names[name]

    # pyairtable Table API

    def schema(self, force=False):
        self.calls.append('schema')
        return SimpleNamespace(
            fields=[SimpleNamespace(name=n, type=t) for n, t in self.fields.items()],
            views=[SimpleNamespace(id='viwGrid', name='Grid view')],
        )

    def create_field(self, name, type, description=None, options=None):
        self.calls.append(('create_field', name))
        self.fields[name] = type

    def all(self, view=None, fields=None, **options):
        self.calls.append(('all', view))
        creation_order = list(self.records)
        # Like Airtable: grid order with a view, record-id order without one.
        order = (self.view_order or creation_order) if view else sorted(self.records)
        return [
            {
                'id': rid,
                'createdTime': f'2026-01-01T00:00:{creation_order.index(rid):02d}.000Z',
                'fields': {
                    k: v for k, v in self.records[rid].items()
                    if (fields is None or k in fields) and v not in (None, '', [])
                },
            }
            for rid in order
        ]

    def batch_update(self, records, replace=False, typecast=False):
        self.calls.append(('batch_update', len(records)))
        self._check_write(records)
        for record in records:
            self.records[record['id']].update(record['fields'])
        return [{'id': r['id'], 'fields': self.records[r['id']]} for r in records]

    def batch_upsert(self, records, key_fields, replace=False, typecast=False):
        self.calls.append(('batch_upsert', len(records)))
        self._check_write(records)
        created, updated = [], []
        for record in records:
            fields = record['fields']
            key = tuple(fields[k] for k in key_fields)
            match = next(
                (rid for rid, f in self.records.items() if tuple(f.get(k) for k in key_fields) == key),
                None,
            )
            if match:
                self.records[match].update(fields)
                updated.append(match)
            else:
                created.append(self.add_row(**fields))
        return {
            'createdRecords': created,
            'updatedRecords': updated,
            'records': [{'id': rid, 'fields': self.records[rid]} for rid in created + updated],
        }
