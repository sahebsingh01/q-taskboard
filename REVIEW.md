# Code Review

This documents contains a list of bugs found during the code review. The bugs are mentioned along with their Severity (Security / Performance / Architecture / Data Integrity / Testing) in descending order.

## Issue 1:

The current RBAC (Role Based Access Control) is not defined as it should be causing us to rely on the code level checks in the backend. 

There can be role - permission mapping in the database and the permissions should be checked in order to make that the correct user is able to perform the allowed action. These permission should be available in the frontend side as well so that Frontend can show/hide UI to prevent restricted actions to be performed. 

**Category:** Security

**Severity:** Very High

### Before: role checks hard-coded in each view

Each view decided for itself which roles may act (`membership.role != 'admin'`, `_can_edit_tasks(role)`), and some views had no check at all. The frontend had no way of knowing what the user was allowed to do. In the examples below, `dev@example.com` is a **viewer** on Q3 Launch.

```console
# Creating a task is blocked for viewers…
$ curl -s -X POST $OLD/api/projects/$PROJECT/tasks -H "Authorization: Bearer $VIEWER" \
    -H "Content-Type: application/json" -d '{"title":"viewer task"}' -w "\nHTTP %{http_code}\n"
{"error":"viewers cannot create tasks"}
HTTP 403

# …but editing a task has no check at all, so the viewer's edit is saved (see Issue 2)
$ curl -s -X PATCH $OLD/api/tasks/$TASK -H "Authorization: Bearer $VIEWER" \
    -H "Content-Type: application/json" -d '{"title":"Edited by a viewer","status":"done"}' -w "\nHTTP %{http_code}\n"
{"task":{"id":"6accdf2d-…","title":"Edited by a viewer","status":"done", …}}
HTTP 200

# There is no API the frontend can call to find out what the user may do
$ curl -s $OLD/api/users/me/permissions -H "Authorization: Bearer $VIEWER" -o /dev/null -w "HTTP %{http_code}\n"
HTTP 404
```

### After: role → permission mapping in the database

The new `permission_mapping` table maps each role to rows in `auth_permission`:

- **admin:** every permission.
- **member:** view the project, plus everything to do with tasks, export, comments and activity.
- **viewer:** view the project, tasks, comments and activity.

Every view checks the mapping with `has_permission(membership, '<codename>')`. The frontend loads the same permissions from `GET /api/users/me/permissions` and hides actions the user can't perform.

```console
$ db "select role, count(*) from permission_mapping group by role order by role"
admin|40
member|9
viewer|4

$ curl -s $NEW/api/users/me/permissions -H "Authorization: Bearer $VIEWER" | jq
{
  "projects": {
    "e7156a22-c648-4447-8a6a-60f91924171d": {
      "role": "viewer",
      "permissions": ["view_activity", "view_comment", "view_project", "view_task"]
    }
  }
}

# The same viewer edit is now rejected, and the task is unchanged
$ curl -s -X PATCH $NEW/api/tasks/$TASK -H "Authorization: Bearer $VIEWER" \
    -H "Content-Type: application/json" -d '{"title":"Edited by a viewer","status":"done"}' -w "\nHTTP %{http_code}\n"
{"error":"you do not have permission to edit tasks"}
HTTP 403

# A member can edit tasks but not the project, because change_project is not mapped to member
$ curl -s -X PATCH $NEW/api/tasks/$TASK -H "Authorization: Bearer $MEMBER" \
    -H "Content-Type: application/json" -d '{"status":"done"}' | jq "{status: .task.status}"
{
  "status": "done"
}
$ curl -s -X PATCH $NEW/api/projects/$PROJECT -H "Authorization: Bearer $MEMBER" \
    -H "Content-Type: application/json" -d '{"name":"Renamed by a member"}' -w "\nHTTP %{http_code}\n"
{"error":"you do not have permission to update this project"}
HTTP 403
```

`$OLD` is the original commit `acf2058` and `$NEW` is the current code, both run on the same seeded data. The full, unedited output is in sections 3 and 4 of [TERMINAL_LOG.md](TERMINAL_LOG.md).

## Issue 2:

Although I am not able to add a new task but I am able to edit a task's title and description and even change the assignee and the status.

**Category:** Security

**Severity:** Very High

## Issue 3:

When we open Task details after creating a task and click on Save, the assignee is shown in the task card but when task detailed is opened again the drop down says `unassigned`.

After refreshing the page, the newly created task still stays `unsassinged` and the new assignee does not even after on the Card.

**Category:** Data Integrity

**Severity:** High

## Issue 4:

No use of Refresh Tokens. An access token will long expiry comes with a security concern and should rotated frequenctly in order prevent malicious attacks.

**Category:** Security

**Severity:** High


# Improvements

This contains a list of improvement that can be made in order to make better UX.

## Improvement 1:
Delete task feature on the Task card should have a dialog in order to warn the user 

## Improvement 2:
After a task in updated the task is moved to the bottom of the list but the position should be maintained. Also there is not ability to move the task up or down within the same category.

## Improvement 3:
A drag and drop feature to update the status would be better

## Improvement 4:
Tasks under backend can have a separate module

## Improvement 5:
Creating a separate table for roles and task statuses and using the ids instead of slugs in the database