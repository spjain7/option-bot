"""Failure labels for stage-1 cells (pre-registered in PREREGISTRATION.md), applied in this order:
  TOO_FEW                    n_days(DEV) < 40
  WRONG_SIGN                 DEV excess t <= -2 (the pattern predicts the OPPOSITE direction)
  INFO_SPENT_BEFORE_ENTRY    DEV excess from the signal close has t >= 2, but from the executable next open t < 1
  NO_INFO                    DEV excess t < 1
  NOT_SIGNIFICANT            BH q >= 0.10
  UNSTABLE                   VALID excess <= 0
  TOO_SMALL_VS_COST          raw gross fwd (DEV+VALID) < 2 x realistic round-trip cost (both in ATR)
  PASS_STAGE1                otherwise
"""
import numpy as np


def label(r):
    if not r.nd_DEV >= 40:
        return "TOO_FEW"
    if r.t_DEV <= -2:
        return "WRONG_SIGN"
    if r.tfd_DEV >= 2 and r.t_DEV < 1:
        return "INFO_SPENT_BEFORE_ENTRY"
    if r.t_DEV < 1:
        return "NO_INFO"
    if not r.q_DEV < 0.10:
        return "NOT_SIGNIFICANT"
    if not r.x_VALID > 0:
        return "UNSTABLE"
    if not (np.nan_to_num(r.raw_DV) >= 2 * r.cost_DV):
        return "TOO_SMALL_VS_COST"
    return "PASS_STAGE1"
