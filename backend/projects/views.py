from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import timedelta
from django.db import connection, transaction
from django.utils import timezone
from users.serializers import UserSerializer
from . import activity
from .airtable_export import run_export_in_background
from .models import Project, Membership, Task, ExportJob, Comment, Activity
from .permissions import has_permission, get_user_project_permissions
from .serializers import ProjectDetailSerializer, TaskSerializer


def _get_membership(user, project_id):
    try:
        return Membership.objects.get(user=user, project_id=project_id)
    except Membership.DoesNotExist:
        return None


def _forbidden(message='forbidden'):
    return Response({'error': message}, status=status.HTTP_403_FORBIDDEN)


def _bad_request(message):
    return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)


def _is_project_member(user_id, project_id):
    return Membership.objects.filter(user_id=user_id, project_id=project_id).exists()


class ProjectListCreateView(APIView):
    def get(self, request):
        memberships = (
            Membership.objects
            .filter(user=request.user)
            .select_related('project__owner')
            .prefetch_related('project__tasks')
            .order_by('-project__created_at')
        )
        projects = []
        for m in memberships:
            p = m.project
            projects.append({
                'id': str(p.id),
                'name': p.name,
                'description': p.description,
                'role': m.role,
                'owner': UserSerializer(p.owner).data,
                'taskCount': p.tasks.count(),
                'createdAt': p.created_at.isoformat(),
            })
        return Response({'projects': projects})

    def post(self, request):
        name = (request.data.get('name') or '').strip()
        description = request.data.get('description') or None
        if not name or len(name) > 120:
            return Response({'error': 'invalid input'}, status=status.HTTP_400_BAD_REQUEST)
        project = Project.objects.create(name=name, description=description, owner=request.user)
        Membership.objects.create(user=request.user, project=project, role='admin')
        return Response(
            {'project': {'id': str(project.id), 'name': project.name}},
            status=status.HTTP_201_CREATED,
        )


class ProjectDetailView(APIView):
    def get(self, request, project_id):
        membership = _get_membership(request.user, project_id)
        if not has_permission(membership, 'view_project'):
            return _forbidden()
        try:
            project = (
                Project.objects
                .prefetch_related('memberships__user', 'tasks__assignee', 'tasks__created_by')
                .select_related('owner')
                .get(id=project_id)
            )
        except Project.DoesNotExist:
            return Response({'error': 'not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'project': ProjectDetailSerializer(project).data})

    def patch(self, request, project_id):
        membership = _get_membership(request.user, project_id)
        if not has_permission(membership, 'change_project'):
            return _forbidden('you do not have permission to update this project')
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return Response({'error': 'not found'}, status=status.HTTP_404_NOT_FOUND)
        if 'name' in request.data:
            project.name = request.data['name'].strip()
        if 'description' in request.data:
            project.description = request.data['description'] or None
        project.save()
        return Response({'project': {'id': str(project.id), 'name': project.name}})

    def delete(self, request, project_id):
        membership = _get_membership(request.user, project_id)
        if not has_permission(membership, 'delete_project'):
            return _forbidden('you do not have permission to delete this project')
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return Response({'error': 'not found'}, status=status.HTTP_404_NOT_FOUND)
        project.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskListCreateView(APIView):
    def get(self, request, project_id):
        membership = _get_membership(request.user, project_id)
        if not has_permission(membership, 'view_task'):
            return _forbidden()

        q = request.query_params.get('q')
        if q:
            with connection.cursor() as cursor:
                sql = (
                    f"SELECT id, project_id, title, description, status, assignee_id, created_by_id, position, created_at, updated_at "
                    f"FROM tasks "
                    f"WHERE project_id = '{project_id}' "
                    f"AND (title ILIKE '%{q}%' OR description ILIKE '%{q}%') "
                    f"ORDER BY position ASC"
                )
                cursor.execute(sql)
                columns = [col[0] for col in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return Response({'tasks': rows})

        tasks = (
            Task.objects
            .filter(project_id=project_id)
            .select_related('assignee')
            .order_by('status', 'position')
        )
        return Response({'tasks': TaskSerializer(tasks, many=True).data})

    def post(self, request, project_id):
        membership = _get_membership(request.user, project_id)
        if not has_permission(membership, 'add_task'):
            return _forbidden('you do not have permission to create tasks')

        title = (request.data.get('title') or '').strip()
        if not title:
            return Response({'error': 'title is required'}, status=status.HTTP_400_BAD_REQUEST)

        task_status = request.data.get('status', 'todo')
        if task_status not in ('todo', 'in_progress', 'review', 'done'):
            return Response({'error': 'invalid status'}, status=status.HTTP_400_BAD_REQUEST)

        assignee_id = request.data.get('assigneeId') or None
        if assignee_id and not _is_project_member(assignee_id, project_id):
            return _bad_request('assignee must be a project member')

        with transaction.atomic():
            last = Task.objects.filter(project_id=project_id, status=task_status).order_by('-position').first()
            position = (last.position + 1) if last else 0

            task = Task.objects.create(
                project_id=project_id,
                title=title,
                description=request.data.get('description') or None,
                status=task_status,
                assignee_id=assignee_id,
                created_by=request.user,
                position=position,
            )
            activity.task_created(task, request.user)
        task_data = TaskSerializer(Task.objects.select_related('assignee').get(id=task.id)).data
        return Response({'task': task_data}, status=status.HTTP_201_CREATED)


class TaskDetailView(APIView):
    def patch(self, request, task_id):
        try:
            task = Task.objects.select_related('assignee').get(id=task_id)
        except Task.DoesNotExist:
            return Response({'error': 'not found'}, status=status.HTTP_404_NOT_FOUND)
        membership = _get_membership(request.user, task.project_id)
        if not has_permission(membership, 'change_task'):
            return _forbidden('you do not have permission to edit tasks')
        old_status, old_assignee = task.status, task.assignee
        if 'title' in request.data:
            task.title = request.data['title'].strip()
        if 'description' in request.data:
            task.description = request.data['description'] or None
        if 'status' in request.data:
            new_status = request.data['status']
            if new_status not in ('todo', 'in_progress', 'review', 'done'):
                return Response({'error': 'invalid status'}, status=status.HTTP_400_BAD_REQUEST)
            task.status = new_status
        if 'assigneeId' in request.data:
            assignee_id = request.data['assigneeId'] or None
            if assignee_id and not _is_project_member(assignee_id, task.project_id):
                return _bad_request('assignee must be a project member')
            task.assignee_id = assignee_id

        with transaction.atomic():
            task.save()
            if task.status != old_status:
                activity.status_changed(task, request.user, old_status)
            if str(task.assignee_id or '') != str(old_assignee.id if old_assignee else ''):
                task.refresh_from_db(fields=['assignee'])
                activity.assignee_changed(task, request.user, old_assignee)

        task_data = TaskSerializer(Task.objects.select_related('assignee').get(id=task_id)).data
        return Response({'task': task_data})

    def delete(self, request, task_id):
        try:
            task = Task.objects.select_related('project').get(id=task_id)
        except Task.DoesNotExist:
            return Response({'error': 'not found'}, status=status.HTTP_404_NOT_FOUND)

        membership = _get_membership(request.user, task.project_id)
        if not has_permission(membership, 'delete_task'):
            return _forbidden('you do not have permission to delete tasks')

        task.delete()
        return Response({'ok': True})


class MemberAddView(APIView):
    def post(self, request, project_id):
        membership = _get_membership(request.user, project_id)
        if not has_permission(membership, 'add_membership'):
            return _forbidden('you do not have permission to add members')

        email = (request.data.get('email') or '').strip()
        role = request.data.get('role', 'member')
        if role not in ('admin', 'member', 'viewer'):
            return Response({'error': 'invalid role'}, status=status.HTTP_400_BAD_REQUEST)

        from users.models import User as UserModel
        try:
            user = UserModel.objects.get(email=email)
        except UserModel.DoesNotExist:
            return Response({'error': 'user not found'}, status=status.HTTP_404_NOT_FOUND)

        membership_obj = Membership.objects.filter(user=user, project_id=project_id).first()
        created = membership_obj is None
        if created:
            membership_obj = Membership.objects.create(user=user, project_id=project_id, role=role)
        else:
            if not has_permission(membership, 'change_membership'):
                return _forbidden('you do not have permission to change member roles')
            membership_obj.role = role
            membership_obj.save()

        return Response({'ok': True, 'role': membership_obj.role}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


# A running job older than this was lost (e.g. the server restarted mid-export).
EXPORT_STALE_AFTER = timedelta(minutes=15)


def _export_job_data(job):
    return {
        'id': str(job.id),
        'status': job.status,
        'total': job.total,
        'created': job.created,
        'skipped': job.skipped,
        'failed': job.failed,
        'errors': job.errors[:50],
        'error': job.error or None,
        'startedAt': job.started_at.isoformat(),
        'finishedAt': job.finished_at.isoformat() if job.finished_at else None,
    }


class ExportView(APIView):
    def get(self, request, project_id):
        membership = _get_membership(request.user, project_id)
        if not has_permission(membership, 'export_task'):
            return _forbidden('you do not have permission to export tasks')
        job = ExportJob.objects.filter(project_id=project_id).order_by('-started_at').first()
        return Response({'job': _export_job_data(job) if job else None})

    def post(self, request, project_id):
        membership = _get_membership(request.user, project_id)
        if not has_permission(membership, 'export_task'):
            return _forbidden('you do not have permission to export tasks')

        with transaction.atomic():
            # Lock the project row so two simultaneous clicks can't start two exports.
            Project.objects.select_for_update().get(id=project_id)
            running = ExportJob.objects.filter(project_id=project_id, status='running').first()
            if running and running.started_at > timezone.now() - EXPORT_STALE_AFTER:
                return Response({'job': _export_job_data(running)}, status=status.HTTP_200_OK)
            if running:
                running.status = 'failed'
                running.error = 'Export was interrupted before it finished'
                running.finished_at = timezone.now()
                running.save()
            job = ExportJob.objects.create(project_id=project_id, triggered_by=request.user)
            # Start only once the job row is committed, so the worker can see it.
            transaction.on_commit(lambda: run_export_in_background(job.id))

        return Response({'job': _export_job_data(job)}, status=status.HTTP_202_ACCEPTED)


class MyPermissionsView(APIView):
    def get(self, request):
        return Response({'projects': get_user_project_permissions(request.user)})


COMMENT_MAX_LENGTH = 5000


def _comment_data(comment):
    return {
        'id': str(comment.id),
        'taskId': str(comment.task_id),
        'author': UserSerializer(comment.author).data,
        'body': comment.body,
        'createdAt': comment.created_at.isoformat(),
    }


class TaskCommentsView(APIView):
    """Comments are append-only: this view deliberately has no PATCH or DELETE."""

    def _task_and_membership(self, request, task_id):
        task = Task.objects.filter(id=task_id).first()
        return task, (_get_membership(request.user, task.project_id) if task else None)

    def get(self, request, task_id):
        task, membership = self._task_and_membership(request, task_id)
        if not has_permission(membership, 'view_comment'):
            return _forbidden()
        comments = task.comments.select_related('author').order_by('created_at', 'id')
        return Response({'comments': [_comment_data(c) for c in comments]})

    def post(self, request, task_id):
        task, membership = self._task_and_membership(request, task_id)
        if not has_permission(membership, 'add_comment'):
            return _forbidden('you do not have permission to comment')
        body = request.data.get('body')
        body = body.strip() if isinstance(body, str) else ''
        if not body:
            return _bad_request('comment cannot be empty')
        if len(body) > COMMENT_MAX_LENGTH:
            return _bad_request(f'comment must be at most {COMMENT_MAX_LENGTH} characters')

        with transaction.atomic():
            comment = Comment.objects.create(task=task, author=request.user, body=body)
            activity.comment_added(comment)
        return Response({'comment': _comment_data(comment)}, status=status.HTTP_201_CREATED)


ACTIVITY_DEFAULT_LIMIT = 50
ACTIVITY_MAX_LIMIT = 200


def _activity_data(entry):
    return {
        'id': str(entry.id),
        'verb': entry.verb,
        'actor': {'id': str(entry.actor_id), 'name': entry.actor.name} if entry.actor else None,
        'task': {'id': str(entry.task_id) if entry.task_id else None, 'title': entry.task_title},
        'data': entry.data,
        'createdAt': entry.created_at.isoformat(),
    }


class ProjectActivityView(APIView):
    def get(self, request, project_id):
        membership = _get_membership(request.user, project_id)
        if not has_permission(membership, 'view_activity'):
            return _forbidden()
        try:
            limit = min(max(int(request.query_params.get('limit', ACTIVITY_DEFAULT_LIMIT)), 1), ACTIVITY_MAX_LIMIT)
        except ValueError:
            return _bad_request('limit must be a number')
        entries = (
            Activity.objects
            .filter(project_id=project_id)
            .select_related('actor')
            .order_by('-created_at', '-id')[:limit]
        )
        return Response({'activity': [_activity_data(e) for e in entries]})
