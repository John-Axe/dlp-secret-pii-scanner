"""Property-based tests for the detectors module's pure validation/scoring
logic: the Luhn credit-card validator, the SSN validator, and Shannon
entropy. Complements test_detectors.py's hand-picked examples with
generated inputs - these three functions are exactly the kind of small,
well-defined-invariant pure functions Hypothesis is good at, and they're
security-relevant: a false negative here means a real credit card or SSN
silently passes through undetected, not just a missed test case.
"""

from __future__ import annotations

import math

from hypothesis import example, given
from hypothesis import strategies as st

from dlp import detectors

_DIGIT = st.integers(min_value=0, max_value=9)


def _fires(rule_id: str, line: str) -> bool:
    """Same helper as test_detectors.py - duplicated rather than imported so
    this file stays independently runnable/readable, matching the existing
    one-test-file-per-concern convention."""
    det = detectors.REGEX_DETECTORS_BY_ID[rule_id]
    return bool(det.scan_line(line))


def _luhn_checksum(digits: list[int]) -> int:
    """Mirrors detectors._luhn_ok's exact doubling logic, used here in
    reverse to construct valid numbers rather than to validate them."""
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10


def _with_luhn_check_digit(prefix: list[int]) -> list[int]:
    """Appends the check digit that makes prefix + [check_digit] Luhn-valid."""
    checksum_with_placeholder = _luhn_checksum([*prefix, 0])
    check_digit = (10 - checksum_with_placeholder) % 10
    return [*prefix, check_digit]


@st.composite
def _valid_luhn_digit_strings(draw: st.DrawFn) -> str:
    length = draw(st.integers(min_value=12, max_value=18))  # +1 check digit = 13-19
    prefix = draw(st.lists(_DIGIT, min_size=length, max_size=length))
    return "".join(str(d) for d in _with_luhn_check_digit(prefix))


@given(_valid_luhn_digit_strings())
@example("4111111111111111")  # a well-known Luhn-valid test number
def test_luhn_accepts_any_constructed_valid_number(card_number: str):
    assert detectors._luhn_ok(card_number, None)  # type: ignore[arg-type]


@given(_valid_luhn_digit_strings(), st.integers(min_value=0, max_value=18))
def test_luhn_rejects_any_single_digit_corruption(card_number: str, position: int):
    """Luhn's entire purpose is catching single-digit transcription errors -
    changing any one digit must never coincidentally produce another valid
    number, since a single-digit change can never shift the weighted sum by
    a multiple of 10."""
    position = position % len(card_number)
    original_digit = int(card_number[position])
    corrupted_digit = (original_digit + 1) % 10  # always different, never wraps to same value
    corrupted = card_number[:position] + str(corrupted_digit) + card_number[position + 1 :]

    assert not detectors._luhn_ok(corrupted, None)  # type: ignore[arg-type]


@given(st.text(alphabet="0123456789", min_size=0, max_size=40))
def test_luhn_rejects_any_length_outside_13_to_19(digits: str):
    if 13 <= len(digits) <= 19:
        return  # length alone doesn't guarantee validity - not this test's concern
    assert not detectors._luhn_ok(digits, None)  # type: ignore[arg-type]


def _ssn_parts(area: int, group: int, serial: int) -> tuple[str, str, str]:
    return f"{area:03d}", f"{group:02d}", f"{serial:04d}"


@given(
    area=st.integers(min_value=1, max_value=898).filter(lambda a: a != 666),
    group=st.integers(min_value=1, max_value=99),
    serial=st.integers(min_value=1, max_value=9999),
)
def test_ssn_accepts_any_structurally_valid_number(area: int, group: int, serial: int):
    a, g, s = _ssn_parts(area, group, serial)
    assert _fires("us_ssn", f"SSN: {a}-{g}-{s}")


@given(group=st.integers(min_value=1, max_value=99), serial=st.integers(min_value=1, max_value=9999))
def test_ssn_rejects_area_000(group: int, serial: int):
    g, s = f"{group:02d}", f"{serial:04d}"
    assert not _fires("us_ssn", f"SSN: 000-{g}-{s}")


@given(group=st.integers(min_value=1, max_value=99), serial=st.integers(min_value=1, max_value=9999))
def test_ssn_rejects_area_666(group: int, serial: int):
    g, s = f"{group:02d}", f"{serial:04d}"
    assert not _fires("us_ssn", f"SSN: 666-{g}-{s}")


@given(
    area=st.integers(min_value=900, max_value=999),
    group=st.integers(min_value=1, max_value=99),
    serial=st.integers(min_value=1, max_value=9999),
)
def test_ssn_rejects_area_9xx(area: int, group: int, serial: int):
    a, g, s = _ssn_parts(area, group, serial)
    assert not _fires("us_ssn", f"SSN: {a}-{g}-{s}")


@given(area=st.integers(min_value=1, max_value=898).filter(lambda a: a != 666), serial=st.integers(min_value=1, max_value=9999))
def test_ssn_rejects_group_00(area: int, serial: int):
    a, s = f"{area:03d}", f"{serial:04d}"
    assert not _fires("us_ssn", f"SSN: {a}-00-{s}")


@given(area=st.integers(min_value=1, max_value=898).filter(lambda a: a != 666), group=st.integers(min_value=1, max_value=99))
def test_ssn_rejects_serial_0000(area: int, group: int):
    a, g = f"{area:03d}", f"{group:02d}"
    assert not _fires("us_ssn", f"SSN: {a}-{g}-0000")


@given(st.text(min_size=1, max_size=200))
def test_shannon_entropy_is_never_negative(s: str):
    assert detectors.shannon_entropy(s) >= 0.0


@given(st.characters(), st.integers(min_value=1, max_value=200))
def test_shannon_entropy_of_a_repeated_character_is_zero(ch: str, count: int):
    assert detectors.shannon_entropy(ch * count) == 0.0


@given(st.text(min_size=1, max_size=50, alphabet=st.characters(min_codepoint=33, max_codepoint=126)))
def test_shannon_entropy_is_invariant_under_shuffling(s: str):
    """Entropy is a function of the character *frequency distribution*, not
    order - reversing the string must give the exact same value."""
    assert detectors.shannon_entropy(s) == detectors.shannon_entropy(s[::-1])


@given(st.integers(min_value=1, max_value=26))
def test_shannon_entropy_of_all_distinct_characters_equals_log2_n(n: int):
    """n equiprobable distinct symbols -> entropy is exactly log2(n) - the
    textbook maximum-entropy case, distinct from the repeated-character
    minimum case above."""
    s = "".join(chr(ord("a") + i) for i in range(n))
    assert math.isclose(detectors.shannon_entropy(s), math.log2(n), abs_tol=1e-9)
