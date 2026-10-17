import pytest
from rest_framework.test import APIClient

from users.models import User
from projects.models import Activity, Comment, Membership, Project, Task


def login(user):
    client = APIClient()
    token = client.post('/api/auth/login', {'email': user.email, 'password': 'password123'}, format='json').data['token']
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


def make_user(email, name='User'):
    return User.objects.create_user(email=email, name=name, password='password123')


@pytest.fixture
def setup(db):
    admin = make_user('admin@example.com', 'Admin')
    member = make_user('member@example.com', 'Member')
    viewer = make_user('viewer@example.com', 'Viewer')
    outsider = make_user('outsider@example.com', 'Outsider')
    project = Project.objects.create(name='P', owner=admin)
    for user, role in [(admin, 'admin'), (member, 'member'), (viewer, 'viewer')]:
        Membership.objects.create(user=user, project=project, role=role)
    task = Task.objects.create(project=project, title='Write docs', created_by=admin)
    return {'admin': admin, 'member': member, 'viewer': viewer, 'outsider': outsider, 'project': project, 'task': task}


@pytest.mark.django_db
class TestComments:
    @pytest.mark.parametrize('role', ['admin', 'member'])
    def test_members_can_post(self, setup, role):
        task = setup['task']
        response = login(setup[role]).post(f'/api/tasks/{task.id}/comments', {'body': '  Looks good  '}, format='json')
        assert response.status_code == 201
        assert response.data['comment']['body'] == 'Looks good'
        assert response.data['comment']['author']['name'] == setup[role].name

    def test_viewer_can_read_but_not_post(self, setup):
        task = setup['task']
        Comment.objects.create(task=task, author=setup['admin'], body='hi')
        client = login(setup['viewer'])
        assert client.post(f'/api/tasks/{task.id}/comments', {'body': 'nope'}, format='json').status_code == 403
        response = client.get(f'/api/tasks/{task.id}/comments')
        assert response.status_code == 200
        assert [c['body'] for c in response.data['comments']] == ['hi']
        assert Comment.objects.count() == 1

    def test_outsider_cannot_read_or_post(self, setup):
        task = setup['task']
        client = login(setup['outsider'])
        assert client.get(f'/api/tasks/{task.id}/comments').status_code == 403
        assert client.post(f'/api/tasks/{task.id}/comments', {'body': 'x'}, format='json').status_code == 403

    def test_listed_chronologically_with_author_and_time(self, setup):
        task = setup['task']
        client = login(setup['member'])
        for body in ['first', 'second', 'third']:
            client.post(f'/api/tasks/{task.id}/comments', {'body': body}, format='json')
        comments = client.get(f'/api/tasks/{task.id}/comments').data['comments']
        assert [c['body'] for c in comments] == ['first', 'second', 'third']
        assert all(c['author']['name'] == 'Member' and c['createdAt'] for c in comments)

    @pytest.mark.parametrize('body', ['', '   ', None, 'x' * 5001])
    def test_rejects_invalid_body(self, setup, body):
        task = setup['task']
        response = login(setup['member']).post(f'/api/tasks/{task.id}/comments', {'body': body}, format='json')
        assert response.status_code == 400

    def test_cannot_be_edited_or_deleted_via_api(self, setup):
        task = setup['task']
        comment = Comment.objects.create(task=task, author=setup['admin'], body='original')
        client = login(setup['admin'])
        for method in (client.patch, client.put, client.delete):
            assert method(f'/api/tasks/{task.id}/comments', {'body': 'changed'}, format='json').status_code == 405
        comment.refresh_from_db()
        assert comment.body == 'original'

    def test_cannot_be_edited_or_deleted_via_orm(self, setup):
        comment = Comment.objects.create(task=setup['task'], author=setup['admin'], body='original')
        comment.body = 'changed'
        with pytest.raises(ValueError):
            comment.save()
        with pytest.raises(ValueError):
            comment.delete()

    def test_no_role_can_be_granted_edit_or_delete(self):
        from django.contrib.auth.models import Permission
        codenames = set(Permission.objects.filter(content_type__model='comment').values_list('codename', flat=True))
        assert codenames == {'add_comment', 'view_comment'}


@pytest.mark.django_db
class TestActivity:
    def feed(self, setup, user='viewer'):
        response = login(setup[user]).get(f"/api/projects/{setup['project'].id}/activity")
        assert response.status_code == 200
        return response.data['activity']

    def test_records_each_change_newest_first(self, setup):
        project, member = setup['project'], setup['member']
        client = login(member)
        task_id = client.post(f'/api/projects/{project.id}/tasks', {'title': 'Ship it'}, format='json').data['task']['id']
        client.patch(f'/api/tasks/{task_id}', {'status': 'in_progress'}, format='json')
        client.patch(f'/api/tasks/{task_id}', {'assigneeId': str(member.id)}, format='json')
        client.post(f'/api/tasks/{task_id}/comments', {'body': 'on it'}, format='json')

        feed = self.feed(setup)
        assert [e['verb'] for e in feed] == ['comment_added', 'assignee_changed', 'status_changed', 'task_created']
        assert all(e['actor']['name'] == 'Member' and e['task']['title'] == 'Ship it' for e in feed)
        assert feed[2]['data'] == {'from': 'todo', 'to': 'in_progress'}
        assert feed[1]['data'] == {'from': None, 'to': {'id': str(member.id), 'name': 'Member'}}
        assert feed[0]['data']['excerpt'] == 'on it'

    def test_unchanged_fields_are_not_recorded(self, setup):
        task = setup['task']
        login(setup['admin']).patch(
            f'/api/tasks/{task.id}', {'title': 'Renamed', 'status': task.status, 'assigneeId': None}, format='json',
        )
        assert self.feed(setup) == []

    def test_scoped_to_one_project(self, setup):
        other = Project.objects.create(name='Other', owner=setup['admin'])
        Membership.objects.create(user=setup['admin'], project=other, role='admin')
        login(setup['admin']).post(f'/api/projects/{other.id}/tasks', {'title': 'Elsewhere'}, format='json')
        assert self.feed(setup) == []

    @pytest.mark.parametrize('role', ['admin', 'member', 'viewer'])
    def test_every_role_can_read(self, setup, role):
        assert self.feed(setup, role) == []

    def test_outsider_cannot_read(self, setup):
        response = login(setup['outsider']).get(f"/api/projects/{setup['project'].id}/activity")
        assert response.status_code == 403

    def test_rejected_change_leaves_no_record(self, setup):
        task = setup['task']
        response = login(setup['viewer']).patch(f'/api/tasks/{task.id}', {'status': 'done'}, format='json')
        assert response.status_code == 403
        assert Activity.objects.count() == 0

    def test_assignee_must_be_project_member(self, setup):
        task = setup['task']
        response = login(setup['admin']).patch(
            f'/api/tasks/{task.id}', {'assigneeId': str(setup['outsider'].id)}, format='json',
        )
        assert response.status_code == 400
        assert Activity.objects.count() == 0

    def test_feed_survives_task_deletion(self, setup):
        client = login(setup['admin'])
        task_id = client.post(f"/api/projects/{setup['project'].id}/tasks", {'title': 'Temp'}, format='json').data['task']['id']
        client.delete(f'/api/tasks/{task_id}')
        feed = self.feed(setup)
        assert feed[0]['verb'] == 'task_created'
        assert feed[0]['task'] == {'id': None, 'title': 'Temp'}
