#!/usr/bin/env bash
# Daily usage stats from Postgres into stats/daily.tsv, one row per day. Not part of the app:
# read-only SQL through the db container. Cron (after midnight in STATS_TZ):
#   10 0 * * * /opt/battleship/stats.sh >> /opt/battleship/stats/cron.log 2>&1
#
#   ./stats.sh                        yesterday
#   ./stats.sh 2026-10-01             one day
#   ./stats.sh 2026-10-01 2026-10-13  a range (backfill: every column is exact for past days)
#   column -t -s $'\t' stats/daily.tsv | less -S     to read it
#
# Days already in the file are skipped, so a rerun is safe. To recompute a day, delete its row.
# Today is never written (it is not over yet), so a range may end with today.
# Columns:
#   date             day in STATS_TZ
#   new_visitors     player ids issued that day (≈ new browsers that opened the site)
#   players_total    player ids issued up to the end of the day
#   played_total     of them, ever played at least one game (vs model or human)
#   active           distinct people who played that day
#   returning        of them, whose id was issued before that day
#   active_touch     of them, on a touch device (phone / tablet)
#   h2m_games        games vs the model started that day (finished + left mid-game)
#   h2m_finished     of them, played to the end
#   h2m_human_wins   of them, won by the human
#   h2m_players      distinct people who played vs the model
#   h2h_games        human-vs-human matches played (ended that day; walk-outs included)
#   h2h_room         of them, by invite link
#   h2h_queue        of them, random opponent
#   h2h_walkouts     of them, ended by resign / idle / disconnect
#   h2h_players      distinct people who played vs a human
#   rooms_unanswered invite rooms nobody joined
#   h2h_abandoned    all matches that never started (unanswered rooms + placement timeouts)
#   reports          reports filed on opponents
#   name_rejects     names rejected by moderation
set -euo pipefail
cd "$(dirname "$0")"

TZ_NAME=${STATS_TZ:-Europe/Moscow}
OUT=${STATS_OUT:-stats/daily.tsv}
# on the VPS: psql in the db container; locally e.g. PSQL="psql -d battleship" ./stats.sh
PSQL=${PSQL:-docker compose exec -T db psql -U battleship -d battleship}

COLUMNS="date new_visitors players_total played_total active returning active_touch h2m_games h2m_finished h2m_human_wins h2m_players h2h_games h2h_room h2h_queue h2h_walkouts h2h_players rooms_unanswered h2h_abandoned reports name_rejects"

mkdir -p "$(dirname "$OUT")"
[ -s "$OUT" ] || echo "$COLUMNS" | tr ' ' '\t' > "$OUT"

rows=$($PSQL -X -q -A -t -F $'\t' -v ON_ERROR_STOP=1 \
  -v tz="$TZ_NAME" -v from="${1:-}" -v to="${2:-${1:-}}" <<'SQL'
BEGIN READ ONLY;
SET LOCAL TIME ZONE :'tz';
WITH days AS (
  SELECT d::date AS day, d::date::timestamptz AS t0, (d::date + 1)::timestamptz AS t1
  FROM generate_series(coalesce(nullif(:'from', '')::date, current_date - 1),
                       coalesce(nullif(:'to', '')::date, current_date - 1),
                       interval '1 day') AS d
  WHERE d < current_date      -- only finished days: a row once written is never updated
),
-- every game a human took part in: (player, when, mode, touch)
acts AS (
  SELECT attacker_player AS pid, created_at AS t, mode, (client_info->>'touch')::boolean AS touch
  FROM game_logs WHERE attacker_kind = 'player' AND attacker_player IS NOT NULL
  UNION ALL
  SELECT player_a, finished_at, 'h2h', NULL FROM h2h_matches WHERE status = 'finished'
  UNION ALL
  SELECT player_b, finished_at, 'h2h', NULL FROM h2h_matches WHERE status = 'finished' AND player_b IS NOT NULL
),
first_play AS (SELECT pid, min(t) AS t FROM acts GROUP BY pid),
-- one row per game vs the model: the log where the human attacks (the other log of the game,
-- the model attacking, has the same client_game_id)
h2m AS (
  SELECT client_game_id, created_at AS t, won
  FROM game_logs WHERE mode = 'h2m' AND attacker_kind = 'player'
)
SELECT
  d.day,
  (SELECT count(*) FROM players p WHERE p.created_at >= d.t0 AND p.created_at < d.t1),
  (SELECT count(*) FROM players p WHERE p.created_at < d.t1),
  (SELECT count(*) FROM first_play f WHERE f.t < d.t1),
  (SELECT count(DISTINCT a.pid) FROM acts a WHERE a.t >= d.t0 AND a.t < d.t1),
  (SELECT count(DISTINCT a.pid) FROM acts a JOIN players p ON p.id = a.pid
     WHERE a.t >= d.t0 AND a.t < d.t1 AND p.created_at < d.t0),
  (SELECT count(DISTINCT a.pid) FROM acts a WHERE a.t >= d.t0 AND a.t < d.t1 AND a.touch),
  (SELECT count(*) FROM h2m g WHERE g.t >= d.t0 AND g.t < d.t1),
  (SELECT count(*) FROM h2m g WHERE g.t >= d.t0 AND g.t < d.t1 AND g.won IS NOT NULL),
  (SELECT count(*) FROM h2m g WHERE g.t >= d.t0 AND g.t < d.t1 AND g.won),
  (SELECT count(DISTINCT a.pid) FROM acts a WHERE a.t >= d.t0 AND a.t < d.t1 AND a.mode = 'h2m'),
  (SELECT count(*) FROM h2h_matches m WHERE m.status = 'finished' AND m.finished_at >= d.t0 AND m.finished_at < d.t1),
  (SELECT count(*) FROM h2h_matches m WHERE m.status = 'finished' AND m.finished_at >= d.t0 AND m.finished_at < d.t1 AND m.kind = 'room'),
  (SELECT count(*) FROM h2h_matches m WHERE m.status = 'finished' AND m.finished_at >= d.t0 AND m.finished_at < d.t1 AND m.kind = 'queue'),
  (SELECT count(*) FROM h2h_matches m WHERE m.status = 'finished' AND m.finished_at >= d.t0 AND m.finished_at < d.t1
     AND m.end_reason IN ('resigned', 'idle', 'disconnect', 'forfeit')),
  (SELECT count(DISTINCT a.pid) FROM acts a WHERE a.t >= d.t0 AND a.t < d.t1 AND a.mode = 'h2h'),
  (SELECT count(*) FROM h2h_matches m WHERE m.status = 'abandoned' AND m.kind = 'room' AND m.player_b IS NULL
     AND coalesce(m.finished_at, m.created_at) >= d.t0 AND coalesce(m.finished_at, m.created_at) < d.t1),
  (SELECT count(*) FROM h2h_matches m WHERE m.status = 'abandoned'
     AND coalesce(m.finished_at, m.created_at) >= d.t0 AND coalesce(m.finished_at, m.created_at) < d.t1),
  (SELECT count(*) FROM reports r WHERE r.created_at >= d.t0 AND r.created_at < d.t1),
  (SELECT count(*) FROM name_rejects n WHERE n.created_at >= d.t0 AND n.created_at < d.t1)
FROM days d ORDER BY d.day;
COMMIT;
SQL
)

# append only the days that are not in the file yet
added=0
while IFS= read -r line; do
  [ -n "$line" ] || continue
  day=${line%%$'\t'*}
  if grep -q "^$day"$'\t' "$OUT"; then
    echo "$day: уже есть в $OUT, пропускаю"
  else
    echo "$line" >> "$OUT"; added=$((added + 1))
  fi
done <<< "$rows"
echo "$(date '+%F %T') добавлено строк: $added → $OUT"
