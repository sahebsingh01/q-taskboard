# Code Review

This documents contains a list of bugs found during the code review. The bugs are mentioned along with their Severity (Security / Performance / Architecture / Data Integrity / Testing) in descending order.

## Issue 1:

The current RBAC (Role Based Access Control) is not defined as it should be causing us to rely on the code level checks in the backend. 

There can be role - permission mapping in the database and the permissions should be checked in order to make that the correct user is able to perform the allowed action. These permission should be available in the frontend side as well so that Frontend can show/hide UI to prevent restricted actions to be performed. 

**Category:** Security

**Severity:** Very High

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