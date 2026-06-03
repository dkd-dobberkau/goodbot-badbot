-- Reduce the production MySQL user to least-privilege.
--
-- The app needs SELECT + INSERT for normal traffic, and CREATE so the
-- `CREATE TABLE IF NOT EXISTS visits` in lifespan() is a no-op rather
-- than an error on boot. No UPDATE, DELETE, ALTER, DROP.
--
-- Run as a privileged user (root) against the Mittwald MySQL.
-- Substitute ${MYSQL_DB} and ${MYSQL_USER} with the values from .deploy.env.

REVOKE ALL PRIVILEGES ON `${MYSQL_DB}`.* FROM '${MYSQL_USER}'@'%';
GRANT SELECT, INSERT, CREATE ON `${MYSQL_DB}`.* TO '${MYSQL_USER}'@'%';
FLUSH PRIVILEGES;

-- Verify the resulting grants:
SHOW GRANTS FOR '${MYSQL_USER}'@'%';
