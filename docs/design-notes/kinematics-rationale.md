# Kinematics rationale: why three degrees of freedom, and what they cannot support

**Scope.** This note explains why the SURF Test Unit has three motorised axes
rather than six, and what that choice rules out.

**Status.** It was written during release preparation (2026-09). Statements
about repository contents refer to that state.

**Provenance.** The note supersedes `docs/PoPargumentation&blueprints.txt`, an
informal German discussion note that was removed during release preparation
(CHANGELOG.md:52–53). Sections 2–8 restate that note's arguments and tighten
them. Where the repository contradicts or does not support a point, we say so.
Section 9 is new.

**References.** Defects cited as KI-nn are described in
[`../known-issues.md`](../known-issues.md). Code and data claims cite their
location; paths are relative to the repository root.

## 1. The rig as built

| Axis | Motion | Range | Resolution | Notes |
|---|---|---|---|---|
| H | Horizontal slide | −45 … +25 mm (`SURF_nanoAxis_v5.ino:55–58`) | 800 steps/mm (:39) | |
| V | Vertical slide | −35 … +50 mm (:61–64) | 800 steps/mm (:39) | Moves the phantom vertically and tilts it about a horizontal axis at the same time (README.md:103). The protocol of 2026-03-10 describes a V = +50 mm start as "tilt needed" (`data/raw/2026-03-10/runs.csv:25`). |
| R | Rotation stage, driven through a 1:2 bevel gear (README.md:104) | −30 … +120° (`SURF_nanoAxis_v5.ino:67–70`) | 16.156 steps/° (:40) | No endstop; the zero is set wherever the stage stands (:392–397, :420–424). |

Speeds are capped at 50 mm/s for H and V and at 90°/s for R (:42–43). On H and V
this cap never engages, because step generation saturates at about 5 mm/s
(KI-23).

Each axis has a CL57T driver (:4). According to the hardware author, these are
closed-loop stepper drivers that correct step loss against a motor encoder.

Two heated pads bring the phantom surface to a skin-like temperature.

The tracking system under test reports three translations and three rotations:
lateral, longitudinal and vertical shift, plus pitch, roll and yaw. These are
the fields the MATLAB viewer reads from its export
(`matlab/ETDCombinedJSONCSVViewerApp.m:244`).

The repository does not document the geometry needed to relate the two:

- It contains no drawings.
- It does not record whether the R stage sits beneath the V mechanism or rides
  on it.
- It gives no link lengths or pivot position for the V coupling.
- It does not give the orientation of the R axis relative to the phantom
  surface.
- It contains no forward-kinematic model.

The pairing between rig axes and tracker axes depends on the mounting and the
couch angle. The MATLAB viewer offers four pairings, including `Pos_V` against
both vertical and longitudinal shift
(`matlab/ETDCombinedJSONCSVViewerApp.m:866–873`).

The QA blueprints compensate a −90° couch rotation by driving R to +90°
(`blueprints/qa/ETsurface_easyQA_wcouch_T32_new.json:124–128`). In that
mounting, R therefore turns about an axis parallel to the couch rotation axis.
This is inferred from the procedure; no documented dimension states it.

## 2. Purpose, and the requirements that follow from it

The rig produces reference poses against which the tracker's output is compared.
It is not a patient-positioning device and never has to correct an arbitrary
pose. Two requirements follow:

1. Every commanded state must correspond to a pose that is known in the tracker's
   frame, to a stated uncertainty.
2. The set of poses must exercise the tracker in the ways the validation claims
   to cover.

A correction device needs independent control of all six pose components. A
measurement reference needs neither independence nor completeness. It needs to
know the pose it produced, and a pose set that matches the claims made from it.
The three-axis design meets the first requirement in principle. It meets the
second only for restricted claims (Section 9.5).

## 3. Why coupled axes do not destroy the ground truth

The V slide couples a vertical shift with a pitch rotation. One might conclude
that a rig which cannot move one without the other cannot validate either.

For validation, that conclusion is wrong. Suppose the mechanism is rigid and its
geometry is known. Forward kinematics then maps each axis state (H, V, R) to
exactly one six-component pose.

- The coupling restricts which poses are reachable: a three-parameter family
  inside the six-dimensional pose space.
- It does not make any reachable pose unknown. For each one, the expected
  tracker output is determined.
- A tracker that reports the coupled pose correctly (vertical shift and pitch
  together, in the right proportion) has measured that pose correctly.

The coupling is therefore a modelling constraint, not a loss of ground truth. It
even has a use: a tracker that mistook a vertical shift for a pitch, or the
reverse, would show an error along V, provided the shift-to-pitch ratio is known
accurately.

The argument rests on conditions that are easy to leave unstated:

- **A kinematic model must exist and be accurate.** That includes the rigidity
  it assumes. Compliance, such as deflection of the V slide under load, has not
  been measured.
- **The axis states must be what the log says they are.** Here the model's inputs
  are commanded step counts, not measured output positions.

Section 9.4 shows that the repository meets neither condition.

The argument also does not generalise. Validating the tracker on the reachable
family says nothing about poses outside it, unless the tracker's errors are known
not to depend on the directions the rig cannot excite. This rig cannot provide
that evidence.

## 4. Cost

The original note put a three-axis rig at roughly €1,000–2,000 and a six-axis
robot at roughly €20,000. Both figures are estimates from that note, not the
result of a costed bill of materials or a quotation. The parts list in
`hardware/bom.csv` carries no prices. Taken at face value, the
difference of about an order of magnitude made a dedicated phantom feasible for
this project.

The saving buys a restricted experiment, not a cheaper equivalent of the robot.
The cost argument holds only if the limits of Section 9 are stated alongside
every result obtained with the rig.

## 5. Single-axis excursions first; what mixed poses would add

We began with symmetric excursions of one axis at a time. They isolate the
properties of each axis (backlash, resolution, the V coupling) and give a
baseline in which each tracker reading can be attributed to a single input.

The original note recommended mixed multi-axis poses as the next step, for three
reasons:

1. **Coordinate-system calibration.** Phantom and tracker frames are related by
   an unknown transformation.
   - The couch angle (0° or 90°) gives only a coarse estimate of it.
   - Poses that vary several axes together allow the full transformation to be
     estimated, much as in hand–eye calibration.
   - Single-axis excursions constrain it only along the few directions they span.
2. **Field-of-view coverage.** Optical tracking systems often distort
   non-linearly towards the edges of their field of view. Excursions along the
   main axes stay near the centre; mixed poses reach the corners of the working
   volume.
3. **Mechanical tolerances.** Combining axes reveals whether mechanical errors
   add up, for example deflection of the V slide while R is far from zero.
   Single-axis runs cannot expose interactions between axes.

The proposed design was a set of 10–15 pseudo-random mixed poses inside the safe
volume, each compared with the pose computed from the kinematics.

That design has not been carried out, and its precondition, a kinematic model,
is also absent (Section 9.4). The QA blueprints do dwell at two combined poses,
reached by sequential single-axis moves
(`blueprints/qa/ETsurface_easyQA_new.json:45–47`, :85–87):

- d1: H −10 mm, V +20 mm, R 1°;
- d2: H −30 mm, V +50 mm, R 2°.

Section 9.1 explains why these two poses cannot stand in for the design.

## 6. Command resolution: why sub-millimetre and sub-degree targets are accepted

Resolution and accuracy are different things.

- **Resolution** is the smallest increment the rig can be commanded to make.
- **Accuracy and repeatability** are set by the mechanics.

The software accepts decimal targets and converts them to integer steps only at
the last moment (`terminal.py:726`, :739; manual commands :1213, :1223). A
blueprint may therefore command 0.1 mm or 0.1°.

The original note gave the reason this matters: sensitivity questions need
increments at or below the tracker's display resolution. An example is whether
the tracker registers a 0.3 mm shift. Restricting targets to whole millimetres
would waste what the linear axes can do.

The repository's evidence on the tracker's display resolution is indirect. The
operator-entered sphere-detection shifts carry one decimal (e.g.
`data/raw/2026-08-06/ETsurface_easyQA_20260806_163851_QA.csv`), which is
consistent with a 0.1 mm display. The tracker's actual resolution is not
documented here.

What the repository supports, axis by axis:

- **H.** One step is 1.25 µm.
  - A single dial-gauge session found no measurable backlash on H, at most 5 µm,
    and recorded that 0.1 mm moves were reached as commanded
    (`docs/calibration/backlash-measurement-raw.txt:20–21`).
  - This supports sub-millimetre commands on H, subject to an uncalibrated scale.
- **V.** Nothing was measured. V carries the coupling, so its sub-millimetre
  behaviour is an open question.
- **The drivers.** The original note said that closed-loop drivers "guarantee"
  that no steps are lost. That holds only in a narrow sense:
  - The CL57T drivers correct lost steps against their motor encoders and raise
    an alarm when they cannot.
  - The correction ends at the motor shaft. Errors in the screw, coupling, gear
    and linkage lie outside the loop.
  - The H and V alarms are transmitted to the PC but discarded there, and the
    firmware does not act on them during a move. R has no alarm input at all.
  - The archive therefore cannot show that no uncorrected step loss occurred
    (KI-05).
- **R.** One step is 0.062°, and targets are truncated to whole steps
  (`terminal.py:739`; KI-13).
  - A 0.1° command produces 0.062°; a 0.2° command produces 0.186°.
  - Sub-degree sensitivity work on R is dominated by quantisation before backlash
    or scale error even enter.

No archived blueprint uses the resolution the software allows. The smallest
commanded increments are:

- 3 mm on H (`blueprints/heating-off/ETD_QA_PoP_SingleCouchRotation_OnlyH_Clin.json`);
- 9.41 mm on V (`blueprints/qa/ETsurface_easyQA_draft.json`);
- 1° on R (the QA blueprints and `…_RvaryAmp.json`).

The "jitter" experiments the note proposed, to find the tracker's detection
threshold, were never run.

## 7. The rotation axis is the limiting axis

Several limitations compound on R:

- **Gear backlash.** R is driven through a simple 1:2 bevel gear. On a direction
  reversal, the teeth must cross their clearance before the output moves.
  - The original note expected 0.5–1.5° for such a gear.
  - The one measurement in the repository found 0.05–0.06 mm at a 15 mm lever
    arm. That is 0.19–0.23°, or about 3–4 steps
    (`docs/calibration/backlash-measurement-raw.txt:24–33`,
    `rotation_calibration.ino:12–13`).
  - It comes from a single dial-gauge session, under an undocumented load, with a
    gauge resolution of about 0.04° at that radius. It gives an order of magnitude,
    not a characterisation.
- **Relative size.** The QA blueprints rotate R by 1° and 2°, so backlash of about
  0.2° is 10–20 % of the excursion. The ±5° excursions of the PoP blueprints are
  affected at the 4–5 % level.
- **Quantisation and scale.** One step is 0.062°, and targets are truncated toward
  zero. The scale factor 16.156 steps/° has no calibration record, and the
  calibration sketch carries a different value, 16.1599 (KI-13).
- **Reference.** R has no index mark. Its zero is set by eye and is lost with
  every controller reset (KI-06).
- **Monitoring.** The R driver's alarm output is not wired, so an R driver that
  cannot hold position goes unnoticed (KI-05).

The linear axes are free of the gear-related terms. Their remaining
uncertainties are unmeasured, not known to be small: screw pitch, straightness,
and on V the coupling.

The measurement protocol of 2026-03-10, as transcribed in
`data/raw/2026-03-10/runs.csv:15`, notes a residual rotation offset after
backlash had been corrected: 4.7° read against 5° commanded. The discrepancy is
of the order of the measured backlash. Its cause is not established.

## 8. Backlash compensation by approach direction

Backlash does no harm at a dwell pose if the gear rests on the same tooth flank
every time that pose is reached. Two strategies build on this.

**Unidirectional approach (proposed in the original note).** Every dwell target
is approached from the same side. To reach a lower angle, the axis first
overshoots below the target by more than the backlash, then moves up to it. For
example, going from 10° to 5°, it runs to 3° and then to 5°.

- *Advantages.*
  - The backlash magnitude never needs to be known, only an upper bound for the
    overshoot.
  - The method is insensitive to wear and to changes in the clearance.
  - If the zero was set using the same approach, it too sits on the same flank.
- *Disadvantages.*
  - It adds motion time.
  - The trajectory becomes non-monotonic. The tracker sees the overshoot, and
    dynamic analyses must handle it.
  - It fails if the load torque changes sign between dwell points, because the
    load then decides which flank carries.

**Reversal compensation (implemented in the firmware,
`SURF_nanoAxis_v5.ino:335–361`).** On every change of direction the firmware
issues four extra steps (≈0.248°). It then resets the step counter, so the
correction does not appear in the log.

- *Advantages.* Trajectories stay monotonic, and no extra motion is needed.
- *Disadvantages.*
  - It is correct only if the clearance is constant, equals the programmed four
    steps, and is not taken up by load torque.
  - It infers the flank state from the last commanded direction, which becomes
    stale when compensation is toggled (:358–360).
  - It is off by default, can be enabled only from the console, is lost on every
    controller reset, and is recorded nowhere. Its state during any archived run
    is therefore unknown (KI-12).

**Our assessment.**

- For static dwell accuracy, which is what the QA and PoP blueprints evaluate,
  unidirectional approach is the more robust choice: it needs no calibration
  constant, and the log shows exactly what it did.
- Reversal compensation suits continuous motion better, but only if its state and
  its corrections are logged.
- Neither strategy has been validated beyond one dial-gauge check made after the
  firmware change: a move to 1.2° gave 31 divisions, and the return to 0 read 0
  (`docs/calibration/backlash-measurement-raw.txt:35–39`).
- No archived blueprint uses unidirectional approach. The QA blueprints approach
  the combined poses from below and return to zero from above
  (`blueprints/qa/ETsurface_easyQA_new.json:47`, :64, :87, :104). Every R dwell
  that follows a reversal is therefore exposed to backlash, whatever the
  compensation state was.

## 9. What this design cannot support

The arguments above make the three-axis rig adequate for a narrower claim than
"validating a 6-DOF tracking system" suggests. This section sets out the limits
plainly.

### 9.1 Motion as executed: one axis at a time, and linear axes at a single speed

**Evidence**

- **Interpreter.** A blueprint `move` step dispatches its axes one at a time, in
  the fixed order H, V, R. Each command is queued only after the previous one has
  been acknowledged (`terminal.py:724–747`).
- **Firmware.** A move runs inside a loop that steps only the selected motor until
  it arrives; the acknowledgement is sent after that loop
  (`SURF_nanoAxis_v5.ino:326–377`).
  - Under blueprint control the controller cannot run two axes at once.
  - The main loop does step all three motors (:280), but no command ever starts
    concurrent moves.
  - The axis firmware has had the same blocking structure since 2026-02-16
    (commit `3f922f5`).
- **Blueprints.** No blueprint in the repository, or anywhere in its git history,
  contains a `move` step with more than one axis.
- **Data.** In none of the 118 main-format telemetry files do two axes change over
  two or more consecutive sampling intervals. The isolated single-interval
  coincidences are hand-overs between consecutive single-axis moves.
- **The one exception.** Two early pilot recordings, made with superseded firmware
  and console tools, do contain concurrent two-axis motion:
  - `data/raw/2025-12-pilot/manual_final_h_0-10.csv` (V together with R);
  - `data/raw/2026-01-pilot/qa_log_20260126_103910.csv` (H together with V, for
    about 20 s).

  Nothing in the repository links either recording to tracker exports or
  describes it as a designed experiment.

**Consequences**

- **Dynamic cross-talk cannot be separated with the rig as built.** An example of
  such cross-talk is rotation corrupting the tracker's translation estimate while
  both change. The tracker has never been observed under a known, simultaneous
  translation-and-rotation trajectory.
- **The combined static poses do not help.** Between the zero pose and d1 or d2,
  all three axes change at once. The operator-entered sphere-detection shifts of
  one run illustrate this (`data/raw/2026-08-06/ETsurface_easyQA_20260806_163851_QA.csv`):
  - d1: (0.6, −17.2, −0.5) mm;
  - d2: (0.6, −36.6, −3.2) mm.

  Two readings like these cannot be attributed to H, to V with its coupled pitch,
  and to R without a kinematic model, and there is none (Section 9.4).

**Linear motion ran at a single speed**

- The blueprints command H and V at 20 mm/s for traverses and 50 mm/s for sync
  pulses.
- Every archived H and V motion segment ran at about 5.1 mm/s instead: the median
  over 1,094 segments is 5.08 mm/s. Step generation saturates near 4000 steps/s
  (KI-23).
- R did reach its commanded speeds, 0.5–20 °/s, most often 5 °/s, and 2 °/s in
  the QA blueprints.

Dynamic tracking was therefore exercised at about 5 mm/s on the linear axes,
whatever speed the blueprints specify. The archive contains no linear motion
faster than that, and no genuine comparison of "fast" with "normal" linear moves.

### 9.2 The ground truth is a commanded step count, not a measurement

- **Every logged position is a step count.** It is the firmware's count of issued
  steps (`SURF_nanoAxis_v5.ino:162–164`), converted with nominal factors. No axis
  has independent output-side position metrology. The drivers' motor encoders
  stay inside the drivers and are never read out.
- **V has never been characterised.** It is the axis that carries the coupling,
  yet the repository records no measurement of its backlash, linearity,
  straightness or compliance.
- **The drivers' guarantee ends at the motor shaft.** The closed-loop drivers
  correct step loss at the motor shaft and raise an alarm when they cannot.
  However:
  - The terminal discards the H and V alarm bits.
  - The firmware does not act on an alarm during a move.
  - R has no alarm input.

  The archive therefore cannot show that no uncorrected loss occurred. Errors
  between motor shaft and phantom are outside the drivers' loop altogether
  (KI-05).
- **The reference state is unrecorded.**
  - The axis reference is neither enforced nor logged, and the R zero is set by
    eye (KI-06).
  - The R scale factor is undocumented, and targets are truncated (KI-13).
  - The backlash compensation state is unknown (KI-12).
- **Some archived records do not reflect the physical motion at all.**
  - Moves the firmware rejected are acknowledged as completed (KI-01).
  - A missing controller produces a fabricated run (KI-02).
  - Firmware before 2026-02-24 reported no positions during moves (KI-11).

`data/raw/2026-03-10/runs.csv:18` records a radiographic check of static extreme
positions, carried out in the analysis repository. That check lies outside this
repository and is not assessed here. It could bound static errors at the
positions it covered; it cannot bound errors during motion.

### 9.3 Roll and yaw are not independent excitations

The tracker reports three rotation angles. The rig has only two rotational
inputs: the pitch produced by V (tied to a vertical shift) and R. Every reachable
orientation is therefore a function of the two parameters (pitch, R), and at most
two of the three reported angles can vary independently.

Which two depends on a construction detail the repository does not document:
whether the R stage sits beneath the tilting mechanism or rides on it.

- **R beneath the tilt.** R changes yaw and V changes pitch. Roll is never
  excited; it stays at zero apart from mounting error.
- **R on the tilted platform.** Once V has tilted the phantom, turning R changes
  yaw and roll together, in a proportion fixed by the pitch. Roll can neither be
  held constant while yaw varies nor be commanded on its own.

Either way, roll and yaw follow from (pitch, R) rather than being independent
excitations. Pitch cannot be produced without its coupled vertical shift.

The translations are restricted in the same way:

- At a fixed couch angle, H covers one horizontal tracker direction. The other is
  reached only by rotating the couch, as in the `wcouch` blueprints, and that
  rotation is a manual step outside the logged motion.
- A rotation about an axis that does not pass through the tracker's rotation
  centre appears in the tracker output together with a translation. The size of
  that translation depends on offsets the repository does not document.

### 9.4 "Known pose" rests on a model the repository does not contain

The argument of Section 3 needs a forward-kinematic model, and correct inputs to
it. Neither is available here.

- **The model.** The repository contains no drawings, no V-coupling geometry, no
  location or orientation of the R axis relative to the phantom surface or the
  tracker reference, no model code, and no calibration of any model (Section 1).
  Whether the analysis repository holds such a model, and how it was validated,
  is beyond what this note can assess.
- **The inputs.** They are commanded step counts, with all the limitations of
  Section 9.2.

In this project, "known pose" therefore means: the pose implied by the commanded
counts, under a model whose accuracy is not documented here. Any tracker error
computed against such poses includes the rig's own pose error, whose size is
unknown. It follows that:

- a small apparent tracker error does not establish tracker accuracy unless the
  rig's error has been bounded independently;
- a large apparent error does not establish tracker inaccuracy either.

### 9.5 What may and may not be claimed about a 6-DOF tracking system

**Claims we consider defensible**, from the archived data and subject to the
known issues:

- **Single-axis agreement.** Agreement between tracker output and logged
  commanded positions, stated separately for each excitation actually run:
  - H translation, V's coupled shift and pitch, and R rotation;
  - at the amplitudes, couch angles and heating conditions used, on this phantom;
  - at the speeds that were actually realised: about 5.1 mm/s on H and V, and the
    commanded speeds on R (Section 9.1).

  Because the agreement includes the rig's unquantified error, it bounds the
  combined tracker-plus-rig error, not the tracker's error alone.
- **Repeatability at revisited poses.** The repeatability of tracker readings at
  dwell poses revisited within a run, such as the zero pose. The rig's own
  repeatability is unmeasured, so the observed spread is an upper bound on the
  tracker's contribution only if the two are independent.
- **Qualitative behaviour.** Observations under the logged conditions, such as
  tracking losses the tracker reported during the documented motions.

**Claims we consider not defensible:**

- **6-DOF accuracy.** Roll, the second horizontal translation at a fixed couch
  angle, and vertical shift or pitch on its own were never excited independently.
  A reading near zero along those directions shows no response to motion that did
  not happen; it is not a measure of accuracy.
- **Cross-talk.** Nothing can be claimed about translation–rotation cross-talk
  during simultaneous motion (Section 9.1). Static cross-talk can be assessed only
  through a validated kinematic model (Section 9.4).
- **Accuracy finer than the rig's unverified uncertainty.**
  - R: nothing finer than about 0.25°, given backlash of about 0.2°, a 0.062° step,
    truncation and an uncalibrated scale.
  - V: nothing finer than its unmeasured behaviour allows, for translation or
    pitch.
  - H: sub-millimetre accuracy is plausible from the dial-gauge session, but has
    no scale calibration behind it.
- **Detection thresholds.** No blueprint commanded an increment below 1° on R or
  3 mm on H (Section 6).
- **Dynamic accuracy and latency finer than the log's timing.** The log samples at
  roughly 9.3 Hz, non-uniformly. Positions can be up to one 50 ms frame old,
  absolute start times have one-second resolution, and runs before 2026-02-24
  have no mid-move positions (KI-10, KI-11).
- **Linear tracking at any speed other than about 5 mm/s.** In particular, no
  claim at the 20 mm/s and 50 mm/s written in the blueprints (KI-23).
- **Generalisation.** Nothing beyond this phantom and the conditions logged: not
  to patients, other surfaces or other rooms, and not to any clinical acceptance
  or commissioning decision ([`../disclaimer.md`](../disclaimer.md)).

## 10. What would lift these limits

- **Simultaneous motion.** Firmware that moves several axes together along a
  defined trajectory, logging positions and timestamps at the controller.
- **Independent position metrology.**
  - An absolute encoder on the output side of the R gear.
  - Linear encoders, or at least dial-gauge checks, on H and V.
  - An external reference for static poses, such as a laser tracker or an optical
    coordinate-measuring system.
- **A kinematic model.** A documented model of the V coupling and the R axis,
  calibrated against that external reference, with a stated uncertainty.
- **Roll excitation.** A mounting fixture or a fourth axis.
- **A designed pose set.** The mixed pose set of Section 5, with single-axis
  perturbations around each pose so that per-axis effects can be identified.
