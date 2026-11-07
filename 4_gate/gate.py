"""Stage 4: the automated gate. Compares old vs new for every table pair, every day, and decides.

For each pair:
  1. Line up rows by key (full outer join, so rows missing on either side are kept).
  2. Fingerprint each row (md5 of all business columns).
  3. Sort every key into: match / only in old / only in new / different values.
Rules: tool bookkeeping columns (starting with _) are ignored, rows the old tool flagged deleted are
skipped, only the newest version per key is used on the new side, blank text = NULL.

Results are stored in gate.check_results (history = proof) and emailed. Exit code 1 on any FAIL,
so CI goes red. A wave may cut over only after REQUIRED_CLEAN_DAYS all-PASS days in a row.
"""
import argparse
import datetime as dt
import os
import smtplib
import sys
import uuid
from email.mime.text import MIMEText
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import OUT, connect, read_csv, show  # noqa: E402

OLD_DELETED_FLAG = "_legacy_deleted"
NEW_LOADED_AT = "_loaded_at"
REQUIRED_CLEAN_DAYS = 7
NUMERIC = ("DECIMAL", "DOUBLE", "FLOAT", "REAL", "INTEGER", "BIGINT", "SMALLINT", "HUGEINT")


def columns(con, table):
    schema, name = table.split(".")
    return dict(con.execute("select column_name, data_type from information_schema.columns "
                            "where table_schema = ? and table_name = ? order by ordinal_position", [schema, name]).fetchall())


def norm(col, dtype, loose):
    if dtype.startswith(NUMERIC):
        return f"cast(round(cast({col} as double), 6) as varchar)"
    if dtype == "VARCHAR":
        return f"nullif(trim({col}), '')" if loose else col
    return f"cast({col} as varchar)"


def fingerprint(cols, types, loose):
    return "md5(concat_ws('|', " + ", ".join(f"coalesce({norm(c, types[c], loose)}, '<null>')" for c in cols) + "))"


def check_pair(con, p):
    left, right = p["left_table"], p["right_table"]
    lt, rt = columns(con, left), columns(con, right)
    if not lt or not rt:
        return dict(status="FAIL", reason=f"{left if not lt else right} not found")
    keys = p["key_columns"].split("|")
    biz = [c for c in lt if not c.startswith("_") and c in rt]
    missing = [c for c in lt if not c.startswith("_") and c not in rt]

    lsrc = f"select * from {left}" + (f" where not {OLD_DELETED_FLAG}" if OLD_DELETED_FLAG in lt else "")
    rsrc = f"select * from {right}"
    if NEW_LOADED_AT in rt:
        rsrc += f" qualify row_number() over (partition by {', '.join(keys)} order by {NEW_LOADED_AT} desc) = 1"

    side = lambda types: (f"select {fingerprint(keys, types, True)} k, {fingerprint(biz, types, False)} s, "
                          f"{fingerprint(biz, types, True)} x")
    left_rows, right_rows, only_old, only_new, diffs, blank_null = con.execute(f"""
        with l as ({side(lt)} from ({lsrc})), r as ({side(rt)} from ({rsrc}))
        select (select count(*) from l), (select count(*) from r),
               count_if(r.k is null), count_if(l.k is null),
               count_if(l.k = r.k and l.x <> r.x),
               count_if(l.k = r.k and l.s <> r.s and l.x = r.x)
        from l full outer join r on l.k = r.k""").fetchone()
    old_versions = con.execute(f"select count(*) from {right}").fetchone()[0] - right_rows

    reasons = []
    if missing:
        reasons.append("columns missing in new: " + ", ".join(missing))
    if only_old:
        reasons.append(f"{only_old:,} rows only in old")
    if only_new:
        reasons.append(f"{only_new:,} rows only in new")
    if diffs:
        reasons.append(f"{diffs:,} rows with different values")
    notes = []
    if blank_null:
        notes.append(f"{blank_null:,} rows differ only blank vs NULL (match)")
    if old_versions:
        notes.append(f"{old_versions:,} older versions ignored")
    return dict(status="FAIL" if reasons else "PASS", left_rows=left_rows, right_rows=right_rows,
                only_old=only_old, only_new=only_new, diffs=diffs,
                reason="; ".join(reasons) or "match", notes="; ".join(notes))


def clean_streak(con, wave):
    """All-PASS days in a row, ending with the latest run day (last run of each day counts)."""
    days = con.execute("""
        with runs as (select distinct run_id, run_ts::date d, run_ts from gate.check_results where wave = ?),
             last_run as (select * from runs qualify row_number() over (partition by d order by run_ts desc) = 1)
        select last_run.d, bool_and(c.status = 'PASS') from last_run join gate.check_results c using (run_id)
        group by 1 order by 1 desc""", [wave]).fetchall()
    streak, expected = 0, days[0][0] if days else None
    for d, ok in days:
        if not ok or d != expected:
            break
        streak, expected = streak + 1, d - dt.timedelta(days=1)
    return streak


def report_html(wave, results, streak):
    rows = "".join(
        f"<tr><td>{r['layer']}</td><td>{r['left']}</td><td>{r['right']}</td><td>{r.get('left_rows', '')}</td>"
        f"<td>{r.get('right_rows', '')}</td><td style='color:{'#1b7f3b' if r['status'] == 'PASS' else '#c0392b'}'>"
        f"<b>{r['status']}</b></td><td>{r['reason']}<br><small>{r.get('notes', '')}</small></td></tr>" for r in results)
    passed = sum(r["status"] == "PASS" for r in results)
    return (f"<html><body style='font-family:Arial;font-size:13px'><h3>{wave}: {passed} of {len(results)} checks PASS</h3>"
            f"<p>Clean days in a row: <b>{streak} of {REQUIRED_CLEAN_DAYS}</b> needed to cut over.</p>"
            "<table border=1 cellpadding=4 style='border-collapse:collapse'><tr><th>Layer</th><th>Old / prod</th>"
            f"<th>New / test</th><th>Rows old</th><th>Rows new</th><th>Status</th><th>Reason</th></tr>{rows}</table></body></html>")


def send_email(subject, html):
    host, to = os.environ.get("SMTP_HOST"), os.environ.get("GATE_EMAIL_TO")
    if not (host and to):
        print("  Email skipped (set SMTP_HOST, SMTP_USER, SMTP_PASSWORD, GATE_EMAIL_TO to enable)")
        return
    msg = MIMEText(html, "html")
    msg["Subject"], msg["From"], msg["To"] = subject, os.environ.get("SMTP_USER", "gate@localhost"), to
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", 587))) as s:
        s.starttls()
        if os.environ.get("SMTP_USER"):
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.send_message(msg)
    print(f"  Emailed {to}")


def main(wave="Wave 2", email=False):
    con = connect()
    con.execute("create schema if not exists gate")
    con.execute("""create table if not exists gate.check_results (run_id varchar, run_ts timestamp, wave varchar,
        layer varchar, left_table varchar, right_table varchar, left_rows bigint, right_rows bigint, only_old bigint,
        only_new bigint, value_diffs bigint, status varchar, reason varchar, notes varchar)""")
    run_id, run_ts = str(uuid.uuid4()), dt.datetime.now()

    results = []
    for p in (p for p in read_csv(HERE / "table_pairs.csv") if p["wave"] == wave):
        try:
            r = check_pair(con, p)
        except Exception as e:  # a broken check is a FAIL, never a silent skip
            r = dict(status="FAIL", reason=str(e)[:300])
        r.update(layer=p["layer"], left=p["left_table"], right=p["right_table"])
        con.execute("insert into gate.check_results values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [run_id, run_ts, wave, r["layer"], r["left"], r["right"], r.get("left_rows"), r.get("right_rows"),
                     r.get("only_old"), r.get("only_new"), r.get("diffs"), r["status"], r["reason"], r.get("notes")])
        results.append(r)

    streak = clean_streak(con, wave)
    con.close()
    passed = sum(r["status"] == "PASS" for r in results)
    show(results, ["layer", "left", "status", "reason", "notes"])
    print(f"  {passed} of {len(results)} PASS. Clean days in a row: {streak} of {REQUIRED_CLEAN_DAYS}.")

    html = report_html(wave, results, streak)
    (OUT / "gate_report.html").write_text(html)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(html.replace("<html><body style='font-family:Arial;font-size:13px'>", "").replace("</body></html>", "\n"))
    if email:
        send_email(f"Migration gate {wave}: {passed} of {len(results)} PASS", html)
    return passed == len(results)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", default="Wave 2")
    ap.add_argument("--email", action="store_true")
    a = ap.parse_args()
    sys.exit(0 if main(a.wave, a.email) else 1)
