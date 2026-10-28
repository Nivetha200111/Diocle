# SYNTHETIC SAMPLE - written for the Diocle hackathon project.
# Fictional company. Not derived from any real system, employer, or client.
"""Generate twice per scale, compare all bytes, then verify actual fixtures."""
from __future__ import annotations

import argparse
import hashlib
import tempfile
from decimal import Decimal
from pathlib import Path

from generate import ROOT, generate, sha256, json_write
from verify import require, verify


def checksums(folder):
    return {str(p.relative_to(folder)): sha256(p) for p in sorted(folder.rglob('*')) if p.is_file()}


def tree_hash(sums):
    return hashlib.sha256(''.join(k + '\0' + v + '\n' for k, v in sorted(sums.items())).encode('ascii')).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=20261028)
    parser.add_argument('--scales', nargs='+', choices=('small', 'medium', 'large'), default=('small', 'medium'))
    parser.add_argument('--report', type=Path, default=ROOT / 'verification.json')
    args = parser.parse_args()
    report_path = args.report.resolve()
    require(report_path.is_relative_to(ROOT.resolve()), 'Report must stay inside data/')
    work = ROOT / '.work'
    work.mkdir(exist_ok=True)
    result = {'seed': args.seed, 'edge_rate': '0.02', 'repeatability': {}, 'verified': {},
              'limitations': ['PostgreSQL and DB2 servers were not executed.',
                              'Only small CSVs were loaded into SQLite.',
                              'Large was not generated unless explicitly requested.']}
    for scale in args.scales:
        with tempfile.TemporaryDirectory(prefix='repeat-' + scale + '-', dir=work) as temp:
            folder = Path(temp)
            print(f'{scale}: generate first output', flush=True)
            generate(folder / 'first', args.seed, scale, Decimal('0.02'))
            print(f'{scale}: generate second output', flush=True)
            generate(folder / 'second', args.seed, scale, Decimal('0.02'))
            first, second = checksums(folder / 'first'), checksums(folder / 'second')
            require(first == second, f'{scale}: repeated output checksums differ')
            result['repeatability'][scale] = dict(files=len(first), identical=True,
                                                   first_tree_sha256=tree_hash(first),
                                                   second_tree_sha256=tree_hash(second))
            if scale == 'small':
                committed = ROOT / 'out' / 'small'
                require(first == checksums(committed), 'Checked-in small differs from fresh generation')
                result['repeatability'][scale]['checked_in_small_identical'] = True
            print(f'{scale}: identical checksums; verify fixed bytes, hierarchy and patterns', flush=True)
            result['verified'][scale] = verify(folder / 'first', files_only=(scale != 'small'))
            print(f'{scale}: verification passed', flush=True)
    # Boundary rates must preserve record counts and mandatory anchor semantics.
    result['boundary_rates'] = {}
    for rate in ('0', '1'):
        with tempfile.TemporaryDirectory(prefix='rate-' + rate + '-', dir=work) as temp:
            folder = Path(temp) / 'dataset'
            print(f'small: verify edge-rate {rate}', flush=True)
            manifest = generate(folder, args.seed, 'small', Decimal(rate))
            checked = verify(folder)
            result['boundary_rates'][rate] = {
                'customer_rows': manifest['row_counts']['CUSTOMER'],
                'transaction_rows': manifest['row_counts']['TRANSACTION'],
                'checksums_fixed_hierarchy_patterns_sqlite': 'passed',
                'cobol': checked['cobol']['status'],
            }
    result['committed_small_bytes'] = sum(p.stat().st_size for p in (ROOT / 'out' / 'small').rglob('*') if p.is_file())
    require(result['committed_small_bytes'] < 5_000_000, 'Small output exceeds 5 MB')
    json_write(report_path, result)
    print(f'Wrote {report_path}', flush=True)


if __name__ == '__main__':
    main()
