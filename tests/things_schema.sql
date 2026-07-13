-- Things 3 schema (database version 26), dumped from a real main.sqlite.
-- Only the tables things.py queries. Used to build the test fixture DB
-- so reads.py is testable in CI without Things installed.

CREATE TABLE 'Meta' (                    'key'                 TEXT PRIMARY KEY,                'value'               TEXT                             );

CREATE TABLE 'TMArea' (                  'uuid'                 TEXT PRIMARY KEY,               'title'                TEXT,                           'visible'              INTEGER,                        'index'                INTEGER                         , 'cachedTags' BLOB, experimental BLOB);

CREATE TABLE 'TMAreaTag' (                                                     'areas'                TEXT NOT NULL,                                                        'tags'                 TEXT NOT NULL                                                         );

CREATE TABLE 'TMChecklistItem' (                                                 'uuid'                 TEXT PRIMARY KEY,                                                       'userModificationDate' REAL,                                                                   'creationDate'         REAL,                                                                   'title'                TEXT,                                                                   'status'               INTEGER,                                                                'stopDate'             REAL,                                                                   'index'                INTEGER,                                                                'task'                 TEXT                                                                    , 'leavesTombstone' INTEGER, experimental BLOB);

CREATE TABLE 'TMSettings' (                 'uuid'                 TEXT PRIMARY KEY,                  'logInterval'          INTEGER,                           'manualLogDate'        REAL                               , 'groupTodayByParent' INTEGER, 'uriSchemeAuthenticationToken' TEXT, experimental BLOB);

CREATE TABLE 'TMTag' (                   'uuid'                 TEXT PRIMARY KEY,               'title'                TEXT,                           'shortcut'             TEXT,                           'usedDate'             REAL,                           'parent'               TEXT,                           'index'                INTEGER                         , experimental BLOB);

CREATE TABLE TMTask (

        "uuid"                              TEXT PRIMARY KEY,
        "leavesTombstone"                   INTEGER,

        "creationDate"                      REAL,
        "userModificationDate"              REAL,

        "type"                              INTEGER,

        "status"                            INTEGER,
        "stopDate"                          REAL,

        "trashed"                           INTEGER,

        "title"                             TEXT,
        "notes"                             TEXT,
        "notesSync"                         INTEGER,

        "cachedTags"                        BLOB,

        "start"                             INTEGER,
        "startDate"                         INTEGER,   -- REAL -> INTEGER
        "startBucket"                       INTEGER,
        "reminderTime"                      INTEGER,
        "lastReminderInteractionDate"       REAL,      -- Renamed from "lastAlarmInteractionDate"

        "deadline"                          INTEGER,   -- Renamed from "dueDate", REAL -> INTEGER
        "deadlineSuppressionDate"           INTEGER,   -- Renamed from "dueDateSuppressionDate", REAL -> INTEGER
        "t2_deadlineOffset"                 INTEGER,   -- Renamed from "dueDateOffset"

        "index"                             INTEGER,
        "todayIndex"                        INTEGER,
        "todayIndexReferenceDate"           INTEGER,   -- REAL -> INTEGER

        "area"                              TEXT,
        "project"                           TEXT,
        "heading"                           TEXT,      -- Renamed from "actionGroup"
        "contact"                           TEXT,      -- Renamed from "delegate"

        "untrashedLeafActionsCount"         INTEGER,
        "openUntrashedLeafActionsCount"     INTEGER,

        "checklistItemsCount"               INTEGER,
        "openChecklistItemsCount"           INTEGER,

        "rt1_repeatingTemplate"             TEXT,      -- Renamed from "repeatingTemplate"
        "rt1_recurrenceRule"                BLOB,      -- Renamed from "recurrenceRule"
        "rt1_instanceCreationStartDate"     INTEGER,   -- Renamed from "instanceCreationStartDate", REAL -> INTEGER
        "rt1_instanceCreationPaused"        INTEGER,   -- Renamed from "instanceCreationPaused"
        "rt1_instanceCreationCount"         INTEGER,   -- Renamed from "instanceCreationCount"
        "rt1_afterCompletionReferenceDate"  INTEGER,   -- Renamed from "afterCompletionReferenceDate", REAL -> INTEGER
        "rt1_nextInstanceStartDate"         INTEGER,   -- Renamed from "nextInstanceStartDate", REAL -> INTEGER

        "experimental"                      BLOB,

        "repeater"                          BLOB,
        "repeaterMigrationDate"             REAL
    );

CREATE TABLE 'TMTaskTag' (                                                     'tasks'                TEXT NOT NULL,                                                        'tags'                 TEXT NOT NULL                                                         );
