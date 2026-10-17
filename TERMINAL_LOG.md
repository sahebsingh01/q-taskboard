# Terminal log

Every block below is real output from this machine, captured on 2026-10-17, in the order the sections were run.
Commands appear exactly as run, after `$`. JWTs are cut short, and the Airtable API key is never printed.

**How it was set up**

- So the demos wouldn't wipe the dev data (`seed` deletes everything), they run against a throwaway database, `taskboard_log`, in the same Postgres container.
- **Original code (bug proof):** a checkout of the original commit `acf2058`, served on `$OLD` = `http://localhost:8002`.
- **Current code (fix proof and demos):** served on `$NEW` = `http://localhost:8001`.
- Both servers use the same database, so the bug and the fix are shown on identical data.
- Shell helpers used below: `login`/`token` (POST `/api/auth/login`), `short` (cuts the JWT short), `db` (runs a query with `psql` against `taskboard_log`), `wait_job` (polls the export status).
- `$SCRATCH/airtable_rows.py` reads the Airtable table back through the API, in grid order.

## 1. Setup

```console
$ docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
NAME                     STATUS             PORTS
q-taskboard-backend-1    Up 28 minutes      0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp
q-taskboard-db-1         Up About an hour   0.0.0.0:5432->5432/tcp, [::]:5432->5432/tcp
q-taskboard-frontend-1   Up About an hour   0.0.0.0:3000->3000/tcp, [::]:3000->3000/tcp

$ docker exec q-taskboard-db-1 createdb -U taskboard taskboard_log

$ venv/bin/pip install -q -r requirements.txt && venv/bin/pip list 2>/dev/null | grep -iE "^(django|djangorestframework|djangorestframework-simplejwt|pyairtable|pytest-django) "
Django                        5.2.18
djangorestframework           3.18.3
pyairtable                    2.3.7
pytest-django                 4.14.0

$ POSTGRES_DB=taskboard_log venv/bin/python manage.py migrate
Operations to perform:
  Apply all migrations: auth, contenttypes, projects, users
Running migrations:
  Applying contenttypes.0001_initial... OK
  Applying contenttypes.0002_remove_content_type_name... OK
  Applying auth.0001_initial... OK
  Applying auth.0002_alter_permission_name_max_length... OK
  Applying auth.0003_alter_user_email_max_length... OK
  Applying auth.0004_alter_user_username_opts... OK
  Applying auth.0005_alter_user_last_login_null... OK
  Applying auth.0006_require_contenttypes_0002... OK
  Applying auth.0007_alter_validators_add_error_messages... OK
  Applying auth.0008_alter_user_username_max_length... OK
  Applying auth.0009_alter_user_last_name_max_length... OK
  Applying auth.0010_alter_group_name_max_length... OK
  Applying auth.0011_update_proxy_permissions... OK
  Applying auth.0012_alter_user_first_name_max_length... OK
  Applying users.0001_initial... OK
  Applying projects.0001_initial... OK
  Applying projects.0002_rolepermission... OK
  Applying projects.0003_seed_permission_mapping... OK
  Applying projects.0004_exportjob... OK
  Applying projects.0005_exportjob_skipped... OK
  Applying projects.0006_comments_activity... OK
  Applying projects.0007_seed_comment_activity_permissions... OK

$ POSTGRES_DB=taskboard_log venv/bin/python manage.py seed
seeding...
seed complete.
login with any of these (password: password123):
  meera@taskboard.dev   — admin on Q3 Launch, Internal Tools
  arjun@taskboard.dev   — admin on Onboarding, member on Q3 Launch
  kavya@example.com     — member on Q3 Launch
  dev@example.com       — viewer on Q3 Launch
  lina@example.com      — member on Onboarding
```

## 2. Initial test run (original commit `acf2058`)

```console
$ git log --oneline -1
acf2058 first commit

$ /Users/sahebsingh/Downloads/q-taskboard/backend/venv/bin/python -m pytest -p no:warnings -p no:cacheprovider 2>&1 | tail -4
projects/tests.py .......                                                [ 46%]
users/tests.py ........                                                  [100%]

============================== 15 passed in 2.20s ==============================

$ npx vitest run 2>&1 | grep -E "✓|×|FAIL|Test Files|Tests " | sort -u | head -20
      Tests  4 failed | 5 passed (9)
   × session management > clears token and user on clearSession 0ms
   × session management > returns null when no token is stored 2ms
   × session management > returns the stored user after setSession 0ms
   × session management > returns the token after setSession 0ms
 FAIL  src/tests/schemas.test.ts > session management > clears token and user on clearSession
 FAIL  src/tests/schemas.test.ts > session management > returns null when no token is stored
 FAIL  src/tests/schemas.test.ts > session management > returns the stored user after setSession
 FAIL  src/tests/schemas.test.ts > session management > returns the token after setSession
 Test Files  1 failed | 1 passed (2)
 ✓ src/tests/TaskCard.test.tsx (3 tests) 31ms
⎯⎯⎯⎯⎯⎯⎯ Failed Tests 4 ⎯⎯⎯⎯⎯⎯⎯
```

The 4 frontend failures come with the original code and are still there at the end. They're caused by the environment, not the app: Node on this machine ships an experimental global `localStorage` that hides jsdom's (`TypeError: Cannot read properties of undefined (reading 'removeItem')`).

## 3. Bug proof: a viewer can edit tasks (original code)

`dev@example.com` is a **viewer** on Q3 Launch. The original code blocks viewers from *creating* a task, yet lets them *edit* one: the PATCH returns 200 and the change is saved. There was also no permissions API for the frontend (404).

```console
$ export PROJECT=$(db "select id from projects where name='Q3 Launch'"); export TASK=$(db "select id from tasks where title='Draft press release'"); echo "PROJECT=$PROJECT TASK=$TASK"
PROJECT=e7156a22-c648-4447-8a6a-60f91924171d TASK=6accdf2d-58d5-4e52-8155-222c5a50c618

$ db "select u.email, m.role from memberships m join users u on u.id=m.user_id where m.project_id='$PROJECT' order by m.role"
meera@taskboard.dev|admin
arjun@taskboard.dev|member
kavya@example.com|member
dev@example.com|viewer

$ login $OLD dev@example.com | short
{
  "user": {
    "id": "c7ce8ce8-0ddb-4f4f-a552-945d179ca8da",
    "email": "dev@example.com",
    "name": "Dev Sharma"
  },
  "token": "eyJhbGciOiJIUzI1NiIs…(truncated)"
}

$ VIEWER=$(token $OLD dev@example.com)

$ curl -s -X POST $OLD/api/projects/$PROJECT/tasks -H "Authorization: Bearer $VIEWER" -H "Content-Type: application/json" -d '{"title":"viewer task"}' -w "\nHTTP %{http_code}\n"
{"error":"viewers cannot create tasks"}
HTTP 403

$ curl -s -X PATCH $OLD/api/tasks/$TASK -H "Authorization: Bearer $VIEWER" -H "Content-Type: application/json" -d '{"title":"Edited by a viewer","status":"done"}' -w "\nHTTP %{http_code}\n" | jq -R "fromjson? // ." | jq "if type==\"object\" then .task | {id, title, status} else . end"
{
  "id": "6accdf2d-58d5-4e52-8155-222c5a50c618",
  "title": "Edited by a viewer",
  "status": "done"
}
"HTTP 200"

$ db "select title, status from tasks where id='$TASK'"
Edited by a viewer|done

$ curl -s $OLD/api/users/me/permissions -H "Authorization: Bearer $VIEWER" -o /dev/null -w "HTTP %{http_code}\n"
HTTP 404
```

## 4. Fix proof: role permissions come from the `permission_mapping` table (current code)

```console
$ db "update tasks set title='Draft press release', status='review' where id='$TASK' returning title, status"   # reset the row the bug run changed
Draft press release|review
UPDATE 1

$ VIEWER=$(token $NEW dev@example.com); MEMBER=$(token $NEW arjun@taskboard.dev)

$ curl -s $NEW/api/users/me/permissions -H "Authorization: Bearer $VIEWER" | jq
{
  "projects": {
    "e7156a22-c648-4447-8a6a-60f91924171d": {
      "role": "viewer",
      "permissions": [
        "view_activity",
        "view_comment",
        "view_project",
        "view_task"
      ]
    }
  }
}

$ curl -s -X PATCH $NEW/api/tasks/$TASK -H "Authorization: Bearer $VIEWER" -H "Content-Type: application/json" -d '{"title":"Edited by a viewer","status":"done"}' -w "\nHTTP %{http_code}\n"
{"error":"you do not have permission to edit tasks"}
HTTP 403

$ db "select title, status from tasks where id='$TASK'"
Draft press release|review

$ curl -s $NEW/api/users/me/permissions -H "Authorization: Bearer $MEMBER" | jq --arg p $PROJECT ".projects[\$p]"
{
  "role": "member",
  "permissions": [
    "add_comment",
    "add_task",
    "change_task",
    "delete_task",
    "export_task",
    "view_activity",
    "view_comment",
    "view_project",
    "view_task"
  ]
}

$ curl -s -X PATCH $NEW/api/tasks/$TASK -H "Authorization: Bearer $MEMBER" -H "Content-Type: application/json" -d '{"status":"done"}' | jq "{status: .task.status}"
{
  "status": "done"
}

$ curl -s -X PATCH $NEW/api/projects/$PROJECT -H "Authorization: Bearer $MEMBER" -H "Content-Type: application/json" -d '{"name":"Renamed by a member"}' -w "\nHTTP %{http_code}\n"
{"error":"you do not have permission to update this project"}
HTTP 403

$ db "select role, count(*) from permission_mapping group by role order by role"
admin|40
member|9
viewer|4
```

## 5. Part 3c: Airtable export

"Customer Onboarding Revamp" (5 tasks, never exported before) is exported twice by its admin. Run 1 writes the 5 tasks into empty rows. Run 2 finds each `Task ID` already in the table and skips all 5, so no duplicates are created.

```console
$ backend/venv/bin/python -I $SCRATCH/airtable_rows.py .env "Customer Onboarding Revamp"   # before
grid rows: 13 | rows with a Task ID: 6 | duplicate Task IDs: 0
rows for project 'Customer Onboarding Revamp':
```

### Run 1

```console
$ export ONBOARDING=$(db "select id from projects where name='Customer Onboarding Revamp'"); ADMIN=$(token $NEW arjun@taskboard.dev); VIEWER=$(token $NEW dev@example.com); echo "ONBOARDING=$ONBOARDING"
ONBOARDING=ad1d6c2e-d367-4d2d-87f8-4bed13fa6a35

$ db "select count(*) from tasks where project_id='$ONBOARDING'"
5

$ curl -s -X POST $NEW/api/projects/$ONBOARDING/export -H "Authorization: Bearer $ADMIN" -w "\nHTTP %{http_code}\n"
{"job":{"id":"50732ed4-d712-4594-b8ef-a0411710ea26","status":"running","total":0,"created":0,"skipped":0,"failed":0,"errors":[],"error":null,"startedAt":"2026-10-17T15:41:11.083806+00:00","finishedAt":null}}
HTTP 202

$ wait_job   # polls GET /api/projects/$ONBOARDING/export until the job finishes
{
  "status": "succeeded",
  "total": 5,
  "created": 5,
  "skipped": 0,
  "failed": 0,
  "errors": [],
  "error": null
}
```

### Run 2 (nothing changed since run 1)

```console
$ curl -s -X POST $NEW/api/projects/$ONBOARDING/export -H "Authorization: Bearer $ADMIN" -o /dev/null -w "HTTP %{http_code}\n"
HTTP 202

$ wait_job
{
  "status": "succeeded",
  "total": 5,
  "created": 0,
  "skipped": 5,
  "failed": 0,
  "errors": [],
  "error": null
}
```

> The read-back between the two runs wasn't captured: the logging script used a wrong file path for it. The job results above are from the real runs. The read-back below was taken after both runs: the 5 rows each appear exactly once, and the number of rows holding a Task ID went from 6 to 11, with no duplicates.

```console
$ backend/venv/bin/python -I $SCRATCH/airtable_rows.py .env "Customer Onboarding Revamp"   # after both runs
grid rows: 13 | rows with a Task ID: 11 | duplicate Task IDs: 0
rows for project 'Customer Onboarding Revamp':
  row  7  01cada84…  Map current onboarding funnel              Done         Arjun Rao
  row  8  d4950f98…  Wireframe new welcome screens              In progress  Meera Iyer
  row  9  bfbbed90…  Interview 5 recently-onboarded customers   In review    Lina Joshi
  row 10  4b691e04…  Audit current onboarding emails            Todo         Lina Joshi
  row 11  ba713173…  Define success metric (TTFV target)        Todo         Arjun Rao

$ export PROJECT=$(db "select id from projects where name='Q3 Launch'"); VIEWER=$(token $NEW dev@example.com)   # dev is a viewer on Q3 Launch

$ curl -s -X POST $NEW/api/projects/$PROJECT/export -H "Authorization: Bearer $VIEWER" -w "\nHTTP %{http_code}\n"
{"error":"you do not have permission to export tasks"}
HTTP 403
```

### Airtable screenshot / share link

<!-- TODO: add a screenshot of the Tasks table (rows 7–11) or a read-only share link here -->
_Screenshot or share link to be added._

## 6. Parts 3a and 3b: task comments and activity feed

`kavya@example.com` is a **member** and `dev@example.com` a **viewer** on Q3 Launch. `lina@example.com` is not on the project.

```console
$ export PROJECT=$(db "select id from projects where name='Q3 Launch'"); MEMBER=$(token $NEW kavya@example.com); VIEWER=$(token $NEW dev@example.com); OUTSIDER=$(token $NEW lina@example.com); KAVYA_ID=$(db "select id from users where email='kavya@example.com'")

# 3b: a member creates a task, moves it, assigns it (each change leaves an activity record)

$ TASK=$(curl -s -X POST $NEW/api/projects/$PROJECT/tasks -H "Authorization: Bearer $MEMBER" -H "Content-Type: application/json" -d '{"title":"Write launch FAQ"}' | jq -r .task.id); echo "TASK=$TASK"
TASK=f1cfb7ef-0e3d-472e-9d1b-c07f71124201

$ curl -s -X PATCH $NEW/api/tasks/$TASK -H "Authorization: Bearer $MEMBER" -H "Content-Type: application/json" -d '{"status":"in_progress"}' | jq -c "{status: .task.status}"
{"status":"in_progress"}

$ curl -s -X PATCH $NEW/api/tasks/$TASK -H "Authorization: Bearer $MEMBER" -H "Content-Type: application/json" -d "{\"assigneeId\":\"$KAVYA_ID\"}" -o /dev/null -w "HTTP %{http_code}\n"
HTTP 200

# 3a: comments: members post, viewers read only, append-only

$ curl -s -X POST $NEW/api/tasks/$TASK/comments -H "Authorization: Bearer $MEMBER" -H "Content-Type: application/json" -d '{"body":"Drafted the first 10 questions."}' -w "\nHTTP %{http_code}\n"
{"comment":{"id":"2b051be4-8fa0-424f-acf0-d42a33f0a8ec","taskId":"f1cfb7ef-0e3d-472e-9d1b-c07f71124201","author":{"id":"cdc5ac4d-2edb-40d8-a626-77bd457455b9","email":"kavya@example.com","name":"Kavya Reddy"},"body":"Drafted the first 10 questions.","createdAt":"2026-10-17T15:42:02.534510+00:00"}}
HTTP 201

$ curl -s -X POST $NEW/api/tasks/$TASK/comments -H "Authorization: Bearer $MEMBER" -H "Content-Type: application/json" -d '{"body":"Added pricing questions; ready for review."}' -o /dev/null -w "HTTP %{http_code}\n"
HTTP 201

$ curl -s -X POST $NEW/api/tasks/$TASK/comments -H "Authorization: Bearer $VIEWER" -H "Content-Type: application/json" -d '{"body":"viewer comment"}' -w "\nHTTP %{http_code}\n"
{"error":"you do not have permission to comment"}
HTTP 403

$ curl -s $NEW/api/tasks/$TASK/comments -H "Authorization: Bearer $VIEWER" | jq ".comments[] | {author: .author.name, body, createdAt}"   # chronological
{
  "author": "Kavya Reddy",
  "body": "Drafted the first 10 questions.",
  "createdAt": "2026-10-17T15:42:02.534510+00:00"
}
{
  "author": "Kavya Reddy",
  "body": "Added pricing questions; ready for review.",
  "createdAt": "2026-10-17T15:42:03.582486+00:00"
}

$ for m in PATCH PUT DELETE; do printf "%-6s " $m; curl -s -X $m $NEW/api/tasks/$TASK/comments -H "Authorization: Bearer $MEMBER" -H "Content-Type: application/json" -d '{"body":"edited"}' -w " HTTP %{http_code}\n"; done
PATCH  {"detail":"Method \"PATCH\" not allowed."} HTTP 405
PUT    {"detail":"Method \"PUT\" not allowed."} HTTP 405
DELETE {"detail":"Method \"DELETE\" not allowed."} HTTP 405

$ curl -s -X POST $NEW/api/tasks/$TASK/comments -H "Authorization: Bearer $MEMBER" -H "Content-Type: application/json" -d '{"body":"   "}' -w "\nHTTP %{http_code}\n"
{"error":"comment cannot be empty"}
HTTP 400

$ curl -s $NEW/api/tasks/$TASK/comments -H "Authorization: Bearer $OUTSIDER" -w "\nHTTP %{http_code}\n"   # lina is not on Q3 Launch
{"error":"forbidden"}
HTTP 403

# 3b: activity feed, newest first, readable by every role, scoped to the project

$ curl -s "$NEW/api/projects/$PROJECT/activity?limit=10" -H "Authorization: Bearer $VIEWER" | jq -c ".activity[] | {when: .createdAt, who: .actor.name, verb, task: .task.title, data}"
{"when":"2026-10-17T15:42:03.583925+00:00","who":"Kavya Reddy","verb":"comment_added","task":"Write launch FAQ","data":{"excerpt":"Added pricing questions; ready for review.","commentId":"288cc9e4-308a-47b2-8dca-914ce6eb573a"}}
{"when":"2026-10-17T15:42:02.535634+00:00","who":"Kavya Reddy","verb":"comment_added","task":"Write launch FAQ","data":{"excerpt":"Drafted the first 10 questions.","commentId":"2b051be4-8fa0-424f-acf0-d42a33f0a8ec"}}
{"when":"2026-10-17T15:42:02.515778+00:00","who":"Kavya Reddy","verb":"assignee_changed","task":"Write launch FAQ","data":{"to":{"id":"cdc5ac4d-2edb-40d8-a626-77bd457455b9","name":"Kavya Reddy"},"from":null}}
{"when":"2026-10-17T15:42:02.495630+00:00","who":"Kavya Reddy","verb":"status_changed","task":"Write launch FAQ","data":{"to":"in_progress","from":"todo"}}
{"when":"2026-10-17T15:42:02.476201+00:00","who":"Kavya Reddy","verb":"task_created","task":"Write launch FAQ","data":{"status":"todo"}}
{"when":"2026-10-17T15:40:42.329784+00:00","who":"Arjun Rao","verb":"status_changed","task":"Draft press release","data":{"to":"done","from":"review"}}

$ curl -s $NEW/api/projects/$PROJECT/activity -H "Authorization: Bearer $OUTSIDER" -w "\nHTTP %{http_code}\n"
{"error":"forbidden"}
HTTP 403

$ curl -s -X PATCH $NEW/api/tasks/$TASK -H "Authorization: Bearer $VIEWER" -H "Content-Type: application/json" -d '{"status":"done"}' -o /dev/null -w "HTTP %{http_code}\n"; db "select count(*) from activities where task_id='$TASK'"   # rejected change, no new record
HTTP 403
5
```

## 7. Final test run (current code)

```console
$ git log --oneline -1 && git status --short
0b6793a Merge pull request #6 from sahebsingh01/doc/design-notes
 M backend/projects/activity.py
 M backend/projects/test_comments_activity.py
 M backend/projects/views.py
?? RECORDING.md

$ venv/bin/python -m pytest -p no:warnings -p no:cacheprovider 2>&1 | tail -6
projects/test_airtable_export.py ...............                         [ 23%]
projects/test_comments_activity.py ..........................            [ 64%]
projects/tests.py ...............                                        [ 87%]
users/tests.py ........                                                  [100%]

============================= 64 passed in 15.04s ==============================

$ npx tsc --noEmit 2>&1 | grep -c "^src" || true   # type errors in src/
0

$ npx vitest run 2>&1 | grep -E "✓|×|Test Files|Tests " | sort -u
      Tests  4 failed | 5 passed (9)
   × session management > clears token and user on clearSession 0ms
   × session management > returns null when no token is stored 2ms
   × session management > returns the stored user after setSession 0ms
   × session management > returns the token after setSession 0ms
 Test Files  1 failed | 1 passed (2)
 ✓ src/tests/TaskCard.test.tsx (3 tests) 32ms
⎯⎯⎯⎯⎯⎯⎯ Failed Tests 4 ⎯⎯⎯⎯⎯⎯⎯
```

Backend: 15 tests at the start, 64 now, all passing. Frontend: no type errors in `src/`; the same 4 environment-caused failures as in section 2.
