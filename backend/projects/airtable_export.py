"""Export a project's tasks to Airtable.

``Task ID`` is treated as the table's unique key: a task whose ID is already
in the table is skipped, never written twice. New tasks first fill empty rows
(top of the grid first), then are appended. Every write is idempotent (updates
target a record id, creates are upserts on ``Task ID``), so a retried request
can never create a duplicate row.
"""
import logging
import time

import requests
from django.conf import settings
from django.db import connection
from django.utils import timezone

from .models import ExportJob, Task

logger = logging.getLogger(__name__)

KEY_FIELD = 'Task ID'
BATCH_SIZE = 10  # Airtable's per-request record limit
MAX_ATTEMPTS = 5
BASE_DELAY = 1.0
RATE_LIMIT_DELAY = 30.0  # Airtable asks clients to back off 30s after a 429
TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
# These mean the token, base or table is wrong: every record would fail the
# same way, so the whole export stops instead of trying records one by one.
FATAL_STATUSES = {401, 403, 404}

# Fields TaskBoard owns, created in the table if they are missing.
REQUIRED_FIELDS = {
    KEY_FIELD: 'singleLineText',
    'Project': 'singleLineText',
    'Assigned To': 'singleLineText',
}

# Field types Airtable computes itself; a row holding only these is empty.
COMPUTED_FIELD_TYPES = {
    'aiText', 'formula', 'rollup', 'count', 'multipleLookupValues', 'autoNumber',
    'createdTime', 'lastModifiedTime', 'createdBy', 'lastModifiedBy', 'button',
    'externalSyncSource',
}

STATUS_LABELS = {
    'todo': 'Todo',
    'in_progress': 'In progress',
    'review': 'In review',
    'done': 'Done',
}


class ExportConfigError(Exception):
    """The export cannot run at all (missing settings, bad token, missing table)."""


def _status_code(exc):
    response = getattr(exc, 'response', None)
    return response.status_code if response is not None else None


def is_transient(exc):
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    return isinstance(exc, requests.HTTPError) and _status_code(exc) in TRANSIENT_STATUSES


def error_message(exc):
    response = getattr(exc, 'response', None)
    if response is not None:
        try:
            error = response.json().get('error')
        except ValueError:
            error = None
        if isinstance(error, dict):
            return f"{error.get('type', 'ERROR')}: {error.get('message', '')}".strip(': ')[:500]
        if isinstance(error, str):
            return error[:500]
        return f'HTTP {response.status_code}'
    return str(exc)[:500] or type(exc).__name__


def _retry_delay(exc, attempt):
    response = getattr(exc, 'response', None)
    if response is not None:
        retry_after = response.headers.get('Retry-After')
        if retry_after and retry_after.isdigit():
            return float(retry_after)
        if response.status_code == 429:
            return RATE_LIMIT_DELAY
    return BASE_DELAY * 2 ** (attempt - 1)


def call_with_retry(fn, *, sleep=time.sleep, max_attempts=MAX_ATTEMPTS):
    """Run ``fn``, retrying only transient failures with backoff."""
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:
            if not is_transient(exc) or attempt == max_attempts:
                raise
            delay = _retry_delay(exc, attempt)
            logger.warning('airtable call failed (%s), retry %d in %.0fs', error_message(exc), attempt, delay)
            sleep(delay)


def task_fields(task):
    return {
        KEY_FIELD: str(task.id),
        'Name': task.title,
        'Notes': task.description or '',
        'Status': STATUS_LABELS[task.status],
        'Project': task.project.name,
        'Assigned To': task.assignee.name if task.assignee else '',
    }


def get_table():
    if not (settings.AIRTABLE_API_KEY and settings.AIRTABLE_BASE_ID and settings.AIRTABLE_TABLE_NAME):
        raise ExportConfigError('Airtable is not configured: set AIRTABLE_API_KEY, AIRTABLE_BASE_ID and AIRTABLE_TABLE_NAME')
    from pyairtable import Api
    # Retries are handled by call_with_retry so the policy is explicit and testable.
    api = Api(settings.AIRTABLE_API_KEY, timeout=(10, 30), retry_strategy=None)
    return api.table(settings.AIRTABLE_BASE_ID, settings.AIRTABLE_TABLE_NAME)


def ensure_fields(table, sleep=time.sleep):
    """Create any missing TaskBoard fields and return the table schema."""
    try:
        schema = call_with_retry(table.schema, sleep=sleep)
        existing = {f.name for f in schema.fields}
        missing = [name for name in REQUIRED_FIELDS if name not in existing]
        for name in missing:
            call_with_retry(lambda: table.create_field(name, REQUIRED_FIELDS[name]), sleep=sleep)
        return call_with_retry(lambda: table.schema(force=True), sleep=sleep) if missing else schema
    except KeyError:
        raise ExportConfigError(f'Airtable table "{table.name}" was not found in the base')
    except requests.HTTPError as exc:
        raise ExportConfigError(
            f'Could not prepare the Airtable table ({error_message(exc)}). The token needs the '
            f'data.records:read, data.records:write, schema.bases:read and schema.bases:write scopes.'
        )


def _has_value(value):
    return value not in (None, '', [], {})


def scan_table(table, schema, sleep=time.sleep):
    """Return (Task IDs already in the table, empty record ids in grid order)."""
    records = call_with_retry(table.all, sleep=sleep)
    existing_ids = {r['fields'][KEY_FIELD] for r in records if _has_value(r['fields'].get(KEY_FIELD))}

    editable = {f.name for f in schema.fields if f.type not in COMPUTED_FIELD_TYPES}
    empty = {r['id'] for r in records if not any(_has_value(r['fields'].get(n)) for n in editable)}

    # The API returns records by id, not in the order people see them, so use
    # the first view's row order. Rows that view hides go last, oldest first.
    ordered = []
    if empty and schema.views:
        view_id = schema.views[0].id
        view_records = call_with_retry(lambda: table.all(view=view_id, fields=[KEY_FIELD]), sleep=sleep)
        ordered = [r['id'] for r in view_records if r['id'] in empty]
    seen = set(ordered)
    ordered += [
        r['id'] for r in sorted(records, key=lambda r: r['createdTime'])
        if r['id'] in empty and r['id'] not in seen
    ]
    return existing_ids, ordered


def _fill(table, items, sleep):
    """Write tasks into existing empty rows; ``items`` is [(record_id, fields)]."""
    call_with_retry(
        lambda: table.batch_update([{'id': rid, 'fields': f} for rid, f in items], typecast=True),
        sleep=sleep,
    )
    return len(items), 0


def _append(table, items, sleep):
    """Create rows for tasks; ``items`` is [(None, fields)]."""
    result = call_with_retry(
        lambda: table.batch_upsert(
            [{'fields': f} for _, f in items], key_fields=[KEY_FIELD], typecast=True,
        ),
        sleep=sleep,
    )
    # A row matched instead of created means the task appeared in the table
    # after we scanned it; count it as already present.
    return len(result.get('createdRecords', [])), len(result.get('updatedRecords', []))


def _write(job, table, tasks, items, send, sleep):
    for start in range(0, len(items), BATCH_SIZE):
        batch_tasks = tasks[start:start + BATCH_SIZE]
        batch = items[start:start + BATCH_SIZE]
        try:
            created, skipped = send(table, batch, sleep)
            job.created += created
            job.skipped += skipped
        except Exception as exc:
            if _status_code(exc) in FATAL_STATUSES:
                raise ExportConfigError(f'Airtable rejected the export: {error_message(exc)}')
            # One bad record fails its whole batch, so send them one at a time
            # to isolate it and still export the rest.
            for task, item in zip(batch_tasks, batch):
                try:
                    created, skipped = send(table, [item], sleep)
                    job.created += created
                    job.skipped += skipped
                except Exception as record_exc:
                    if _status_code(record_exc) in FATAL_STATUSES:
                        raise ExportConfigError(f'Airtable rejected the export: {error_message(record_exc)}')
                    job.failed += 1
                    job.errors.append({'taskId': str(task.id), 'title': task.title, 'error': error_message(record_exc)})
        job.save(update_fields=['created', 'skipped', 'failed', 'errors'])


def export_tasks(job, table, *, sleep=time.sleep):
    """Push the tasks of ``job.project`` that Airtable doesn't have yet, recording progress on ``job``."""
    tasks = list(
        Task.objects
        .filter(project=job.project)
        .select_related('assignee', 'project')
        .order_by('status', 'position')
    )
    job.total = len(tasks)
    job.save(update_fields=['total'])

    schema = ensure_fields(table, sleep=sleep)
    existing_ids, empty_rows = scan_table(table, schema, sleep=sleep)

    new_tasks = [t for t in tasks if str(t.id) not in existing_ids]
    job.skipped = len(tasks) - len(new_tasks)
    job.save(update_fields=['skipped'])

    fill_tasks, append_tasks = new_tasks[:len(empty_rows)], new_tasks[len(empty_rows):]
    _write(job, table, fill_tasks, [(rid, task_fields(t)) for rid, t in zip(empty_rows, fill_tasks)], _fill, sleep)
    _write(job, table, append_tasks, [(None, task_fields(t)) for t in append_tasks], _append, sleep)


def run_export(job_id, *, table=None, sleep=time.sleep):
    """Run an export job to completion. Never raises; the outcome is stored on the job."""
    job = ExportJob.objects.select_related('project').get(id=job_id)
    try:
        export_tasks(job, table if table is not None else get_table(), sleep=sleep)
        job.status = 'partial' if job.failed else 'succeeded'
    except ExportConfigError as exc:
        job.status, job.error = 'failed', str(exc)
    except Exception as exc:
        logger.exception('airtable export %s failed', job_id)
        job.status, job.error = 'failed', f'Export failed: {error_message(exc)}'
    job.finished_at = timezone.now()
    job.save()
    return job


def run_export_in_background(job_id):
    import threading

    def target():
        try:
            run_export(job_id)
        finally:
            connection.close()  # the thread's own connection

    threading.Thread(target=target, name=f'airtable-export-{job_id}', daemon=True).start()
