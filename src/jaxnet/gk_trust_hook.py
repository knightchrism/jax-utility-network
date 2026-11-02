"""geoknight-trust hook: counts-only checks on DB tables (PostGIS or DuckDB) and files.

Never reads or writes record values; reports are counts only. Never builds any list or flag of
s.119.071 exempt parcels. Phone-like column names stop the run (assert_no_phone_columns).
Copyright (c) 2026 GeoKnight GIS. All rights reserved.
"""
from __future__ import annotations

from pathlib import Path

from geoknight_trust import LayerCheck, log_change, run_checks
from geoknight_trust.io import read_layer


def _q(conn, sql):
    if hasattr(conn, "cursor") and not hasattr(conn, "sql"):     # psycopg / DB-API
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    return conn.execute(sql).fetchall()                          # duckdb


def _ident(name):
    return ".".join('"' + p.replace('"', '""') + '"' for p in name.split("."))


def table_check(conn, table, *, kind="postgis", geom=None, id_field=None, key_fields=(), source_count=None,
                source_count_label=None, expected_crs=None, name=None, **thresholds) -> LayerCheck:
    """LayerCheck for a DB table with counts computed in SQL. kind: 'postgis' or 'duckdb'."""
    t = _ident(table)
    if kind == "postgis":
        sch, _, tb = table.rpartition(".")
        cols = [r[0] for r in _q(conn, f"select column_name from information_schema.columns where table_name='{tb}'"
                                       + (f" and table_schema='{sch}'" if sch else "") + " order by ordinal_position")]
    else:
        cols = [r[0] for r in _q(conn, f"select * from {t} limit 0")] if False else \
               [r[0] for r in _q(conn, f"describe {t}")]
    parts = ["count(*)"]
    if geom:
        g = _ident(geom)
        if kind == "postgis":
            parts += [f"count(*) filter (where {g} is null)", f"count(*) filter (where {g} is not null and ST_IsEmpty({g}))",
                      f"count(*) filter (where {g} is not null and not ST_IsEmpty({g}) and not ST_IsValid({g}))",
                      f"max(ST_SRID({g}))"]
        else:
            parts += [f"count(*) filter (where {g} is null)", f"count(*) filter (where {g} is not null and ST_IsEmpty({g}))",
                      f"count(*) filter (where {g} is not null and not ST_IsEmpty({g}) and not ST_IsValid({g}))", "null"]
    parts += [f"count(*) filter (where {_ident(f)} is null or trim(cast({_ident(f)} as varchar)) = '')" for f in key_fields]
    row = _q(conn, f"select {', '.join(parts)} from {t}")[0]
    st = {"rows": int(row[0]), "geometry": bool(geom)}
    i = 1
    if geom:
        st.update(missing_geometry=int(row[1]), empty_geometry=int(row[2]), invalid_geometry=int(row[3]))
        st["crs"] = f"EPSG:{row[4]}" if row[4] else (expected_crs or "none")
        i = 5
    else:
        st["crs"] = "n/a (tabular)"
    st["null_counts"] = {f: int(row[i + k]) for k, f in enumerate(key_fields)}
    if id_field:
        d = _q(conn, f"select count(*), coalesce(sum(n),0) from (select count(*) n from {t} where {_ident(id_field)} is not null "
                     f"group by {_ident(id_field)} having count(*) > 1) x")[0]
        st.update(duplicate_id_values=int(d[0]), rows_with_duplicate_id=int(d[1]))
    return LayerCheck(name or table, None, id_field=id_field, key_fields=list(key_fields), source_count=source_count,
                      source_count_label=source_count_label, expected_crs=expected_crs, stats=st, columns=cols,
                      **thresholds)


def file_check(path, *, name=None, layer=None, **kw) -> LayerCheck:
    df = read_layer(path, layer)
    return LayerCheck(name or Path(path).stem, df, **kw)


def run(out_dir, load_name, checks, *, approved_by="pipeline (automatic)"):
    """Run checks, write CHECK_REPORT.md/check_report.json, append CHANGELOG.csv. Returns the report."""
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    rep = run_checks(out, checks, load_name=load_name)
    rows = sum(int(c.stats["rows"]) if c.stats else len(c.data) for c in checks)
    log_change(out / "CHANGELOG.csv", layer=load_name, change="trust check",
               reason=f"geoknight-trust check: {rep['overall']}", records_affected=rows, approved_by=approved_by)
    print(f"[trust] {load_name}: {rep['overall']} -> {out}/CHECK_REPORT.md")
    return rep
