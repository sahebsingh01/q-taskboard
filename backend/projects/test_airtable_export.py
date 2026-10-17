import pytest
import requests
from rest_framework.test import APIClient

from users.models import User
from projects import airtable_export, views
from projects.airtable_export import call_with_retry, run_export
from projects.airtable_mock import FakeAirtableTable, http_error
from projects.models import ExportJob, Membership, Project, Task


@pytest.fixture
def owner(db):
    return User.objects.create_user(email='owner@example.com', name='Owner', password='password123')


@pytest.fixture
def project(owner):
    project = Project.objects.create(name='Launch', owner=owner)
    Membership.objects.create(user=owner, project=project, role='admin')
    return project


def make_tasks(project, owner, n):
    return [
        Task.objects.create(project=project, title=f'Task {i}', created_by=owner, position=i, assignee=owner)
        for i in range(n)
    ]


def new_job(project, owner):
    return ExportJob.objects.create(project=project, triggered_by=owner)


def no_sleep(_):
    pass


@pytest.mark.django_db
class TestExportService:
    def test_exports_all_tasks_and_creates_missing_fields(self, project, owner):
        make_tasks(project, owner, 23)
        table = FakeAirtableTable()

        job = run_export(new_job(project, owner).id, table=table, sleep=no_sleep)

        assert job.status == 'succeeded'
        assert (job.total, job.created, job.skipped, job.failed) == (23, 23, 0, 0)
        assert len(table.records) == 23
        assert {'Task ID', 'Project', 'Assigned To'} <= set(table.fields)
        # 23 tasks -> batches of 10, 10, 3
        assert [c for c in table.calls if c[0] == 'batch_upsert'] == [
            ('batch_upsert', 10), ('batch_upsert', 10), ('batch_upsert', 3),
        ]
        record = next(iter(table.records.values()))
        assert record['Status'] == 'Todo'
        assert record['Assigned To'] == 'Owner'
        assert record['Project'] == 'Launch'

    def test_rerun_skips_tasks_already_in_airtable(self, project, owner):
        tasks = make_tasks(project, owner, 5)
        table = FakeAirtableTable()
        run_export(new_job(project, owner).id, table=table, sleep=no_sleep)

        tasks[0].title = 'Renamed'
        tasks[0].save()
        make_tasks(project, owner, 1)  # one new task
        job = run_export(new_job(project, owner).id, table=table, sleep=no_sleep)

        assert (job.total, job.created, job.skipped) == (6, 1, 5)
        assert len(table.records) == 6
        # Existing rows are left exactly as they were.
        assert 'Renamed' not in {r['Name'] for r in table.records.values()}

    def test_fills_empty_rows_from_the_top_before_appending(self, project, owner):
        make_tasks(project, owner, 4)
        table = FakeAirtableTable()
        table.view_order = []
        # Grid: empty, someone's own note, empty (only a computed field), then appended rows.
        first = table.add_row()
        kept = table.add_row(Notes='keep me')
        third = table.add_row(**{'Attachment Summary': {'state': 'empty'}})

        job = run_export(new_job(project, owner).id, table=table, sleep=no_sleep)

        assert (job.created, job.skipped, job.failed) == (4, 0, 0)
        rows = table.rows()
        assert len(rows) == 5  # 2 empty rows reused + 2 appended
        assert [r.get('Name') for r in rows] == ['Task 0', None, 'Task 1', 'Task 2', 'Task 3']
        assert table.records[kept] == {'Notes': 'keep me'}
        assert table.records[first]['Task ID'] and table.records[third]['Task ID']

    def test_empty_rows_follow_grid_order_not_record_id_order(self, project, owner):
        make_tasks(project, owner, 2)
        table = FakeAirtableTable()
        a, b = table.add_row(), table.add_row()
        table.view_order = [b, a]  # user dragged b above a

        run_export(new_job(project, owner).id, table=table, sleep=no_sleep)

        assert table.records[b]['Name'] == 'Task 0'
        assert table.records[a]['Name'] == 'Task 1'

    def test_task_already_present_is_ignored_even_if_edited_in_airtable(self, project, owner):
        task = make_tasks(project, owner, 1)[0]
        table = FakeAirtableTable()
        rid = table.add_row(**{'Task ID': str(task.id), 'Name': 'edited in Airtable'})

        job = run_export(new_job(project, owner).id, table=table, sleep=no_sleep)

        assert (job.created, job.skipped) == (0, 1)
        assert table.records == {rid: {'Task ID': str(task.id), 'Name': 'edited in Airtable'}}

    def test_failed_fill_is_isolated(self, project, owner):
        make_tasks(project, owner, 3)
        table = FakeAirtableTable()
        for _ in range(3):
            table.add_row()
        table.bad_names = {'Task 1': http_error(422, 'INVALID_VALUE_FOR_COLUMN', 'bad value')}

        job = run_export(new_job(project, owner).id, table=table, sleep=no_sleep)

        assert job.status == 'partial'
        assert (job.created, job.failed) == (2, 1)
        assert len(table.records) == 3

    def test_transient_failures_are_retried(self, project, owner):
        make_tasks(project, owner, 3)
        table = FakeAirtableTable()
        table.write_failures = [http_error(503), requests.ConnectionError('reset'), http_error(429)]
        sleeps = []

        job = run_export(new_job(project, owner).id, table=table, sleep=sleeps.append)

        assert job.status == 'succeeded'
        assert len(table.records) == 3
        assert sleeps == [1.0, 2.0, 30.0]

    def test_permanent_record_failure_is_isolated(self, project, owner):
        make_tasks(project, owner, 12)
        table = FakeAirtableTable()
        table.bad_names = {'Task 4': http_error(422, 'INVALID_VALUE_FOR_COLUMN', 'bad value')}
        sleeps = []

        job = run_export(new_job(project, owner).id, table=table, sleep=sleeps.append)

        assert job.status == 'partial'
        assert (job.created, job.failed) == (11, 1)
        assert job.errors[0]['title'] == 'Task 4'
        assert 'INVALID_VALUE_FOR_COLUMN' in job.errors[0]['error']
        assert sleeps == []  # 422 is never retried

    def test_auth_failure_stops_the_export(self, project, owner):
        make_tasks(project, owner, 25)
        table = FakeAirtableTable()
        table.write_failures = [http_error(401, 'AUTHENTICATION_REQUIRED', 'bad token')]

        job = run_export(new_job(project, owner).id, table=table, sleep=no_sleep)

        assert job.status == 'failed'
        assert 'AUTHENTICATION_REQUIRED' in job.error
        assert len([c for c in table.calls if c[0] == 'batch_upsert']) == 1

    def test_missing_configuration_fails_cleanly(self, project, owner, settings):
        settings.AIRTABLE_API_KEY = ''
        job = run_export(new_job(project, owner).id, sleep=no_sleep)
        assert job.status == 'failed'
        assert 'not configured' in job.error

    def test_retry_gives_up_after_max_attempts(self):
        calls = []

        def always_503():
            calls.append(1)
            raise http_error(503)

        with pytest.raises(requests.HTTPError):
            call_with_retry(always_503, sleep=no_sleep)
        assert len(calls) == airtable_export.MAX_ATTEMPTS


@pytest.mark.django_db
class TestExportEndpoint:
    @pytest.fixture
    def fake_table(self, monkeypatch):
        table = FakeAirtableTable()
        monkeypatch.setattr(
            views, 'run_export_in_background',
            lambda job_id: run_export(job_id, table=table, sleep=no_sleep),
        )
        return table

    def login(self, user):
        client = APIClient()
        token = client.post('/api/auth/login', {'email': user.email, 'password': 'password123'}, format='json').data['token']
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return client

    def test_member_can_export(self, project, owner, fake_table, django_capture_on_commit_callbacks):
        make_tasks(project, owner, 4)
        member = User.objects.create_user(email='m@example.com', name='M', password='password123')
        Membership.objects.create(user=member, project=project, role='member')
        client = self.login(member)

        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(f'/api/projects/{project.id}/export')
        assert response.status_code == 202
        assert len(fake_table.records) == 4

        latest = client.get(f'/api/projects/{project.id}/export').data['job']
        assert latest['status'] == 'succeeded'
        assert latest['created'] == 4
        assert latest['skipped'] == 0

    @pytest.mark.parametrize('role', ['viewer', None])
    def test_viewers_and_outsiders_cannot_export(self, project, fake_table, role):
        user = User.objects.create_user(email='v@example.com', name='V', password='password123')
        if role:
            Membership.objects.create(user=user, project=project, role=role)
        client = self.login(user)

        assert client.post(f'/api/projects/{project.id}/export').status_code == 403
        assert client.get(f'/api/projects/{project.id}/export').status_code == 403
        assert ExportJob.objects.count() == 0

    def test_second_trigger_while_running_returns_existing_job(self, project, owner, monkeypatch):
        started = []
        monkeypatch.setattr(views, 'run_export_in_background', started.append)
        client = self.login(owner)

        first = client.post(f'/api/projects/{project.id}/export')
        second = client.post(f'/api/projects/{project.id}/export')

        assert first.status_code == 202
        assert second.status_code == 200
        assert second.data['job']['id'] == first.data['job']['id']
        assert ExportJob.objects.count() == 1
