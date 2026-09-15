# Disclaimer — research use only

## Not a medical device

The SURF Test Unit — the mechanical phantom, its Arduino firmware, the PC
terminal, the measurement blueprints and the measurement data in this
repository — is **research hardware and research software**.

- It is **not a medical device**.
- It has **not been assessed under Regulation (EU) 2017/745 (MDR)** or under any
  other medical-device regulation, and no conformity assessment procedure has
  been carried out for it.
- It carries **no CE mark** and no declaration of conformity.
- It has not been assessed for electrical safety, electromagnetic compatibility,
  functional safety, or risk management by any notified body or by any formal
  internal process. The repository contains no such assessment.

## Permitted and prohibited use

This equipment **must not** be used:

- in patient treatment, or in the same treatment session as a patient;
- for clinical decision-making of any kind, including the acceptance,
  release, commissioning or periodic constancy testing of a clinical system
  where the result would alter patient treatment;
- on, in or attached to patient-bearing equipment in a way that could affect
  that equipment's function or its own conformity;
- by personnel who are not trained in the hazards described in
  [`safety.md`](safety.md).

It is intended **only** for phantom measurements — that is, measurements on
inanimate test objects with no patient present — carried out by qualified
medical-physics personnel, under the local institution's own governance for
research equipment, room access, radiation protection and electrical safety.
Local rules always take precedence over anything written in this repository.

Any use of the results in a clinical context remains the full responsibility of
the qualified professional making that decision, who must independently verify
them with an established, approved method.

## No warranty

This work is provided **"as is", without warranty of any kind**, express or
implied, including but not limited to the warranties of merchantability,
fitness for a particular purpose, accuracy, and non-infringement. The authors
and their institutions accept no liability for any claim, damage, injury or
other liability arising from the use of, or inability to use, this hardware,
software or data.

The firmware, software and data are released under the licences named in
`LICENSES/`; the warranty disclaimers in those licences apply in full and are
not narrowed by this document.

The defects documented in [`safety.md`](safety.md) and
[`known-issues.md`](known-issues.md) are known and unresolved at the time of
publication. They are published so that a reproducer can judge the
risk, not because they have been mitigated.

## Trademarks and non-affiliation

"ExacTrac", "ExacTrac Dynamic" and "Brainlab" are trademarks of Brainlab AG.
"Varian" is a trademark of Varian Medical Systems, Inc. (a Siemens Healthineers
company). All other product names, including those of component manufacturers,
are the trademarks of their respective owners.

These marks are used **nominatively**, solely to identify the commercial systems
that this work was measured against or alongside, as required for a factual
technical description. Their use does not imply any endorsement, sponsorship,
certification or approval.

**Neither Brainlab nor Varian, nor any other named vendor, endorses this work,
is affiliated with it, has reviewed it, or is responsible for it in any way.**
This work is not derived from any vendor's confidential documentation, and it
is not a substitute for the QA procedures specified by the manufacturer of any
clinical system. Nothing here should be read as a statement about the
performance, safety or conformity of any commercial product.
