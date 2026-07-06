from agentic_pureclip.pipeline.motifs import MotifPWM, scan_sequence_with_pwm
from agentic_pureclip.scoring.objective import composite_objective


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


def test_pssm_with_negative_cells_does_not_crash():
    # RBPmap *_PSSM matrices store log-odds values that can be negative.
    # Normalizing those by their row sum yields negative pseudo-frequencies;
    # log_odds must clamp them instead of raising "math domain error".
    pssm = MotifPWM(
        motif_id="HNRNPK_gccca_human_PSSM", rbp_name="HNRNPK", database="RBPmap_1.2",
        pwm=[{"A": -2.1, "C": 3.4, "G": -1.8, "T": -2.0},
             {"A": -3.0, "C": 4.1, "G": -2.5, "T": -2.2},
             {"A": -1.0, "C": -1.0, "G": 2.0, "T": -1.0}],
    )
    low, high = pssm.score_range()          # must not raise
    assert low < 0 < high
    # Disfavored bases become strongly negative log-odds; the peaked base wins.
    assert pssm.match_threshold(0.80) > pssm.match_threshold(0.0)
    assert pssm.consensus == "CCG"


def test_composite_penalises_reproducible_noise():
    balanced = {"replicate_agreement": 0.60, "motif_hit_rate": 0.40}
    noisy = {"replicate_agreement": 0.66, "motif_hit_rate": 0.20}
    # Higher agreement but collapsed motif => composite must not reward it.
    assert composite_objective(noisy) < composite_objective(balanced)


def test_composite_falls_back_without_motif():
    assert composite_objective({"replicate_agreement": 0.5, "motif_hit_rate": None}) == 0.5


def test_composite_recall_punishes_site_collapse():
    # Collapsing sites can raise reproducibility & motif but drops known-site recall;
    # the composite must not reward it.
    broad = {"reproducibility_score": 0.30, "motif_hit_rate": 0.30, "benchmark_region_recall": 0.40}
    collapsed = {"reproducibility_score": 0.35, "motif_hit_rate": 0.35, "benchmark_region_recall": 0.10}
    assert composite_objective(collapsed) < composite_objective(broad)


def test_composite_prefers_chance_corrected_reproducibility():
    # Raw agreement is gameable; the chance-corrected score should be used instead.
    report = {"replicate_agreement": 0.90, "reproducibility_score": 0.10}
    assert composite_objective(report) == 0.10


def test_composite_renormalises_over_present_terms():
    assert composite_objective({"reproducibility_score": 0.42}) == 0.42


def test_collapse_guard_crushes_tiny_site_counts():
    # 1 "perfect" site must score far below a real multi-site solution.
    collapsed = {"reproducibility_score": 1.0, "motif_hit_rate": 1.0,
                 "benchmark_region_recall": 0.1, "n_binding_sites": 1}
    real = {"reproducibility_score": 0.43, "motif_hit_rate": 0.36,
            "benchmark_region_recall": 0.1, "n_binding_sites": 14}
    assert composite_objective(collapsed) < composite_objective(real)
    assert composite_objective(collapsed) < 0.15


def test_collapse_guard_inactive_above_floor():
    # At/above the floor the guard does not change the score.
    rep = {"reproducibility_score": 0.5, "motif_hit_rate": 0.5,
           "benchmark_region_recall": 0.5, "n_binding_sites": 500}
    assert composite_objective(rep) == 0.5
