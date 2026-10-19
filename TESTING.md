# Test evidence / Test kanıtı

Verified local run: 19 October 2026 UTC, Linux 7.2.11-1-cachyos x86_64 / glibc 2.44, CPython 3.14.8.

| Suite | Passed | Skipped | Failures | Errors |
| --- | ---: | ---: | ---: | ---: |
| Development | 20 | 0 | 0 | 0 |
| Independent | 7 | 0 | 0 | 0 |

Commands, from the repository root:

    python3 -B ci/run_tests.py --suite development
    python3 -B ci/run_tests.py --suite independent

The production source and both original synthetic test files are unchanged.
SHA256 identities:

| File | SHA256 |
| --- | --- |
| backup_compare.py | 9c00d29fd61136195163257cfc2f65e250c2595e6f254c56c2cc797c45fc6620 |
| test_backup_compare.py | fb694fd5e5aa68de747d20372b964d46e9084343103c0d6581da7e899fbc4988 |
| review/test_review.py | 3f325cdfa5cdd41fb4f4e03c81019ed417a3911b90807837fdf59744d2cedffe |

Fixtures use only temporary synthetic directories. Coverage includes categories, empty directories, chunked hashing, unreadability, symlinks, observable changes, exit codes and content/mtime/mode preservation. These tests do not prove every race impossible.

Windows, macOS and Python 3.9 were not run. No CI/platform pass, restoration guarantee or certification is claimed. The optional workflow is manual-only and was not dispatched. Quota/cost conditions remain unverified. Skipped tests must not be counted as full platform success.

An earlier reviewed Linux run (7.2.9-2-cachyos / Python 3.14.8, 16 October UTC) also passed 20+7; the table above is the fresh 19 October run.

Ham yerel log, kişisel dosya yolu, takip CSV'si, çalışma raporu veya oturum verisi bu depoya eklenmedi.
