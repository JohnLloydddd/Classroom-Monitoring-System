BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS "alembic_version" (
	"version_num"	VARCHAR(32) NOT NULL,
	CONSTRAINT "alembic_version_pkc" PRIMARY KEY("version_num")
);
CREATE TABLE IF NOT EXISTS "amenities" (
	"id"	INTEGER NOT NULL,
	"name"	TEXT NOT NULL,
	PRIMARY KEY("id"),
	CONSTRAINT "uq_amenities_name" UNIQUE("name")
);
CREATE TABLE IF NOT EXISTS "departments" (
	"id"	INTEGER NOT NULL,
	"name"	VARCHAR(255) NOT NULL,
	PRIMARY KEY("id"),
	CONSTRAINT "uq_departments_name" UNIQUE("name")
);
CREATE TABLE IF NOT EXISTS "professor" (
	"id"	INTEGER NOT NULL,
	"name"	VARCHAR(100) NOT NULL,
	"rfid_tag"	VARCHAR(100) NOT NULL,
	PRIMARY KEY("id"),
	UNIQUE("rfid_tag")
);
CREATE TABLE IF NOT EXISTS "rfid_log" (
	"id"	INTEGER NOT NULL,
	"professor_id"	INTEGER,
	"room_id"	INTEGER,
	"timestamp"	DATETIME NOT NULL,
	PRIMARY KEY("id"),
	FOREIGN KEY("professor_id") REFERENCES "professor"("id"),
	FOREIGN KEY("room_id") REFERENCES "room"("id")
);
CREATE TABLE IF NOT EXISTS "room" (
	"id"	INTEGER NOT NULL,
	"room_number"	VARCHAR(10) NOT NULL,
	"status"	VARCHAR(20) NOT NULL,
	"rfid_tag"	VARCHAR(100),
	"department_id"	INTEGER,
	PRIMARY KEY("id"),
	CONSTRAINT "uq_room_rfid_tag" UNIQUE("rfid_tag"),
	UNIQUE("room_number"),
	CONSTRAINT "fk_room_department_id" FOREIGN KEY("department_id") REFERENCES "departments"("id")
);
CREATE TABLE IF NOT EXISTS "room_amenities" (
	"room_id"	INT NOT NULL,
	"amenity_id"	INT NOT NULL,
	PRIMARY KEY("room_id","amenity_id"),
	FOREIGN KEY("amenity_id") REFERENCES "amenities"("id"),
	FOREIGN KEY("room_id") REFERENCES "room"("id")
);
CREATE TABLE IF NOT EXISTS "user" (
	"id"	INTEGER NOT NULL,
	"username"	VARCHAR(64) NOT NULL,
	"password_hash"	VARCHAR(128) NOT NULL,
	PRIMARY KEY("id"),
	CONSTRAINT "uq_user_username" UNIQUE("username"),
	UNIQUE("username")
);
INSERT INTO "alembic_version" VALUES ('69d0bf3ee2f7');
INSERT INTO "departments" VALUES (1,'coe');
INSERT INTO "room" VALUES (1,'Room1','Occupied',NULL,NULL);
INSERT INTO "room" VALUES (2,'Hangar 2 (H2)','Vacant',NULL,NULL);
INSERT INTO "room" VALUES (3,'Hangar 3 (H3)','Occupied',NULL,NULL);
COMMIT;
