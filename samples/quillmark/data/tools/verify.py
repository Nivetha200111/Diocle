# SYNTHETIC SAMPLE - written for the Diocle hackathon project.
# Fictional company. Not derived from any real system, employer, or client.
"""Check actual files, hierarchy, PII patterns, SQLite loads, and GnuCOBOL wire bytes."""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN
from pathlib import Path

from generate import (ROOT, NOTICE, PREAMBLE, SEGMENTS, COLUMNS, MONEY_COLUMNS,
                      layouts, decode, encode, luhn_valid, sha256, json_write)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rows(out, table):
    with (out / 'csv' / (table.lower() + '.csv')).open(encoding='ascii', newline='') as stream:
        require(stream.readline() + stream.readline() == PREAMBLE.decode('ascii'), 'CSV notice')
        reader = csv.DictReader(stream)
        require(tuple(reader.fieldnames) == COLUMNS[table], 'CSV columns: ' + table)
        for row in reader:
            require(None not in row and None not in row.values(), 'CSV column count')
            yield {k: None if v == '\\N' else v for k, v in row.items()}


def binary_records(path, length):
    with path.open('rb') as stream:
        require(stream.read(len(PREAMBLE)) == PREAMBLE, f'Binary notice: {path}')
        while payload := stream.read(length):
            require(len(payload) == length, f'Truncated record: {path}')
            yield payload


def projection(seg, row):
    columns = {
        'CUSTROOT': ('CUSTOMER_ID', 'DISPLAY_NAME', 'CUSTOMER_KIND', 'OPEN_DATE', 'STATUS'),
        'ADDRSEG': COLUMNS['CUSTOMER_ADDRESS'], 'ACCTSEG': COLUMNS['ACCOUNT'],
        'CARDSEG': COLUMNS['CARD'], 'TXNSEG': COLUMNS['TRANSACTION'],
    }
    return tuple(row[c] for c in columns[seg])


def check_fixed(out, manifest, layout):
    tables = dict(CUSTROOT='CUSTOMER', ADDRSEG='CUSTOMER_ADDRESS', ACCTSEG='ACCOUNT',
                  CARDSEG='CARD', TXNSEG='TRANSACTION')
    counts = {}
    for seg in SEGMENTS:
        count = 0
        records = binary_records(out / 'fixed' / (seg.lower() + '.bin'), layout[seg]['length'])
        for payload, row in itertools.zip_longest(records, rows(out, tables[seg])):
            require(payload is not None and row is not None, f'CSV/fixed row count: {seg}')
            actual = decode(seg, payload, layout)
            expected = projection(seg, row)
            for field, value, source in zip(layout[seg]['fields'], actual, expected):
                if field['packed']:
                    require(value == Decimal(source), f'Money/rate mismatch: {seg} {count}')
                elif field['digits']:
                    require(value == int(source), f'DISPLAY mismatch: {seg} {count}')
                else:
                    require(value == (source or '').ljust(field['length']), f'Text mismatch: {seg} {count}')
            if seg == 'TXNSEG':
                variant, detail = actual[-2:]
                if variant == 'P':
                    require(detail[0] in '+-' and detail[1:4] == 'SIM' and detail[4] == 'R', 'Payment variant')
                    require(detail[0] == ('-' if actual[3] < 0 else '+'), 'Payment direction')
                elif variant == 'F':
                    require(detail == 'QF01' + ' ' * 8 and actual[3] == Decimal('-2.50'), 'Fee variant')
                else:
                    require(variant == 'I' and detail == '001R' + ' ' * 8, 'Interest variant')
            count += 1
        require(count == manifest['segment_counts'][seg], 'Segment manifest count: ' + seg)
        counts[seg] = count
    return counts


def check_unload(out, manifest, layout):
    counts, root, account = Counter(), None, None
    streams = {s: iter(binary_records(out / 'fixed' / (s.lower() + '.bin'), layout[s]['length']))
               for s in SEGMENTS}
    with (out / 'ims' / 'hierarchy.unload').open('rb') as stream:
        require(stream.read(len(PREAMBLE)) == PREAMBLE, 'Unload notice')
        while prefix := stream.read(8):
            require(len(prefix) == 8, 'Unload prefix length')
            seg = prefix.decode('ascii').rstrip()
            require(seg in SEGMENTS, 'Unknown segment')
            payload = stream.read(layout[seg]['length'])
            require(payload == next(streams[seg], None), 'Unload/extract byte mismatch')
            value = decode(seg, payload, layout)
            if seg == 'CUSTROOT':
                root, account = value[0], None
            elif seg == 'ADDRSEG':
                require(root is not None and account is None and value[0] == root, 'Address parent/order')
            elif seg == 'ACCTSEG':
                require(root is not None and value[1] == root, 'Account parent/order')
                account = value[0]
            elif seg == 'CARDSEG':
                require(account is not None and value[1] == account, 'Card parent/order')
            else:
                require(account is not None and value[1] == account, 'Transaction parent/order')
            counts[seg] += 1
    require(dict(counts) == manifest['segment_counts'], 'Unload counts')
    require(all(next(it, None) is None for it in streams.values()), 'Unload missing records')
    for seg, expected in manifest['quarantined_segment_counts'].items():
        records = list(binary_records(out / 'fixed' / 'orphan_acctseg.bin', layout[seg]['length']))
        require(len(records) == expected == 1, 'Orphan count')
        value = decode(seg, records[0], layout)
        require(value[:2] == ('99Q9999999', 'C999999'), 'Orphan keys')
        require((out / 'ims' / 'orphan.unload').read_bytes() == PREAMBLE + b'ACCTSEG ' + records[0], 'Orphan unload')
    return dict(counts)


def check_patterns(out):
    # Scan raw byte chunks with overlap, including packed files, to catch ASCII PANs.
    patterns = {
        'email': re.compile(rb'[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}'),
        'url': re.compile(rb'(?i)(?:https?://|ftp://|www\.)'),
        'phone': re.compile(rb'(?<![A-Za-z0-9])(?:\+\d[\d -]{9,18}\d|\(\d{3}\)[ -]?\d{3}[ -]\d{4}|\d{3}[ -]\d{3}[ -]\d{4}|\d{10,15})(?![A-Za-z0-9]|\.\d)'),
    }
    candidates = re.compile(rb'(?<!\d)\d{16}(?!\d)')
    pan_count = 0
    for path in sorted(out.rglob('*')):
        if not path.is_file():
            continue
        with path.open('rb') as stream:
            # Both sides of each chunk have real file context. A regex must never
            # interpret an artificial chunk boundary as the end/start of a token.
            # 512 exceeds the longest bounded pattern plus lookaround context.
            before = b''
            chunk = stream.read(1024 * 1024)
            while chunk:
                following = stream.read(1024 * 1024)
                block = before + chunk + following[:512]
                start, end = len(before), len(before) + len(chunk)
                for label, pattern in patterns.items():
                    if label == 'email' and b'@' not in block:
                        continue
                    for match in pattern.finditer(block):
                        if start <= match.start() < end:
                            raise ValueError(f'{label} pattern: {path}')
                for candidate in candidates.finditer(block):
                    if start <= candidate.start() < end:
                        require(not luhn_valid(candidate[0].decode('ascii')), f'Luhn-valid number: {path}')
                        pan_count += 1
                before = (before + chunk)[-512:]
                chunk = following
    # Structured validation also covers every card and enforces the unissued prefix.
    cards = 0
    for row in rows(out, 'CARD'):
        pan = row['INVALID_PAN']
        require(len(pan) == 16 and pan.isdigit() and pan.startswith('000000')
                and not luhn_valid(pan), 'Card invariant')
        cards += 1
    for row in rows(out, 'ACCOUNT'):
        require(re.fullmatch(r'99Q\d{7}', row['ACCOUNT_NO']) is not None, 'Account invariant')
    return dict(luhn_valid=0, email=0, phone=0, url=0, cards_checked=cards,
                ascii_pan_tokens_checked=pan_count)


def cents(value):
    amount = Decimal(str(value)) * 100
    require(amount == amount.to_integral_value(), 'Non-cent monetary amount')
    return int(amount)


def check_sqlite(out, manifest):
    # SQLite NUMERIC uses binary floats; all aggregate checks explicitly sum integer cents.
    db = sqlite3.connect(':memory:')
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript((ROOT / 'db2' / 'schema.postgres.sql').read_text())
    counts = {}
    for table, columns in COLUMNS.items():
        sql = f'INSERT INTO "{table}" VALUES ({",".join("?" for _ in columns)})'
        db.executemany(sql, (tuple(row[c] for c in columns) for row in rows(out, table)))
        counts[table] = db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    require(counts == manifest['row_counts'], 'Loaded table counts')
    require(not db.execute('PRAGMA foreign_key_check').fetchall(), 'Foreign key check')
    totals = {}
    for table, columns in MONEY_COLUMNS.items():
        totals[table] = {}
        for col in columns:
            # Verify SQLite's stored values still represent the exact source cents.
            actual_values = db.execute(f'SELECT "{col}" FROM "{table}"')
            exact_sum = sum(cents(value[0]) for value in actual_values)
            sql_sum = db.execute(f'SELECT COALESCE(SUM(CAST(ROUND("{col}" * 100) AS INTEGER)),0) FROM "{table}"').fetchone()[0]
            expected = cents(manifest['controls']['money_totals'][table][col])
            require(exact_sum == sql_sum == expected, f'Loaded total: {table}.{col}')
            totals[table][col] = sql_sum
    require(totals['ACCOUNT']['BALANCE'] == cents(manifest['controls']['balance_sum']), 'Balance control')
    days = db.execute('SELECT POSTED_DATE, COUNT(*), SUM(CAST(ROUND(AMOUNT * 100) AS INTEGER)) FROM "TRANSACTION" GROUP BY POSTED_DATE').fetchall()
    expected_days = manifest['controls']['transaction_amount_by_day']
    require(set(d[0] for d in days) == set(expected_days), 'Daily key set')
    for day, count, total in days:
        expected = expected_days[day]
        require(count == expected['rows'] and total == cents(expected['sum']), 'Daily control: ' + day)
    require(db.execute('SELECT COUNT(*) FROM (SELECT TXN_ID FROM GL_POSTING GROUP BY TXN_ID HAVING COUNT(*) != 2 OR SUM(CAST(ROUND(AMOUNT*100) AS INTEGER)) != 0)').fetchone()[0] == 0, 'GL pairing')
    require(db.execute('SELECT COUNT(*) FROM PAYMENT p JOIN "TRANSACTION" t ON t.TXN_ID=p.TXN_ID WHERE t.TXN_TYPE != \'P\' OR p.AMOUNT != t.AMOUNT').fetchone()[0] == 0, 'Payment linkage')
    require(db.execute('SELECT COUNT(*) FROM "TRANSACTION" WHERE TXN_TYPE=\'P\'').fetchone()[0] == counts['PAYMENT'], 'Payment coverage')
    if manifest['quarantined_segment_counts']:
        require(db.execute("SELECT COUNT(*) FROM CUSTOMER WHERE CUSTOMER_ID='C999999'").fetchone()[0] == 0, 'Orphan parent unexpectedly exists')
        try:
            db.execute("INSERT INTO ACCOUNT VALUES ('99Q9999999','C999999','QSV1',0,.05,'2000-02-29','A')")
        except sqlite3.IntegrityError:
            orphan_rejected = True
        else:
            raise ValueError('SQLite accepted orphan')
    else:
        orphan_rejected = None
    fixture = manifest['controls']['interest_rounding']
    for item in fixture:
        raw = Decimal(item['principal']) * Decimal(item['annual_rate']) * item['days'] / item['divisor']
        require(raw == Decimal(item['exact']), 'Raw interest inputs')
        require(raw.quantize(Decimal('.01'), rounding=ROUND_HALF_UP) == Decimal(item['cobol_rounded']), 'Rounded interest inputs')
        require(raw.quantize(Decimal('.01'), rounding=ROUND_HALF_EVEN) == Decimal(item['half_even']), 'Half-even interest inputs')
        posted = db.execute('SELECT ACCOUNT_NO, POSTED_DATE, AMOUNT, TXN_TYPE FROM "TRANSACTION" WHERE TXN_ID=?', (item['txn_id'],)).fetchone()
        require(posted[:2] == (item['account_no'], '2000-02-29') and cents(posted[2]) == cents(item['cobol_rounded']) and posted[3] == 'I', 'Posted interest fixture')
        principal = db.execute('SELECT BALANCE FROM ACCOUNT WHERE ACCOUNT_NO=?', (item['account_no'],)).fetchone()[0]
        require(cents(principal) == cents(item['principal']), 'Interest account principal')
    if fixture:
        require(sum(Decimal(x['cobol_rounded']) for x in fixture) == Decimal('0.03'), 'COBOL day total')
        require(sum(Decimal(x['half_even']) for x in fixture) == Decimal('0.02'), 'Half-even day expectation')
        # The third tie also makes half-even fail the whole-day control.
        require(any(x['cobol_rounded'] != x['half_even'] for x in fixture), 'No rounding difference')
    edge_checks = []
    if Decimal(manifest['edge_rate']) > 0:
        require(db.execute("SELECT BALANCE FROM ACCOUNT WHERE ACCOUNT_NO='99Q0000005'").fetchone()[0] == 0, 'Zero balance fixture')
        require(cents(db.execute("SELECT BALANCE FROM ACCOUNT WHERE ACCOUNT_NO='99Q0000002'").fetchone()[0]) == -3650, 'Negative balance fixture')
        require(cents(db.execute("SELECT BALANCE FROM ACCOUNT WHERE ACCOUNT_NO='99Q0000004'").fetchone()[0]) == 99999999999, 'Max balance fixture')
        require(db.execute("SELECT STATUS FROM ACCOUNT WHERE ACCOUNT_NO='99Q0000006'").fetchone()[0] == 'D', 'Dormant fixture')
        for key in ('99Q0000006', '99Q0000007'):
            require(db.execute('SELECT COUNT(*) FROM "TRANSACTION" WHERE ACCOUNT_NO=?', (key,)).fetchone()[0] == 0, 'Empty account fixture')
        duplicate = db.execute("SELECT FULL_NAME, DISPLAY_NAME FROM CUSTOMER WHERE CUSTOMER_ID IN ('C000008','C000009') ORDER BY CUSTOMER_ID").fetchall()
        require(len(duplicate) == 2 and duplicate[0] == duplicate[1], 'Duplicate-looking fixture')
        full, display = db.execute("SELECT FULL_NAME, DISPLAY_NAME FROM CUSTOMER WHERE CUSTOMER_ID='C000010'").fetchone()
        require(len(full) > 24 and display == full[:24], 'Truncation fixture')
        note_rows = db.execute("SELECT DELIVERY_NOTE FROM CUSTOMER_ADDRESS WHERE CUSTOMER_ID IN ('C000001','C000002','C000003') ORDER BY CUSTOMER_ID").fetchall()
        require(note_rows == [('  ',), (None,), ('',)], 'Spaces / NULL / empty fixture')
        require(db.execute("SELECT COUNT(*) FROM CUSTOMER_ADDRESS WHERE CUSTOMER_ID='C000011'").fetchone()[0] == 0, 'Missing address fixture')
        require(db.execute("SELECT COUNT(*) FROM CARD WHERE ACCOUNT_NO='99Q0000008'").fetchone()[0] == 0, 'Missing card fixture')
        extrema = db.execute('SELECT MIN(AMOUNT), MAX(AMOUNT) FROM "TRANSACTION"').fetchone()
        require(tuple(map(cents, extrema)) == (-999999999, 999999999), 'Max signed transaction fixtures')
        require(expected_days['2000-02-29'] == {'rows': 3, 'sum': '0.03'}, 'Rounding day control')
        edge_checks = ['zero/negative/max balances', 'signed transaction maxima', 'dormant/empty accounts',
                       'duplicate-looking customers', 'truncated names', 'spaces/NULL/empty',
                       'missing optional segments', 'interest rounding day']
    db.close()
    return dict(engine='SQLite', postgres_executed=False, counts=counts,
                money_totals_cents=totals, days_checked=len(days), orphan_rejected=orphan_rejected, edge_checks=edge_checks)


def check_cobol(layout):
    compiler = shutil.which('cobc')
    if not compiler:
        return {'status': 'not run', 'reason': 'cobc unavailable'}
    work = ROOT / '.work'
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cobol-', dir=work) as folder:
        folder = Path(folder)
        program = ['      * ' + n for n in NOTICE] + [
            '       identification division.', '       program-id. wirecheck.',
            '       environment division.', '       configuration section.',
            '       repository. function all intrinsic.',
            '       data division.', '       working-storage section.',
        ] + [f'           copy "{s}.cpy".' for s in SEGMENTS] + [
            '       01 RAW-INTEREST PIC S9(7)V9(5) COMP-3.',
            '       procedure division.',
        ] + [f'           display length of {s}-REC' for s in SEGMENTS]
        for principal in ('36.50', '-36.50', '182.50'):
            program += [
                '           initialize TXNSEG-REC',
                '           move "T00000001" to TX-TXN-ID',
                '           move "99Q0000001" to TX-ACCOUNT-NO',
                '           move "2000-02-29" to TX-POSTED-DATE',
                '           move "I" to TX-TYPE',
                '           move "001R        " to TX-DETAIL',
                f'           move {principal} to AC-BALANCE',
                '           move 0.0500 to AC-RATE',
                '           compute RAW-INTEREST =',
                '               AC-BALANCE * AC-RATE / 365',
                '           compute TX-AMOUNT rounded = RAW-INTEREST',
                '           display TXNSEG-REC with no advancing',
            ]
        # Independently exercise packed balance/rate signs, maxima and unsigned F.
        balances = ('0.00', '999999999.99', '-999999999.99')
        for amount in balances:
            program += [
                '           initialize ACCTSEG-REC',
                '           move "99Q0000001" to AC-ACCOUNT-NO',
                '           move "C000001" to AC-CUSTOMER-ID',
                '           move "QSV1" to AC-PRODUCT-ID',
                f'           move {amount} to AC-BALANCE',
                '           move 0.0500 to AC-RATE',
                '           move "2000-01-31" to AC-OPEN-DATE',
                '           move "A" to AC-STATUS',
                '           display ACCTSEG-REC with no advancing',
            ]
        for amount in ('9999999.99', '-9999999.99'):
            program += [f'           move {amount} to TX-AMOUNT',
                        '           display TXNSEG-REC with no advancing']
        program += ['           goback.', '']
        source = folder / 'wirecheck.cbl'
        source.write_text('\n'.join(program), encoding='ascii')
        executable = folder / 'wirecheck'
        subprocess.run([compiler, '-x', '-fixed', '-I', str(ROOT / 'ims' / 'copybooks'),
                        '-o', str(executable), str(source)], check=True, capture_output=True)
        output = subprocess.run([str(executable)], check=True, capture_output=True).stdout
        lines = output.split(b'\n', len(SEGMENTS))
        lengths = [int(x) for x in lines[:-1]]
        require(lengths == [layout[s]['length'] for s in SEGMENTS], 'GnuCOBOL lengths')
        expected = b''.join(encode('TXNSEG', ('T00000001', '99Q0000001', '2000-02-29',
                                            a, 'I', '001R        '), layout)
                            for a in ('0.01', '-0.01', '0.03'))
        expected += b''.join(encode('ACCTSEG', ('99Q0000001', 'C000001', 'QSV1',
                                              a, '0.0500', '2000-01-31', 'A'), layout)
                             for a in balances)
        expected += b''.join(encode('TXNSEG', ('T00000001', '99Q0000001', '2000-02-29',
                                              a, 'I', '001R        '), layout)
                             for a in ('9999999.99', '-9999999.99'))
        require(lines[-1] == expected, 'GnuCOBOL packed bytes / rounded values')
        version = subprocess.run([compiler, '-V'], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    return dict(status='passed', compiler=version, lengths=lengths,
                rounded_values=['0.01', '-0.01', '0.03'], wire_bytes_match=True, signed_maxima_and_unsigned_rate=True)


def verify(out, files_only=False):
    manifest = json.loads((out / 'manifest.json').read_text())
    require(manifest['_notice'] == list(NOTICE), 'Manifest notice')
    for name, digest in manifest['sha256'].items():
        require(sha256(out / name) == digest, 'Checksum mismatch: ' + name)
    actual = {str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()} - {'manifest.json'}
    require(actual == set(manifest['sha256']), 'Unmanifested or missing output file')
    layout = layouts()
    require(manifest['segment_lengths'] == {s: layout[s]['length'] for s in SEGMENTS}, 'Layout lengths')
    result = dict(scale=manifest['scale'], seed=manifest['seed'], checksums='passed',
                  fixed_counts=check_fixed(out, manifest, layout),
                  hierarchy_counts=check_unload(out, manifest, layout),
                  patterns=check_patterns(out))
    result['database'] = {'status': 'not run (files-only)'} if files_only else check_sqlite(out, manifest)
    result['cobol'] = check_cobol(layout)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--files-only', action='store_true')
    parser.add_argument('--report', type=Path, help='Write outside dataset to preserve its checksum set')
    args = parser.parse_args()
    if args.report and args.report.resolve().is_relative_to(args.out.resolve()):
        parser.error('--report must be outside the dataset')
    result = verify(args.out, args.files_only)
    if args.report:
        json_write(args.report, result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
