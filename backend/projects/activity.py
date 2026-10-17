"""Audit records for the project activity feed.

Call these inside the same transaction as the change they describe, so a
change and its audit record are committed (or rolled back) together.
"""
from .models import Activity


def _user_ref(user):
    # Store a snapshot so the feed still reads correctly if the user is renamed.
    return {'id': str(user.id), 'name': user.name} if user else None


def record(task, actor, verb, data=None):
    return Activity.objects.create(
        project_id=task.project_id,
        actor=actor,
        verb=verb,
        task=task,
        task_title=task.title,
        data=data or {},
    )


def task_created(task, actor):
    return record(task, actor, 'task_created', {'status': task.status})


def status_changed(task, actor, old_status):
    return record(task, actor, 'status_changed', {'from': old_status, 'to': task.status})


def assignee_changed(task, actor, old_assignee):
    return record(task, actor, 'assignee_changed', {
        'from': _user_ref(old_assignee),
        'to': _user_ref(task.assignee),
    })


def comment_added(comment):
    return record(comment.task, comment.author, 'comment_added', {
        'commentId': str(comment.id),
        'excerpt': comment.body[:140],
    })
