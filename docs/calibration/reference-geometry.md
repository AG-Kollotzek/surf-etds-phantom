# Reference geometry and kV cross-validation

This page documents two properties of the SURF Test Unit that matter to anyone
reading results obtained with it:

1. the geometric imperfections of the phantom that its kinematic model does not
   contain, as characterised on 10 March 2026;
2. how sensitive the stereotactic kV cross-validation of the phantom is at each
   position where it is taken.

Both were derived during pre-publication review from the exported evaluation
files of the analysis repository
[`surf-etds-analysis`](https://github.com/tim-buck/surf-etds-analysis), as they
stood on 15 September 2026. The computation is described below
so it can be repeated; it is not part of this repository.

## 1. Geometry the kinematic model does not contain

### What the model assumes

The kinematic model (`kinematics_werror_v2.py` in the analysis repository) sets
the local lateral coordinate to zero for every axis position
(`x_local = h_u * 0`), contains no translation term for the rotation axis, and
gives roll ≡ 0 whenever R = 0 (`roll = arcsin(sin p · sin r)`). Any real lateral
motion, roll at R = 0, or translation caused by rotation is therefore absent from
the modelled ground truth.

### Method

For each isolated-axis run of the 10 March 2026 campaign (horizontal, vertical,
rotation; n = 3 runs per condition; room temperature and 32 °C):

- Residual = tracked pose − modelled pose, from `03_residual3d.csv`, joined on
  time to the modelled pose in `02_after_align_phantom.csv`.
- Settled plateaus are the samples at ≥ 95 % of the peak deflection of the driving
  channel: modelled longitudinal position for the horizontal and vertical runs,
  modelled yaw for the rotation runs.
- The residual of each degree of freedom is split into a component that reverses
  sign with the deflection (antisymmetric: half the difference of the mean residual
  on the positive and the negative plateau) and one that does not (symmetric).

### Result

The antisymmetric components in degrees of freedom the model predicts to be zero
repeat across runs and are the same at both temperatures (mean ± SD, n = 3):

| Axis → degree of freedom | Room temperature | 32 °C |
|---|---|---|
| Vertical → lateral | −0.524 ± 0.011 mm | −0.512 ± 0.008 mm |
| Vertical → roll | −0.114 ± 0.005° | −0.100 ± 0.011° |
| Horizontal → lateral | −0.110 ± 0.004 mm | −0.126 ± 0.008 mm |
| Rotation → longitudinal | +0.084 ± 0.010 mm | +0.088 ± 0.009 mm |
| Rotation → lateral | +0.070 ± 0.019 mm | +0.066 ± 0.004 mm |

Three geometric parameters account for all five:

| Parameter | From the residuals | From kV sphere detection |
|---|---|---|
| Yaw of the vertical axis's tilt (pivot) axis | 2.07–2.12° (lateral ÷ longitudinal), 1.95–2.23° (roll ÷ pitch) | ≈ 2.2° (2.0–2.4°) |
| Apparent yaw of horizontal travel | 0.63–0.72° | ≈ 0.6° (0.3–0.9°) |
| Offset of the tracked surface centroid from the rotation axis | 1.28–1.29 mm | ≈ 1.1 mm |

How each follows:

- **Tilt-axis yaw.** Tilting about an axis yawed by ψ turns part of the
  longitudinal travel into lateral travel and part of the pitch into roll, so both
  ratios equal sin ψ. At the vertical runs' plateaus the modelled longitudinal
  half-amplitude is 14.16 mm and the pitch half-amplitude 2.93°. The two ratios
  agree to within 0.3°.
- **Horizontal travel.** The horizontal runs' longitudinal half-amplitude is
  9.98 mm; the lateral component gives the apparent yaw.
- **Rotation-axis offset.** A centroid at distance d from the rotation axis moves
  by d · sin θ; at θ = ±4.95° the in-plane antisymmetric component of 0.110–0.111 mm
  gives d.
- **kV column.** The kV estimates use `xray_verification_v2.csv` (points 2, 5 and 6)
  in the analysis repository, which does not involve the surface tracker. Its
  readout is quantised to 0.1 mm, hence the ranges. The earlier offset estimate of
  ≈ 1.1 mm comes from the kV rotation points (docstring of `xray_verification_v2.py`).

### What this means

- **The phantom's axes are not perfectly aligned with the tracking coordinate
  system, and not with each other.** The phantom was placed rigidly on the couch
  and aligned by eye to the room lasers, so a setup or couch yaw of a fraction of a
  degree is expected. A yaw of the whole phantom on the couch would shift the
  tilt-axis and horizontal angles by the same amount. Setup can therefore
  explain at most their common part; the difference of about 1.4° is a property of
  the mechanism.
- **A couch tilt cannot produce these components.** Tilting about a horizontal
  axis mixes vertical into lateral, but the vertical runs move the surface by the
  same ≈ −0.42 mm vertically on both sides of zero, so a tilt adds nothing that
  reverses sign. The flatness of the hexapod couch top was not documented. The
  horizontal runs bound the pitch of horizontal travel relative to the tracker at
  0.03–0.08°, at most about 0.15°, from a vertical component of
  −0.013 ± 0.002 mm (room temperature) and −0.006 ± 0.010 mm (32 °C) per 9.98 mm,
  where the model predicts none. Roll of the couch top cannot be observed in these
  runs.
- **Re-seating the phantom head on its printed adapter changes the rotation-axis
  offset,** and possibly the effective lever arm. It does not change the tilt-axis
  yaw, which belongs to the vertical mechanism. A repeat estimate of the tilt-axis
  yaw is therefore a direct check that the vertical mechanism is unchanged between
  sessions. The head orientation was not recorded in any campaign. According to the
  hardware author, the spread of the per-linac lever-arm calibrations is most
  plausibly mechanical instability of this kind.
- **On-axis antisymmetric components** (for example rotation → yaw, −0.162° at room
  temperature) cannot be attributed from these data: rotary backlash and a scale
  mismatch in either system both produce them.

These values describe the build as used on 10 March 2026. The kinematic model does
not contain them, so off-axis residuals of this size are a property of the
reference and must not be read as tracking error.

## 2. Sensitivity of the kV cross-validation

The phantom is cross-validated against stereotactic kV sphere detection. How much
such a check can reveal about the calibrated lever arm (`SD_CALIB`, 4.156 mm)
depends on where the sphere is imaged.

Sensitivity of the modelled pose to the lever-arm offset, by central difference
(±0.5 mm around 4.156 mm) with `SurfKinematicsNominalV2`:

| Position | ∂ longitudinal / ∂ lever arm | Lever-arm change that moves the readout by one 0.1 mm step |
|---|---|---|
| V = +10 mm (March verification) | −0.052 mm/mm | ≈ 1.9 mm |
| V = −10 mm (March verification) | +0.051 mm/mm | ≈ 2.0 mm |
| H = −10, V = 20 mm (QA deflection 1) | −0.104 mm/mm | ≈ 1.0 mm |
| H = −30, V = 50 mm (QA deflection 2) | −0.264 mm/mm | ≈ 0.4 mm |
| H = +10 mm, V = 0 | 0 | not sensitive |

Between the calibrated and the uncalibrated model the difference at V = +10 mm is
0.214 mm.

Consequences:

- The March verification positions (V = ±10 mm) cannot detect a lever-arm change
  smaller than about 2 mm, more than three times the standard deviation of the
  per-linac calibrations (0.55 mm, `SD_CALIB_DEFAULT` in the analysis repository).
- The July–August QA positions detect changes down to about 0.4 mm (deflection 2),
  so they are the ones that can demonstrate stability of the lever arm.
- Positions with V = 0 carry no information about the lever arm at all.
- A statement that the phantom was cross-validated should always name the positions
  used.
