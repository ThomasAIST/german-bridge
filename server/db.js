const mysql = require('mysql2/promise');

let pool;

const connectionConfig = {
  host: process.env.MYSQL_HOST,
  port: Number(process.env.MYSQL_PORT || 3306),
  user: process.env.MYSQL_USER,
  password: process.env.MYSQL_PASSWORD,
  ssl: process.env.MYSQL_SSL === 'true' ? {} : undefined,
};

function databaseName() {
  const name = process.env.MYSQL_DATABASE;
  if (!name || !/^[A-Za-z0-9_$-]+$/.test(name)) {
    throw new Error('MYSQL_DATABASE must contain only letters, numbers, underscores, hyphens, or dollar signs.');
  }
  return name;
}

async function init() {
  const name = databaseName();
  const admin = await mysql.createConnection(connectionConfig);
  try {
    await admin.query(`CREATE DATABASE IF NOT EXISTS \`${name}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci`);
  } finally {
    await admin.end();
  }

  pool = mysql.createPool({
    ...connectionConfig,
    database: name,
    waitForConnections: true,
    connectionLimit: Number(process.env.MYSQL_CONNECTION_LIMIT || 10),
  });

  await pool.query(`
    CREATE TABLE IF NOT EXISTS users (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
      username VARCHAR(20) NOT NULL UNIQUE,
      password_hash VARCHAR(255) NOT NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB
  `);
  await pool.query(`
    CREATE TABLE IF NOT EXISTS games (
      id VARCHAR(100) NOT NULL PRIMARY KEY,
      mode VARCHAR(20) NOT NULL,
      num_players INT NOT NULL,
      rounds_played INT NOT NULL,
      started_at DATETIME NOT NULL,
      finished_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB
  `);
  await pool.query(`
    CREATE TABLE IF NOT EXISTS game_players (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
      game_id VARCHAR(100) NOT NULL,
      user_id BIGINT UNSIGNED NULL,
      display_name VARCHAR(20) NOT NULL,
      is_bot BOOLEAN NOT NULL DEFAULT FALSE,
      final_score INT NOT NULL,
      placement INT NOT NULL,
      CONSTRAINT fk_game_players_game FOREIGN KEY (game_id) REFERENCES games(id),
      CONSTRAINT fk_game_players_user FOREIGN KEY (user_id) REFERENCES users(id)
    ) ENGINE=InnoDB
  `);
}

async function get(sql, params = []) {
  const [rows] = await pool.execute(sql, params);
  return rows[0];
}

async function all(sql, params = []) {
  const [rows] = await pool.execute(sql, params);
  return rows;
}

async function run(sql, params = [], connection = pool) {
  const [result] = await connection.execute(sql, params);
  return result;
}

async function transaction(callback) {
  const connection = await pool.getConnection();
  try {
    await connection.beginTransaction();
    const result = await callback({ run: (sql, params) => run(sql, params, connection) });
    await connection.commit();
    return result;
  } catch (error) {
    await connection.rollback();
    throw error;
  } finally {
    connection.release();
  }
}

async function close() {
  if (pool) await pool.end();
}

module.exports = { init, get, all, run, transaction, close };
