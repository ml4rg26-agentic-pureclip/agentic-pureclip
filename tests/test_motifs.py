from pipeline.motifs import MotifPWM, scan_sequence_with_pwm
from agent.decisions import composite_objective


def _conserved_pwm(consensus: str) -> MotifPWM:
    """Build a PWM strongly conserved toward a consensus string."""
    rows = []
    for base in consensus:
        row = {n: 0.01 for n in "ACGT"}
        row[base] = 0.97
        rows.append(row)
    return MotifPWM(motif_id="t", rbp_name="X", database="db", pwm=rows)


def test_log_odds_consensus_is_max_score():
    pwm = _conserved_pwm("TGCATG")
    low, high = pwm.score_range()
    assert low < 0 < high
    # The consensus sequence achieves the maximum possible score.
    assert abs(pwm.score_sequence("TGCATG") - high) < 1e-9


def test_match_threshold_is_monotonic():
    pwm = _conserved_pwm("TGCATG")
    assert pwm.match_threshold(0.0) < pwm.match_threshold(0.8) < pwm.match_threshold(1.0)


def test_scan_distinguishes_motif_from_background():
    pwm = _conserved_pwm("TGCATG")
    thr = pwm.match_threshold(0.80)
    assert scan_sequence_with_pwm("AAATGCATGAAA", pwm, thr)      # contains motif
    assert not scan_sequence_with_pwm("AAAAAAAAAAAA", pwm, thr)  # no motif


def test_flat_position_scores_near_zero():
    # A uniform position carries no information => log-odds ~ 0.
    flat = MotifPWM(motif_id="f", rbp_name="X", database="db",
                    pwm=[{n: 0.25 for n in "ACGT"}])
    low, high = flat.score_range()
    assert abs(high) < 0.05 and abs(low) < 0.05


def test_composite_penalises_reproducible_noise():
    balanced = {"replicate_agreement": 0.60, "motif_hit_rate": 0.40}
    noisy = {"replicate_agreement": 0.66, "motif_hit_rate": 0.20}
    # Higher agreement but collapsed motif => composite must not reward it.
    assert composite_objective(noisy) < composite_objective(balanced)


def test_composite_falls_back_without_motif():
    assert composite_objective({"replicate_agreement": 0.5, "motif_hit_rate": None}) == 0.5
