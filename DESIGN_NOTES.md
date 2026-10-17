# Design notes

Every change and its activity record are written in one database transaction. If the activity record
can't be saved, the whole request rolls back and the API returns `503` with a
"your change was not saved" message, so the user can simply retry.
