# SYNTHETIC SAMPLE - written for the Diocle hackathon project.
# Fictional company. Not derived from any real system, employer, or client.
"""Seeded Quillmark fixtures. Standard library only; copybooks own wire layouts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTICE = (
    'SYNTHETIC SAMPLE - written for the Diocle hackathon project.',
    'Fictional company. Not derived from any real system, employer, or client.',
)
PREAMBLE = ('\n'.join(NOTICE) + '\n').encode('ascii')
SCALES = {'small': (1000, 10000), 'medium': (50000, 1000000),
          'large': (200000, 5000000)}
SEGMENTS = ('CUSTROOT', 'ADDRSEG', 'ACCTSEG', 'CARDSEG', 'TXNSEG')
COLUMNS = {
    'PRODUCT': ('PRODUCT_ID', 'PRODUCT_NAME', 'CURRENCY'),
    'CUSTOMER': ('CUSTOMER_ID', 'DISPLAY_NAME', 'FULL_NAME', 'CUSTOMER_KIND', 'OPEN_DATE', 'STATUS'),
    'CUSTOMER_ADDRESS': ('CUSTOMER_ID', 'ADDRESS_SEQ', 'STREET', 'CITY', 'DELIVERY_NOTE'),
    'RATE_TABLE': ('PRODUCT_ID', 'EFFECTIVE_DATE', 'ANNUAL_RATE'),
    'ACCOUNT': ('ACCOUNT_NO', 'CUSTOMER_ID', 'PRODUCT_ID', 'BALANCE', 'ANNUAL_RATE', 'OPEN_DATE', 'STATUS'),
    'ACCOUNT_HOLDER': ('ACCOUNT_NO', 'CUSTOMER_ID', 'HOLDER_ROLE'),
    'PAYMENT_BATCH': ('BATCH_ID', 'BUSINESS_DATE', 'CREATED_AT', 'STATUS'),
    'TRANSACTION': ('TXN_ID', 'ACCOUNT_NO', 'POSTED_DATE', 'AMOUNT', 'TXN_TYPE', 'DETAIL'),
    'PAYMENT': ('PAYMENT_ID', 'TXN_ID', 'BATCH_ID', 'CHANNEL', 'AMOUNT'),
    'CARD': ('CARD_ID', 'ACCOUNT_NO', 'INVALID_PAN', 'EXPIRY_DATE', 'STATUS'),
    'CARD_AUTH': ('CARD_ID', 'AUTH_SEQ', 'AUTH_AT', 'AMOUNT', 'DECISION'),
    'FEE_SCHEDULE': ('PRODUCT_ID', 'FEE_CODE', 'EFFECTIVE_DATE', 'AMOUNT'),
    'GL_ACCOUNT': ('GL_CODE', 'DESCRIPTION'),
    'GL_POSTING': ('TXN_ID', 'LINE_NO', 'GL_CODE', 'AMOUNT'),
    'FRAUD_ALERT': ('ALERT_ID', 'TXN_ID', 'SEVERITY', 'REASON'),
}
MONEY_COLUMNS = {
    'ACCOUNT': ('BALANCE',), 'TRANSACTION': ('AMOUNT',), 'PAYMENT': ('AMOUNT',),
    'CARD_AUTH': ('AMOUNT',), 'FEE_SCHEDULE': ('AMOUNT',), 'GL_POSTING': ('AMOUNT',),
}
# Invented syllable words, never sampled from people, places, or external data.
GIVEN = ('Zevrill', 'Velqu', 'Orrivex', 'Talvune', 'Nesqil', 'Brevixa', 'Ulmivet', 'Qorvella')
FAMILY = ('Nimbrel', 'Vossquill', 'Orvettle', 'Quenvix', 'Drelvune', 'Sornivel', 'Wexlora', 'Yulqen')
CITIES = ('Orvettle', 'Zevrith', 'Qulvessa', 'Brennivex')
STREETS = ('Nimbrel Weftway', 'Quenvix Loomwalk', 'Vossquill Inkpath', 'Yulqen Spindleway')


def expand_pic(pic: str) -> str:
    return re.sub(r'([X9])\((\d+)\)', lambda m: m[1] * int(m[2]), pic)


def layouts() -> dict:
    """Parse our fixed-format elementary PICs and REDEFINES, using 1-based bytes."""
    result = {}
    for seg in SEGMENTS:
        fields, variants, offset, active, variant_offset = [], {}, 1, None, 0
        for raw in (ROOT / 'ims' / 'copybooks' / (seg + '.cpy')).read_text().splitlines():
            if len(raw) < 7 or raw[6] == '*':
                continue
            line = raw[7:72].strip()
            group = re.fullmatch(r'05\s+(\S+)\s+REDEFINES\s+(\S+)\.', line)
            if group:
                base = next(f for f in fields if f['name'] == group[2])
                active, variant_offset = group[1], base['offset']
                variants[active] = []
                continue
            item = re.fullmatch(r'(05|10)\s+(\S+)\s+PIC\s+(\S+?)(?:\s+(COMP-3))?\.', line)
            if not item:
                if line and not re.fullmatch(r'01\s+\S+\.', line):
                    raise ValueError(f'Unsupported copybook line: {raw}')
                continue
            level, name, pic, packed = item.groups()
            expanded = expand_pic(pic)
            digits = expanded.count('9')
            length = (digits + 2) // 2 if packed else expanded.count('X') + digits
            scale = expanded.split('V')[1].count('9') if 'V' in expanded else 0
            pos = variant_offset if level == '10' else offset
            field = dict(name=name, pic=pic, packed=bool(packed), offset=pos,
                         length=length, scale=scale, digits=digits)
            if level == '10':
                if active is None:
                    raise ValueError('Nested field without REDEFINES')
                variants[active].append(field)
                variant_offset += length
            else:
                fields.append(field)
                offset += length
        for name, variant in variants.items():
            detail = next(f for f in fields if f['name'] == 'TX-DETAIL')
            if sum(f['length'] for f in variant) != detail['length']:
                raise ValueError(f'Variant length mismatch: {name}')
        result[seg] = dict(length=offset - 1, fields=fields, variants=variants)
    return result


def encode(seg: str, values: tuple, layout: dict) -> bytes:
    fields = layout[seg]['fields']
    if len(values) != len(fields):
        raise ValueError(f'{seg}: field count mismatch')
    result = bytearray()
    for field, value in zip(fields, values):
        if field['packed']:
            number = Decimal(str(value))
            scaled = number * (10 ** field['scale'])
            if scaled != scaled.to_integral_value():
                raise ValueError(f'Fraction outside PIC: {field["name"]}')
            integer = abs(int(scaled))
            if integer >= 10 ** field['digits']:
                raise ValueError(f'PIC overflow: {field["name"]}')
            if number < 0 and not field['pic'].startswith('S'):
                raise ValueError('Negative unsigned field')
            sign = 'D' if number < 0 else ('C' if field['pic'].startswith('S') else 'F')
            nibbles = str(integer).zfill(field['digits']) + sign
            if len(nibbles) % 2:
                nibbles = '0' + nibbles
            result.extend(bytes.fromhex(nibbles))
        elif field['digits']:
            text = str(value)
            if not text.isdigit() or len(text) > field['length']:
                raise ValueError('Invalid DISPLAY numeric')
            result.extend(text.zfill(field['length']).encode('ascii'))
        else:
            text = '' if value is None else str(value)
            # Truncation is intentional only for the declared display-name mapping.
            if len(text) > field['length']:
                raise ValueError(f'Overlength {field["name"]}: {text!r}')
            result.extend(text.ljust(field['length']).encode('ascii'))
    if len(result) != layout[seg]['length']:
        raise AssertionError('Record length mismatch')
    return bytes(result)


def decode(seg: str, payload: bytes, layout: dict) -> tuple:
    if len(payload) != layout[seg]['length']:
        raise ValueError('Record length mismatch')
    values = []
    for f in layout[seg]['fields']:
        raw = payload[f['offset'] - 1:f['offset'] - 1 + f['length']]
        if f['packed']:
            nibbles = raw.hex().upper()
            sign = nibbles[-1]
            expected_signs = ('C', 'D') if f['pic'].startswith('S') else ('F',)
            if sign not in expected_signs or not nibbles[:-1].isdigit():
                raise ValueError('Invalid packed decimal')
            digits = nibbles[:-1]
            if len(digits) > f['digits'] and digits[0] != '0':
                raise ValueError('Nonzero packed padding nibble')
            number = Decimal(int(digits)).scaleb(-f['scale'])
            values.append(-number if sign == 'D' else number)
        elif f['digits']:
            if not raw.isdigit():
                raise ValueError('Invalid DISPLAY numeric')
            values.append(int(raw))
        else:
            values.append(raw.decode('ascii'))
    return tuple(values)


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        value = int(ch) * (2 if i % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


def invalid_pan(serial: int) -> str:
    stem = '000000' + f'{serial:09d}'
    valid = next(n for n in range(10) if luhn_valid(stem + str(n)))
    return stem + str((valid + 1) % 10)


def cents_text(cents: int) -> str:
    return ('-' if cents < 0 else '') + f'{abs(cents) // 100}.{abs(cents) % 100:02d}'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def json_write(path: Path, value: dict):
    # JSON cannot have comment lines: the mandatory notice is its first member.
    path.write_text(json.dumps({'_notice': NOTICE, **value}, indent=2, sort_keys=False) + '\n', encoding='ascii')


class EstateWriter:
    def __init__(self, out: Path, layout: dict):
        self.out, self.layout = out, layout
        self.tables, self.streams, self.fixed = {}, [], {}
        self.counts, self.segments = Counter(), Counter()
        for name, columns in COLUMNS.items():
            stream = (out / 'csv' / (name.lower() + '.csv')).open('w', newline='', encoding='ascii')
            stream.write(PREAMBLE.decode('ascii'))
            writer = csv.writer(stream, lineterminator='\n')
            writer.writerow(columns)
            self.tables[name] = writer
            self.streams.append(stream)
        for seg in SEGMENTS:
            stream = (out / 'fixed' / (seg.lower() + '.bin')).open('wb')
            stream.write(PREAMBLE)
            self.fixed[seg] = stream
            self.streams.append(stream)
        self.unload = (out / 'ims' / 'hierarchy.unload').open('wb')
        self.unload.write(PREAMBLE)
        self.streams.append(self.unload)

    def row(self, table: str, *values):
        self.tables[table].writerow('\\N' if v is None else str(v) for v in values)
        self.counts[table] += 1

    def segment(self, seg: str, *values):
        payload = encode(seg, values, self.layout)
        self.fixed[seg].write(payload)
        self.unload.write(seg.ljust(8).encode('ascii') + payload)
        self.segments[seg] += 1

    def close(self):
        for stream in self.streams:
            stream.close()


def generate(out: Path, seed: int, scale: str, edge_rate: Decimal):
    out = out.resolve()
    if not out.is_relative_to(ROOT.resolve()):
        raise ValueError('Output must stay inside samples/quillmark/data/')
    if out.exists() and any(out.iterdir()):
        raise ValueError(f'Output must be empty (will not overwrite): {out}')
    for folder in ('csv', 'fixed', 'ims'):
        (out / folder).mkdir(parents=True, exist_ok=True)
    n_customers, n_txns = SCALES[scale]
    rng = random.Random(seed)
    layout = layouts()
    edges = {}
    enabled = edge_rate > 0

    def mark(case: str, key: str):
        item = edges.setdefault(case, {'count': 0, 'examples': []})
        item['count'] += 1
        if len(item['examples']) < 16:
            item['examples'].append(key)

    def chance():
        return enabled and rng.random() < float(edge_rate)

    # Account snapshots are independent of transaction history. No floats for money.
    accounts = []
    by_customer = defaultdict(list)
    serial = 0
    for c in range(1, n_customers + 1):
        for j in range(2 if c % 2 else 1):
            serial += 1
            account = f'99Q{serial:07d}'
            balance = rng.randint(100, 10000000)
            status, idle = 'A', False
            if enabled:
                if serial == 1:
                    balance = 3650
                elif serial == 2:
                    balance = -3650
                elif serial == 3:
                    balance = 18250
                elif serial == 4:
                    balance = 99999999999
                elif serial == 5:
                    balance = 0
                elif serial == 6:
                    status, idle = 'D', True
                elif serial == 7:
                    idle = True
                elif chance():
                    balance = 0 if serial % 2 else -balance
                if serial > 7 and chance():
                    status, idle = 'D', True
            values = dict(serial=serial, no=account, customer=f'C{c:06d}',
                          product='QSV1' if j == 0 else 'QCK1', balance=balance,
                          status=status, idle=idle, open='2000-01-31')
            accounts.append(values)
            by_customer[c].append(values)
    active = [a for a in accounts if not a['idle']]
    quotient, remainder = divmod(n_txns, len(active))
    for index, account in enumerate(active):
        account['txn_count'] = quotient + int(index < remainder)
    w = EstateWriter(out, layout)
    balance_total, daily, daily_rows = 0, defaultdict(int), Counter()
    money_totals = {table: {col: 0 for col in cols} for table, cols in MONEY_COLUMNS.items()}
    interests = []
    dates = [(date(2001, 1, 1) + timedelta(days=i)).isoformat() for i in range(90)]
    batches = {d: f'B{i:06d}' for i, d in enumerate(['2000-02-29'] + dates, 1)}
    txn_serial, card_serial, alert_serial = 0, 0, 0
    try:
        for prod, name in (('QSV1', 'Quill Reserve'), ('QCK1', 'Weft Current')):
            w.row('PRODUCT', prod, name, 'ZZZ')
            w.row('RATE_TABLE', prod, '2000-01-01', '0.0500')
            w.row('FEE_SCHEDULE', prod, 'QF01', '2000-01-01', '2.50')
            money_totals['FEE_SCHEDULE']['AMOUNT'] += 250
        w.row('GL_ACCOUNT', 'QG01', 'Synthetic customer movement')
        w.row('GL_ACCOUNT', 'QG02', 'Synthetic offset movement')
        for day, batch in batches.items():
            w.row('PAYMENT_BATCH', batch, day, day + ' 12:00:00', 'C')
        for c in range(1, n_customers + 1):
            cid = f'C{c:06d}'
            full_name = rng.choice(GIVEN) + ' ' + rng.choice(FAMILY)
            if enabled and c in (8, 9):
                full_name = 'Velqu Nimbrel'
                mark('duplicate_looking_customers', cid)
            if enabled and c not in (8, 9) and (c == 10 or chance()):
                full_name = 'Zevrillquessa Vossquillnimbrel Orrivex'
                mark('truncated_names', cid)
            display = full_name[:24].ljust(24)
            kind, opened, cust_status = ('B' if c % 19 == 0 else 'P'), '2000-01-31', 'A'
            w.row('CUSTOMER', cid, display, full_name, kind, opened, cust_status)
            w.segment('CUSTROOT', cid, display, kind, opened, cust_status)
            missing_address = enabled and (c == 11 or (c > 11 and chance()))
            if missing_address:
                mark('missing_optional_address', cid)
            else:
                note = '' if c % 3 == 0 else ('  ' if c % 3 == 1 else None)
                street, city = rng.choice(STREETS), rng.choice(CITIES)
                w.row('CUSTOMER_ADDRESS', cid, 1, street.ljust(24), city.ljust(16), note)
                w.segment('ADDRSEG', cid, 1, street, city, note)
                if c in (1, 2, 3):
                    mark('empty_spaces_null', f'{cid}/01')
            for a in by_customer[c]:
                ano, balance = a['no'], a['balance']
                balance_total += balance
                money_totals['ACCOUNT']['BALANCE'] += balance
                w.row('ACCOUNT', ano, cid, a['product'], cents_text(balance),
                      '0.0500', a['open'], a['status'])
                w.segment('ACCTSEG', ano, cid, a['product'], cents_text(balance),
                          '0.0500', a['open'], a['status'])
                w.row('ACCOUNT_HOLDER', ano, cid, 'P')
                if a['serial'] % 10 == 0:
                    w.row('ACCOUNT_HOLDER', ano, f'C{c % n_customers + 1:06d}', 'J')
                if balance == 0:
                    mark('zero_balances', ano)
                if balance < 0:
                    mark('negative_balances', ano)
                if enabled and a['serial'] == 4:
                    mark('max_pic_balance', ano)
                if a['status'] == 'D':
                    mark('dormant_accounts', ano)
                if a['idle']:
                    mark('zero_transaction_accounts', ano)
                missing_card = enabled and (a['serial'] == 8 or (a['serial'] > 8 and chance()))
                if missing_card:
                    mark('missing_optional_card', ano)
                else:
                    card_serial += 1
                    card_id, pan = f'K{card_serial:07d}', invalid_pan(card_serial)
                    w.row('CARD', card_id, ano, pan, '2004-02-29', 'A')
                    w.segment('CARDSEG', card_id, ano, pan, '2004-02-29', 'A')
                    w.row('CARD_AUTH', card_id, 1, '2001-01-31 12:00:00', '1.25', 'A')
                    money_totals['CARD_AUTH']['AMOUNT'] += 125
                for local_txn in range(a.get('txn_count', 0)):
                    txn_serial += 1
                    tid = f'T{txn_serial:08d}'
                    day = rng.choice(dates)
                    amount = rng.randint(-250000, 250000)
                    variant = 'F' if txn_serial % 5 == 0 else 'P'
                    detail = 'QF01' + ' ' * 8 if variant == 'F' else (
                        ('-' if amount < 0 else '+') + 'SIM' + f'R{txn_serial:07d}')
                    if variant == 'F':
                        amount = -250
                    if enabled and a['serial'] <= 3 and local_txn == 0:
                        variant, day, detail = 'I', '2000-02-29', '001R' + ' ' * 8
                        raw_interest = Decimal(cents_text(balance)) * Decimal('0.0500') / Decimal(365)
                        rounded = raw_interest.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                        half_even = raw_interest.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)
                        amount = int(rounded * 100)
                        interests.append(dict(txn_id=tid, account_no=ano, principal=cents_text(balance),
                                              annual_rate='0.0500', days=1, divisor=365,
                                              exact=str(raw_interest), cobol_rounded=str(rounded),
                                              half_even=str(half_even)))
                        mark('half_cent_interest', tid)
                        mark('leap_day', tid)
                    elif enabled and a['serial'] in (4, 5) and local_txn == 0:
                        amount = 999999999 if a['serial'] == 4 else -999999999
                        variant, day = 'P', '2001-01-31'
                        detail = ('+' if amount > 0 else '-') + 'SIM' + f'R{txn_serial:07d}'
                        mark('max_pic_transaction', tid)
                    if day.endswith(('-01-31', '-02-28', '-03-31')):
                        mark('month_end', tid)
                    mark('variant_' + variant, tid)
                    w.row('TRANSACTION', tid, ano, day, cents_text(amount), variant, detail)
                    w.segment('TXNSEG', tid, ano, day, cents_text(amount), variant, detail)
                    daily[day] += amount
                    daily_rows[day] += 1
                    money_totals['TRANSACTION']['AMOUNT'] += amount
                    if variant == 'P':
                        w.row('PAYMENT', f'P{txn_serial:08d}', tid, batches[day], 'SIM', cents_text(amount))
                        money_totals['PAYMENT']['AMOUNT'] += amount
                    w.row('GL_POSTING', tid, 1, 'QG01', cents_text(amount))
                    w.row('GL_POSTING', tid, 2, 'QG02', cents_text(-amount))
                    if enabled and (txn_serial == 1 or chance()):
                        alert_serial += 1
                        w.row('FRAUD_ALERT', f'F{alert_serial:08d}', tid, 2, 'Invented fixture condition')
    finally:
        w.close()
    assert txn_serial == n_txns
    rejects = {}
    if enabled:
        orphan = encode('ACCTSEG', ('99Q9999999', 'C999999', 'QSV1', '0.00',
                                     '0.0500', '2000-02-29', 'A'), layout)
        (out / 'fixed' / 'orphan_acctseg.bin').write_bytes(PREAMBLE + orphan)
        (out / 'ims' / 'orphan.unload').write_bytes(PREAMBLE + b'ACCTSEG ' + orphan)
        mark('orphan_child_quarantined', '99Q9999999 -> C999999')
        rejects = {'ACCTSEG': 1}
    load = ['-- ' + n for n in NOTICE] + [
        '', '-- Run from this output directory: psql -v ON_ERROR_STOP=1 -f load.postgres.sql',
        '-- Create the empty schema first using db2/schema.postgres.sql.',
        '-- Each CSV has exactly two synthetic notice lines before its column header.',
        '\\set ON_ERROR_STOP on', 'BEGIN;',
    ]
    for table, cols in COLUMNS.items():
        sqltable = '"TRANSACTION"' if table == 'TRANSACTION' else table.lower()
        # Client-side COPY FROM PROGRAM lets psql skip notices without modifying CSVs.
        load.append("\\copy " + sqltable + " (" + ','.join(c.lower() for c in cols) +
                    ") FROM PROGRAM 'tail -n +3 csv/" + table.lower() +
                    ".csv' WITH (FORMAT csv, HEADER true, NULL '\\N')")
    load.extend(['COMMIT;', ''])
    (out / 'load.postgres.sql').write_text('\n'.join(load), encoding='ascii')
    manifest = dict(company='Quillmark Trust & Savings (fictional)', format_version=1,
                    seed=seed, scale=scale, edge_rate=str(edge_rate),
                    row_counts={t: w.counts[t] for t in COLUMNS},
                    segment_counts={s: w.segments[s] for s in SEGMENTS},
                    quarantined_segment_counts=rejects,
                    segment_lengths={s: layout[s]['length'] for s in SEGMENTS},
                    controls={'balance_sum': cents_text(balance_total),
                              'transaction_amount_by_day': {
                                  d: {'rows': daily_rows[d], 'sum': cents_text(daily[d])} for d in sorted(daily)},
                              'money_totals': {t: {c: cents_text(v) for c, v in cols.items()}
                                               for t, cols in money_totals.items()},
                              'interest_rounding': interests}, edge_cases=edges)
    manifest['sha256'] = {str(path.relative_to(out)): sha256(path)
                          for path in sorted(out.rglob('*')) if path.is_file()}
    json_write(out / 'manifest.json', manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=20261028)
    parser.add_argument('--scale', choices=SCALES, default='small')
    parser.add_argument('--edge-rate', type=Decimal, default=Decimal('0.02'))
    parser.add_argument('--out', type=Path, help='Empty directory; default data/out/SCALE')
    args = parser.parse_args()
    if not args.edge_rate.is_finite() or not 0 <= args.edge_rate <= 1:
        parser.error('--edge-rate must be a finite decimal between 0 and 1')
    result = generate(args.out or ROOT / 'out' / args.scale, args.seed, args.scale, args.edge_rate)
    print(json.dumps({'scale': args.scale, 'seed': args.seed, 'rows': result['row_counts']}))


if __name__ == '__main__':
    main()
