/* Diocle embedded-SQL shim: what the verifier's precompiler's CALL "DIOSQL" statements run.
 *
 * The engine is SQLite (a stand-in, NOT DB2). The COBOL program is rewritten so every EXEC SQL statement becomes
 *   CALL "DIOSQL" USING BY CONTENT "<statement no>" SQLCA <work item> ...
 * Statement text, kinds and the argument specs live in dio_stmts.c, generated next to the rewritten program.
 * Each work item is one flag byte (' ' untouched, 'Y' value present, 'N' SQL NULL) followed by the value as
 * text: alphanumeric as-is, numeric as a sign character and digits (PIC S9(n)V9(s) SIGN LEADING SEPARATE).
 * DECIMAL columns are stored as integers scaled by 10^scale, so no float rounding ever enters.
 *
 * SQLCODE set: 0, +100, -803 duplicate key, -811 more than one row, -407 NULL into NOT NULL, -404 string too long,
 * -413 numeric overflow, -305 NULL fetched without an indicator, -501 cursor not open, -502 cursor already open,
 * -904 statement limit, -901 any other engine error. Everything else is outside the verified subset.
 * No network, no files other than the database named by DIOCLE_DB; DIOCLE_SQL_MAX_STMTS caps the statements run.
 */
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

extern const int dio_nstmts;
extern const int dio_kind[];     /* 1 select-into 2 exec 3 open 4 fetch 5 close 6 commit 7 rollback */
extern const int dio_cursor[];   /* cursor number for 3/4/5 */
extern const char *dio_sql[];    /* SQL text with ? markers (select-into, exec, open) */
extern const char *dio_args[];   /* "IX8,IN18.2,OX3!,ON9.0" : I/O, X/N, length or digits[.scale], ! = no indicator */

#define MAXARGS 24
#define MAXCUR 32
typedef struct { char dir, type; int len, scale, noind; } Arg;

static sqlite3 *db;
static int in_tx, nrun;
static sqlite3_stmt *cache[4096];
static sqlite3_stmt *cur[MAXCUR];
static int cur_open[MAXCUR];

#define SQLCODE_AT 12
#define SQLERRD3_AT (96 + 8)

static void set_code(unsigned char *ca, int code, int rows)
{
    int32_t v = code;
    memcpy(ca + SQLCODE_AT, &v, 4);   /* PIC S9(9) COMP-5: native endian */
    if (rows >= 0) { v = rows; memcpy(ca + SQLERRD3_AT, &v, 4); }
}

static int parse_args(const char *s, Arg *a)
{
    int n = 0;
    while (*s && n < MAXARGS) {
        a[n].dir = *s++; a[n].type = *s++;
        a[n].len = (int)strtol(s, (char **)&s, 10); a[n].scale = 0; a[n].noind = 0;
        if (*s == '.') { s++; a[n].scale = (int)strtol(s, (char **)&s, 10); }
        if (*s == '!') { a[n].noind = 1; s++; }
        if (*s == ',') s++;
        n++;
    }
    return n;
}

static int arg_size(const Arg *a) { return 1 + (a->type == 'X' ? a->len : 1 + a->len + a->scale); }

static int map_error(int rc)
{
    const char *m = sqlite3_errmsg(db);
    if (strstr(m, "UNIQUE constraint failed") || strstr(m, "PRIMARY KEY")) return -803;
    if (strstr(m, "NOT NULL constraint failed")) return -407;
    if (strstr(m, "dio_len")) return -404;
    if (strstr(m, "dio_prec")) return -413;
    (void)rc;
    return -901;
}

static void open_db(void)
{
    const char *path = getenv("DIOCLE_DB");
    if (!path || sqlite3_open_v2(path, &db, SQLITE_OPEN_READWRITE, NULL) != SQLITE_OK) {
        fprintf(stderr, "DIOSQL: cannot open the database named by DIOCLE_DB\n");
        exit(99);
    }
    sqlite3_exec(db, "PRAGMA max_page_count=8192", 0, 0, 0);
}

static int bind_inputs(sqlite3_stmt *st, const Arg *a, int na, void **p)
{
    int idx = 1;
    for (int i = 0; i < na; i++) {
        if (a[i].dir != 'I') continue;
        const unsigned char *w = p[i];
        if (w[0] == 'N') { sqlite3_bind_null(st, idx++); continue; }
        if (a[i].type == 'X') {
            int n = a[i].len;
            while (n > 0 && w[n] == ' ') n--;        /* CHAR semantics: trailing blanks are not data */
            sqlite3_bind_text(st, idx++, (const char *)w + 1, n, SQLITE_TRANSIENT);
        } else {
            char buf[64]; int nd = a[i].len + a[i].scale;
            if (nd > 40) nd = 40;
            memcpy(buf, w + 1, 1 + nd); buf[1 + nd] = 0;
            sqlite3_bind_int64(st, idx++, strtoll(buf[0] == '+' ? buf + 1 : buf, NULL, 10));
        }
    }
    return idx - 1;
}

static void put_value(const Arg *a, unsigned char *w, sqlite3_stmt *st, int col, int *nulls_bad)
{
    if (sqlite3_column_type(st, col) == SQLITE_NULL) {
        w[0] = 'N';
        if (a->noind) *nulls_bad = 1;
        return;
    }
    w[0] = 'Y';
    if (a->type == 'X') {
        const unsigned char *t = sqlite3_column_text(st, col);
        int n = sqlite3_column_bytes(st, col);
        memset(w + 1, ' ', a->len);
        memcpy(w + 1, t, n < a->len ? n : a->len);
    } else {
        long long v = sqlite3_column_int64(st, col);
        char buf[80]; int nd = a->len + a->scale;
        unsigned long long m = v < 0 ? 0ULL - (unsigned long long)v : (unsigned long long)v;
        snprintf(buf, sizeof buf, "%0*llu", nd, m);
        w[1] = v < 0 ? '-' : '+';
        memcpy(w + 2, buf + (strlen(buf) > (size_t)nd ? strlen(buf) - nd : 0), nd);
    }
}

static void clear_outputs(const Arg *a, int na, void **p)
{
    for (int i = 0; i < na; i++) if (a[i].dir == 'O') ((unsigned char *)p[i])[0] = ' ';
}

static void close_all_cursors(void)
{
    for (int i = 0; i < MAXCUR; i++) if (cur[i]) { sqlite3_finalize(cur[i]); cur[i] = 0; cur_open[i] = 0; }
}

static void begin(void)
{
    if (!in_tx && sqlite3_exec(db, "BEGIN", 0, 0, 0) == SQLITE_OK) in_tx = 1;
}

static void finish(void)
{
    if (db && in_tx) sqlite3_exec(db, "COMMIT", 0, 0, 0);   /* DB2 batch commits at normal termination */
}

int DIOSQL(void *a0, void *a1, void *a2, void *a3, void *a4, void *a5, void *a6, void *a7, void *a8, void *a9,
           void *a10, void *a11, void *a12, void *a13, void *a14, void *a15, void *a16, void *a17, void *a18,
           void *a19, void *a20, void *a21, void *a22, void *a23, void *a24, void *a25)
{
    void *all[26] = {a0, a1, a2, a3, a4, a5, a6, a7, a8, a9, a10, a11, a12, a13, a14, a15, a16, a17, a18, a19,
                     a20, a21, a22, a23, a24, a25};
    unsigned char *ca = all[1];
    void **p = all + 2;
    char num[5]; memcpy(num, a0, 4); num[4] = 0;
    int id = atoi(num);
    Arg a[MAXARGS];
    int na = parse_args(dio_args[id], a);
    static int started;
    if (!started) { started = 1; open_db(); atexit(finish); }
    if (++nrun > (getenv("DIOCLE_SQL_MAX_STMTS") ? atoi(getenv("DIOCLE_SQL_MAX_STMTS")) : 500000)) {
        set_code(ca, -904, 0); return 0;
    }
    int kind = dio_kind[id], c = dio_cursor[id], rc;
    sqlite3_stmt *st;
    clear_outputs(a, na, p);
    if (kind == 6 || kind == 7) {
        if (in_tx) sqlite3_exec(db, kind == 6 ? "COMMIT" : "ROLLBACK", 0, 0, 0);
        in_tx = 0; close_all_cursors();     /* DB2 closes cursors without WITH HOLD at COMMIT/ROLLBACK */
        set_code(ca, 0, -1); return 0;
    }
    begin();
    if (kind == 5) {
        if (!cur_open[c]) { set_code(ca, -501, -1); return 0; }
        sqlite3_finalize(cur[c]); cur[c] = 0; cur_open[c] = 0; set_code(ca, 0, -1); return 0;
    }
    if (kind == 4) {
        if (!cur_open[c]) { set_code(ca, -501, -1); return 0; }
        rc = sqlite3_step(cur[c]);
        if (rc == SQLITE_DONE) { set_code(ca, 100, -1); return 0; }
        if (rc != SQLITE_ROW) { set_code(ca, map_error(rc), -1); return 0; }
        int bad = 0, col = 0;
        for (int i = 0; i < na; i++) if (a[i].dir == 'O') put_value(&a[i], (unsigned char *)p[i], cur[c], col++, &bad);
        set_code(ca, bad ? -305 : 0, -1); return 0;
    }
    if (kind == 3) {
        if (cur_open[c]) { set_code(ca, -502, -1); return 0; }
        if (sqlite3_prepare_v2(db, dio_sql[id], -1, &st, 0) != SQLITE_OK) { set_code(ca, -901, -1); return 0; }
        bind_inputs(st, a, na, p);
        cur[c] = st; cur_open[c] = 1; set_code(ca, 0, -1); return 0;
    }
    if (!cache[id] && sqlite3_prepare_v2(db, dio_sql[id], -1, &cache[id], 0) != SQLITE_OK) { set_code(ca, -901, -1); return 0; }
    st = cache[id];
    sqlite3_reset(st); sqlite3_clear_bindings(st);
    bind_inputs(st, a, na, p);
    if (kind == 2) {
        rc = sqlite3_step(st);
        int changed = sqlite3_changes(db);
        sqlite3_reset(st);
        if (rc != SQLITE_DONE) { set_code(ca, map_error(rc), 0); return 0; }
        set_code(ca, changed == 0 && dio_sql[id][0] != 'I' ? 100 : 0, changed); return 0;
    }
    /* select-into: exactly one row, else +100 / -811; host variables stay untouched on either */
    rc = sqlite3_step(st);
    if (rc == SQLITE_DONE) { sqlite3_reset(st); set_code(ca, 100, 0); return 0; }
    if (rc != SQLITE_ROW) { int code = map_error(rc); sqlite3_reset(st); set_code(ca, code, 0); return 0; }
    int ncol = sqlite3_column_count(st);
    unsigned char *tmp[MAXARGS]; int col = 0, bad = 0;
    for (int i = 0; i < na; i++) {
        tmp[i] = 0;
        if (a[i].dir == 'O' && col < ncol) {
            tmp[i] = calloc(1, arg_size(&a[i]) + 1);
            put_value(&a[i], tmp[i], st, col++, &bad);
        }
    }
    int more = sqlite3_step(st) == SQLITE_ROW;
    sqlite3_reset(st);
    if (!more && !bad) for (int i = 0; i < na; i++) if (tmp[i]) memcpy(p[i], tmp[i], arg_size(&a[i]));
    for (int i = 0; i < na; i++) free(tmp[i]);
    set_code(ca, more ? -811 : bad ? -305 : 0, 1);
    return 0;
}
